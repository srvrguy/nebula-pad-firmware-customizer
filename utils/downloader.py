# downloader.py
#
# Copyright (c) 2025 Michael Johnson
# All rights reserved.
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Licensed under the BSD 2-Clause "Simplified" License

"""Creality Nebula Pad Firmware Downloader."""

import urllib.parse
from pathlib import Path

import requests
import re
from lxml import html
from alive_progress import alive_bar


class Downloader:
    """Firmware Downloader."""

    @staticmethod
    def __get_download_link(version: str) -> str:
        """Try to parse the Creality website to find the download link for the firmware image.

        :param version: The version of the firmware to download without the leading "V".
        :return: The download link for the firmware.
        """
        try:
            # Parse download page to get link
            url = "https://www.creality.com/pages/download-creality-nebula-smart-kit"

            response = requests.get(url)
        except requests.exceptions.RequestException as e:
            raise e

        tree = html.fromstring(response.content)

        # Test by extracting 1.1.0.27
        refs = tree.xpath(f"//a[contains(@href, 'NEBULA_ota') and contains(@href, '{version}')]")

        if len(refs) == 1:
            firmware_url = refs[0].get("href")
        else:
            raise RuntimeError(f"Could not find a download link for version {version}")

        return firmware_url

    @staticmethod
    def __download_firmware(url: str, output_dir: Path) -> None:
        """Given a URL, download the contents while displaying the progress.

        :param url: The URL of the firmware to download.
        :param output_dir: The directory to place the downloaded file.
        :return: None
        """
        file = requests.get(url, stream=True)
        total_size = int(file.headers.get("content-length", 0))
        block_size = 1024  # Download block size in bytes

        # Make the destination directory. Create any parents, if needed. If the directory already exists, don't error.
        output_dir.mkdir(parents=True, exist_ok=True)

        # Try to get the desired filename from the response. If not, parse from the URL.
        if "Content-Disposition" in file.headers.keys():
            output_file_name = urllib.parse.unquote(
                re.findall(r'filename="(.+?)"', file.headers["Content-Disposition"])[0]
            )
        else:
            output_file_name = url.split("/")[-1]

        with (
            open(f"{output_dir}/{output_file_name}", "wb") as firmware_image,
            alive_bar(total=total_size, scale="IEC", unit="B") as bar,
        ):
            for data in file.iter_content(block_size):
                bar(len(data))
                firmware_image.write(data)

    @staticmethod
    def download_firmware(version: str, output_dir: Path) -> None:
        """Download the requested firmware version from the Creality website.

        :param version: The version of the firmware to download.
        :param output_dir: The directory to place the downloaded file.
        :return: None
        """
        Downloader.__download_firmware(Downloader.__get_download_link(version), output_dir)
