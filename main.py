#!/usr/bin/env python3
# main.py
#
# Copyright (c) 2025 - 2026 Michael Johnson
# All rights reserved.
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Licensed under the BSD 2-Clause "Simplified" License

"""Patch Creality Nebula Pad Firmware for Root SSH.

This tool will patch the firmware image for the Nebula Pad to support root SSH access.
If the requested firmware version is not downloaded, it will attempt to download the
file before patching.
"""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import click
import py7zr
from alive_progress import alive_bar, alive_it
from passlib.hash import md5_crypt, sha256_crypt
from py7zr.callbacks import ExtractCallback

from utils import Downloader, PrepareRoot, OtaTools


class FirmwareExtractCallback(ExtractCallback):
    """Callback function used by py7zr to display progress while extracting the firmware image."""

    def __init__(self, bar):  # noqa: D107
        self.bar = bar

    def report_start_preparation(self):  # noqa: D102
        pass

    def report_start(self, processing_file_path, processing_bytes):  # noqa: D102
        self.bar.text = f"processing {processing_file_path}"

    def report_update(self, decompressed_bytes):  # noqa: D102
        pass

    def report_end(self, processing_file_path, wrote_bytes):  # noqa: D102
        self.bar(int(wrote_bytes))

    def report_postprocess(self):  # noqa: D102
        pass

    def report_warning(self, message):  # noqa: D102
        pass


def validate_version(ctx, param, value):
    """Check input version format. Will match any string that contains digits with dots between them.

    :param ctx: Click context
    :param param: Optional parameter
    :param value: Optional value
    """
    version_format = r"^\d+(\.\d+)*$"

    if re.match(version_format, value):
        return value
    else:
        raise click.BadParameter("version number must be in the format w.x.y.z")


def __validate_requirements() -> bool:
    """Check the required external commands are available.

    :returns: True if all required external commands are available, False otherwise.
    """
    meets_requirements = True

    click.echo("Checking required external tools are installed...")

    for tool in ["unsquashfs", "mksquashfs"]:
        try:
            click.echo(f"Checking for '{tool}'... ", nl=False)
            subprocess.run([tool], capture_output=True)
            click.secho("Found", fg="green")
        except subprocess.CalledProcessError:
            # Some commands, like unsquashfs, will exit non-zero on checking.
            # As long as we didn't get a "not found" exception, we can guess that the tool exists.
            click.secho("Found", fg="green")
        except FileNotFoundError:
            # Command most definitely not found. Alert and exit.
            click.secho("MISSING", fg="red", bold=True)
            meets_requirements = False

    return meets_requirements


def __split_rooted_fs(
    working_dir: Path, dest_dir: Path, rooted_fs_stats: dict[str, str], delete_squashfs_file: bool
) -> None:
    """Split the rooted squashfs file while calculating hashes and adding to check file.

    :param working_dir: Path to the working directory where the sqaushfs file is located
    :param rooted_fs_stats: Dict containing the stats for the root squashfs file
    """
    # Split the generated file into 1048576 (1 mebibyte) byte chunks
    with (
        open(f"{working_dir}/rootfs.squashfs", "rb") as rootfs_file,
        open(f"{dest_dir}/ota_md5_rootfs.squashfs.{rooted_fs_stats['md5sum']}", "w") as ota_md5_file,
    ):
        # Ingenic OTAs do a thing where filesystem images are split into chunks of 1 mebibyte if they are larger than
        # that size. The naming scheme is weird in that the file is named as basename.XXXX.MD5 where XXXX is an integer
        # padded with zero and MD5 is a hex-encoded MD5 hash. The hash, however, is not the one of the actual chunk, but
        # that of the _previous_ chunk. For the file numbered 0000, the MD5 hash is that of the non-split file.
        #
        # The accompanying ota_md5 file, however, has the hash of each file in the correct order.
        chunk_number = 0
        prior_md5 = rooted_fs_stats["md5sum"]

        while True:
            chunk = rootfs_file.read(1048576)
            if not chunk:
                break
            chunk_hash = hashlib.md5(chunk).hexdigest()

            # Write the rootfs chunk out to a split file
            with open(f"{dest_dir}/rootfs.squashfs.{chunk_number:04d}.{prior_md5}", "wb") as rootfs_part_file:
                rootfs_part_file.write(chunk)
            chunk_number += 1

            # Add hash of the current chunk to the md5 hash file
            ota_md5_file.write(f"{chunk_hash}\n")

            # Store the hash for use in the next loop.
            prior_md5 = chunk_hash

    if delete_squashfs_file:
        Path(f"{working_dir}/rootfs.squashfs").unlink()


