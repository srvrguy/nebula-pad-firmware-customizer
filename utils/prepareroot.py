# prepareroot.py
#
# Copyright (c) 2025 Michael Johnson
# All rights reserved.
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Licensed under the BSD 2-Clause "Simplified" License

"""Methods to prepare the custom root fs."""

import fileinput
import shutil
from datetime import datetime
from pathlib import Path
from string import Template


class PrepareRoot:
    """Class containing the methods to customize the root filesystem."""

    @staticmethod
    def __add_files(assets: Path, destination: Path) -> None:
        for file in assets.glob("**/*"):
            if file.is_file():
                shutil.copy(file, f"{destination}/{str(file).removeprefix('assets')}")

    @staticmethod
    def __set_password(rootfs_path: Path, root_password_hash: str) -> None:
        with fileinput.input(f"{rootfs_path}/etc/shadow", inplace=True) as shadow_file:
            for line in shadow_file:
                if line.startswith("root"):
                    auth_parts = line.split(":")
                    auth_parts[1] = root_password_hash
                    print(":".join(auth_parts), end="")
                else:
                    print(line, end="")

    @staticmethod
    def __fix_ota_info(template_path: Path, rootfs_path: Path, board_name: str, version: str) -> None:
        with open(f"{template_path}/ota_info.tmpl") as ota_info_template:
            ota_info = Template(ota_info_template.read())

        ota_info = ota_info.substitute(
            version=f"{version}",
            board_name=board_name,
            date=datetime.strftime(datetime.now(), "%Y %m.%d %H:%M:%S"),
        )

        with open(f"{rootfs_path}/etc/ota_info", "w") as ota_info_file:
            ota_info_file.write(ota_info)

    @staticmethod
    def customize_rootfs(
        rootfs_path: Path,
        assets_path: Path,
        template_path: Path,
        root_password_hash: str,
        board_name: str,
        version: str,
    ) -> None:
        """Do all the root filesystem customizations.

        :param rootfs_path: Path to the root filesystem.
        :param assets_path: Path to the assets folder.
        :param template_path: Path to the template folder.
        :param root_password_hash: Hashed root password in crypt(1) format.
        :param board_name: The name of the bozrd, as Creality defines it.
        :param version: Version of the root filesystem.
        """
        # Update the "ota_info" file with the new custom values
        PrepareRoot.__fix_ota_info(template_path, rootfs_path, board_name, version)

        # Copy in the additional assets
        PrepareRoot.__add_files(assets_path, rootfs_path)

        # Set the new root password
        PrepareRoot.__set_password(rootfs_path, root_password_hash)
