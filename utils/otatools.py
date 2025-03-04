# otatools.py
#
# Copyright (c) 2025 Michael Johnson
# All rights reserved.
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Licensed under the BSD 2-Clause "Simplified" License

"""Methods to update the various 'ota' files in the firmware."""

from pathlib import Path


class OtaTools:
    """Static methods that update/modify the various 'ota' files."""

    @staticmethod
    def parse_ota_update_in(ota_file_location: Path) -> dict[dict[str, str]]:
        """Parse an existing 'ota_update.in' file into a nested dict."""
        # The ota_update.in file format is documented at
        # http://docs.ingenic.com.cn/platforms/darwin/01LINUX开发平台/05AdvancedModule/009OTA升级/001双系统OTA升级/#2-编译-ota-升级包固件
        # which is only available in Chinese.
        #
        # The format of the ota_update.in file is pseudo-ini and each section is separated by a blank line.
        # Keys are repeated in each section.
        #
        # The file begins with key "ota_version" which should match the other version strings in the update archive and
        # is used as a sanity check.
        #
        # Each following section is a partition that has an "update" with the following keys:
        # - img_type: The partition to update
        # - img_name: The base file name containing the contents for that partition
        # - img_size: The total size in bytes of the unsplit file.
        # - img_md5:  An MD5 hash of the unsplit file, used to verify no corruption.

        # Read the stock unmodified file and break it into sections.
        raw_contents = Path(ota_file_location).read_text().strip().split("\n\n")

        parsed = dict()

        for section in raw_contents:
            contents = section.splitlines()

            if len(contents) > 1:
                section = dict()

                for line in contents:
                    entry = line.split("=")
                    section[entry[0].removeprefix("img_")] = entry[1]

                parsed[section["type"]] = section

        return parsed

    @staticmethod
    def write_ota_update_in(ota_file_location: Path, ota_version: str, ota_info: dict[dict[str, str]]) -> None:
        """Write out an 'ota_update.in' file given the needed info."""
        with open(ota_file_location, "w") as ota_update_file:
            ota_update_file.write(f"ota_version={ota_version}\n")
            ota_update_file.write("\n")

            for section in ota_info:
                ota_update_file.write(
                    f"img_type={ota_info[section]['type']}\n"
                    f"img_name={ota_info[section]['name']}\n"
                    f"img_size={ota_info[section]['size']}\n"
                    f"img_md5={ota_info[section]['md5']}\n"
                    "\n"
                )

    @staticmethod
    def write_ota_config_in(ota_file_location: Path, ota_version) -> None:
        """Write out an 'ota_config.in' file."""
        with open(ota_file_location, "w") as ota_config_file:
            ota_config_file.write(f"current_version={ota_version}\n")