def __squash_rooted_fs(working_dir: Path, source_dir: str, delete_source_tree: bool) -> dict[str, str]:
    """Reassemble the split rootfs file.

    :param working_dir: Path to the directory where the squashed file should go
    :param source_dir: Name of the directory to squash
    :param delete_source_tree: If true, delete the source directory when done squashing
    :returns: dict containing the md5sum and size in bytes of the new squashfs file
    """
    # Return data structure
    rootfs_stats = dict(
        md5sum="",
        size=0,
    )

    with alive_bar(monitor=False, stats=False):
        subprocess.run(["mksquashfs", source_dir, "rootfs.squashfs", "-quiet", "-no-progress"], cwd=working_dir)

    with open(f"{working_dir}/rootfs.squashfs", "rb") as rootfs_file:
        rootfs_stats["md5sum"] = hashlib.file_digest(rootfs_file, "md5").hexdigest()

    rootfs_stats["size"] = Path(f"{working_dir}/rootfs.squashfs").stat().st_size

    if delete_source_tree:
        shutil.rmtree(f"{working_dir}/{source_dir}")

    return rootfs_stats


def __migrate_firmware_files(stock_path: Path, rooted_path: Path) -> None:
    """Move certain files we need to keep but not modify from the stock to the rooted structure.

    :param stock_path: Path to the stock files
    :param rooted_path: Path to the rooted files
    :returns: None
    """
    # Gather a list of all the files we need to move
    move_files_list = list()
    move_files_list.extend(list(stock_path.glob("xImage.*")))  # Get all the xImage file chunks
    move_files_list.extend(list(stock_path.glob("zero.bin.*")))  # Get all the "zero" file chunks
    move_files_list.extend(
        list(stock_path.glob("ota_md5_[!rootfs]*.*"))
    )  # Get the md5 checksum files except for rootfs

    # Move the files in our list to the rooted path
    with alive_bar(total=len(move_files_list)) as bar:
        for file in move_files_list:
            filename = Path(file).name
            Path(file).rename(f"{rooted_path}/{filename}")
            bar()


def __unsquash_rootfs(file: Path, working_dir: Path, delete_squashfs_source: bool) -> None:
    with alive_bar(monitor=False, stats=False):
        subprocess.run(["unsquashfs", "-q", "-n", file], cwd=working_dir)

    if delete_squashfs_source:
        file.unlink()


def __assemble_rootfs(rootfs_file_path: Path, delete_parts: bool) -> None:
    """Reassemble the split rootfs file.

    :param rootfs_file_path: Path to the directory holding the rootfs parts
    :param delete_parts: If true, delete the parts after reassembling the single file
    :returns: None
    """
    # Get a list of the part files and sort them by name
    rootfs_parts = list(rootfs_file_path.glob("rootfs.squashfs.*.*"))
    rootfs_parts.sort()

    # Reassemble the file from the found parts
    with open(f"{rootfs_file_path}/rootfs.squashfs", "wb") as rootfs_file:
        for part in alive_it(rootfs_parts):
            with open(part, "rb") as file_chunk:
                shutil.copyfileobj(file_chunk, rootfs_file)

    if delete_parts:
        for part in rootfs_parts:
            Path(part).unlink()


def __extract_firmware(firmware_full_path: Path, destination_dir: Path, password: str) -> None:
    """Extract the firmware image file.

    :param firmware_full_path: Full path of the firmware image.
    :param destination_dir: Destination directory.
    :param password: Password to extract the firmware image.
    :returns: None
    """
    with (
        py7zr.SevenZipFile(firmware_full_path, password=password) as firmware_archive,
        alive_bar(
            total=firmware_archive.archiveinfo().uncompressed,
            scale="IEC",
            unit="B",
            dual_line=True,
            spinner=None,
            stats=False,
        ) as bar,
    ):
        cb = FirmwareExtractCallback(bar)
        firmware_archive.extractall(path=destination_dir, callback=cb)


def __get_rooted_version(stock: str, prefix: str) -> str:
    """Return a version number with the first number replaced by the desired prefix."""
    version_parts = stock.split(".")
    version_parts[0] = prefix
    return ".".join(version_parts)


def __gen_root_password_hash(password: str) -> str:
    """Create a password hash compatible with the Linux shadow file format."""
    return sha256_crypt.using(rounds=5000).hash(password)


def __gen_firmware_password(board_name: str) -> str:
    """Generate the password for the firmware image file using the discovered mechanism."""
    return md5_crypt.using(salt="cxswfile").hash(f"{board_name}C3_7e_bz")


@click.command()
@click.option(
    "--board-name",
    default="NEBULA",
    help="Board name for the firmware image. Default is 'NEBULA'",
)
@click.option("--root-password", default="creality", help="Password to use for the root user. Defaults to 'creality'")
@click.option(
    "--source-version",
    default="1.1.0.30",
    help="The source version of the firmware to use. Default is '1.1.0.30'",
    callback=validate_version,
)
@click.option(
    "--prefix-version",
    default="6",
    help="A number to prefix the version by to avoid auto updates. Defaults to '6'",
)
def main(board_name, root_password, source_version, prefix_version):
    """Create a version of the Nebula Pad firmware with root SSH access."""
    # Commonly used variables throughout this tool
    image_password = __gen_firmware_password(board_name)
    rooted_version = __get_rooted_version(source_version, prefix_version)
    root_password_hash = __gen_root_password_hash(root_password)

    # Filename variables
    stock_firmware_basename = f"{board_name}_ota_img_V{source_version}"
    rooted_firmware_basename = f"{board_name}_ota_img_V{rooted_version}"

    # Filesystem-specific variables
    current_dir = Path(__file__).parent
    working_dir = Path(f"{current_dir}/working")
    firmware_dir = Path(f"{current_dir}/firmware")
    stock_firmware_ota_name = f"ota_v{source_version}"
    rooted_firmware_ota_name = f"ota_v{rooted_version}"
    stock_image_full_path = Path(f"{firmware_dir}/{stock_firmware_basename}.img").resolve()
    rooted_image_full_path = Path(f"{firmware_dir}/{rooted_firmware_basename}.img").resolve()

    stock_firmware_files_path = Path(f"{working_dir}/{stock_firmware_basename}/{stock_firmware_ota_name}")
    rooted_firmware_files_path = Path(f"{working_dir}/{rooted_firmware_basename}/{rooted_firmware_ota_name}")

    # Get the terminal width for formatting purposes
    termwidth = 80 if shutil.get_terminal_size().columns > 80 else shutil.get_terminal_size().columns

    click.echo(f"{click.style('Nebula Pad Firmware Root Tool', bold=True, reverse=True): ^{termwidth}}")
    click.echo()
    click.echo(f"Attempting to create a root-enabled image of version {click.style(source_version, bold=True)}")
    click.echo(f"Output image will have version number {click.style(rooted_version, bold=True)}")
    click.echo(f"The root user's password will be set to {click.style(f'{root_password}', bold=True)}")
    click.echo()
    click.Abort()
    click.secho("Pre-Run Checks", bold=True, underline=True)
    # Validate that any requirements are satisfied
    if __validate_requirements():
        click.echo("All required tools found. Proceeding.")
        pass
    else:
        click.secho("At least one required tool was not found. Cannot proceed.", fg="red")
        raise click.Abort()

    # Download the stock firmware, if it isn't in the "firmware" directory already
    if not Path(stock_image_full_path).is_file():
        click.echo("Stock firmware image not found. Attempting to download.")
        Downloader.download_firmware(source_version, firmware_dir)

    # End section
    click.echo()

    click.secho("Preparing Structure", bold=True, underline=True)

    # Extract the stock firmware image to our working directory
    click.echo("Extracting stock firmware from image")
    __extract_firmware(stock_image_full_path, working_dir, image_password)

    # Create the destination directory structure
    click.echo("Creating destination firmware directory structure")
    Path.mkdir(rooted_firmware_files_path.resolve(), parents=True)

    # Create the "ok" file in the rooted firmware structure
    click.echo(f"Creating the '{rooted_firmware_ota_name}.ok' file")
    Path(f"{rooted_firmware_files_path}/{rooted_firmware_ota_name}.ok").write_text("\n")

    # Parse the ota update data from the extracted firmware
    ota_update_data = OtaTools.parse_ota_update_in(Path(f"{stock_firmware_files_path}/ota_update.in"))

    # Move the files we don't need to modify to the new structure
    click.echo("Migrating unchanged stock files to destination structure")
    __migrate_firmware_files(stock_firmware_files_path, rooted_firmware_files_path)

    # End section
    click.echo()

    click.secho("Rooting Firmware", bold=True, underline=True)

    # Reassemble RootFS file from the parts
    click.echo("Assembling stock rootfs file")
    __assemble_rootfs(stock_firmware_files_path, True)

    click.echo("Extracting stock rootfs files")
    __unsquash_rootfs(Path(f"{stock_firmware_files_path}/rootfs.squashfs"), working_dir, True)

    click.echo("Customizing firmware with new password, helper script, and factory reset mechanism")
    PrepareRoot.customize_rootfs(
        Path(f"{working_dir}/squashfs-root/"),
        Path("assets/"),
        Path("templates/"),
        root_password_hash,
        board_name,
        rooted_version,
    )

    # End section
    click.echo()

    click.secho("Building Custom Firmware Image", bold=True, underline=True)

    click.echo("Creating new customized rootfs file")
    rooted_fs_stats = __squash_rooted_fs(working_dir, "squashfs-root", True)

    # Update the ota_update data with the new rootfs
    ota_update_data["rootfs"]["size"] = rooted_fs_stats["size"]
    ota_update_data["rootfs"]["md5"] = rooted_fs_stats["md5sum"]

    click.echo("Writing updated 'ota_update.in' file")
    OtaTools.write_ota_update_in(Path(f"{rooted_firmware_files_path}/ota_update.in"), rooted_version, ota_update_data)

    click.echo("Writing updated 'ota_config.in' file")
    OtaTools.write_ota_config_in(Path(f"{working_dir}/{rooted_firmware_basename}/ota_config.in"), rooted_version)

    click.echo("Splitting the custom rootfs into chunks")
    __split_rooted_fs(working_dir, rooted_firmware_files_path, rooted_fs_stats, True)

    click.echo("Creating custom firmware image file")
    with (
        py7zr.SevenZipFile(rooted_image_full_path, mode="w", password=image_password) as rooted_firmware_image,
        alive_bar(monitor=False, stats=False),
    ):
        rooted_firmware_image.set_encrypted_header(True)
        rooted_firmware_image.writeall(
            f"{working_dir}/{rooted_firmware_basename}", arcname=f"{rooted_firmware_basename}"
        )

    # End section
    click.echo()

    click.secho("Running Cleanup", bold=True, underline=True)
    click.echo("Removing working directory")
    shutil.rmtree(f"{working_dir}")

    # End section
    click.echo()

    click.echo(f"Saved custom firmware to {click.style(rooted_image_full_path, bold=True)}")


if __name__ == "__main__":
    main()
