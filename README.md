# Creality Nebula Pad Firmware Rooting Tool

This tool creates a root-enabled firmware image for the Creality Nebula Pad.

> [!CAUTION]
> 3D FDM printers involve high temperatures, molten plastic, and electricity. Modifications may not only break your
> printer but may cause damage, personal harm, or death. Creating, installing, and/or using custom firmware is at your
> own risk.

## Acknowledgements

This tool is based on [the script created by Koen Erens](https://github.com/koen01/nebula_firmware) which is based on
the [custom firmware script created by Jason Pell](https://github.com/pellcorp/creality/tree/main/firmware).

## Prerequisites

You can use the development container in this project to run the script. It contains all the needed prerequisites for
the tool to function. If you choose to use it, you don't need to read further in this section.

If you want to run the tool locally,  it _must_ be run on a Linux-style system to properly preserve the
permissions of the files it is editing. It should work fine on Linux, macOS, or using WSL.

This tool also requires the system to have [squashfs-tools](https://github.com/plougher/squashfs-tools) installed for
the `mksquashfs` and `unsquashfs` commands. Most Linux systems should have these available to install via the system's
package system. For macOS, you can install `squashfs` via Homebrew.

You should also have [uv](https://docs.astral.sh/uv/) installed, as it's used to manage the dependencies and running of
this patcher.

## Using the Tool

Using the tool is very straightforward. Once you download it and have the prerequisites installed, you can just run
`uv run main.py` to have the tool patch the default firmware version and set the root ssh user password to "creality".
If you want to see the options you can set just add `--help` at the end of the command.

## Why this Tool? Why Python?

While there is a shell script that works perfectly fine, I wanted to gain a deeper understanding of how the update
images are put together. I also wanted to be able to customize a few things, like allowing a custom password to be set
without having to manually generate the hash beforehand. Python was a good candidate for these plans as almost
everything needed was available as a Python module, which greatly reduced the effort in setup. It's also a much easier
language to do complex things in and still have it be maintainable.

## License

While I can't claim this is a fully original work, anything I do have copyright to is licensed under the
[Simplified BSD License](https://opensource.org/license/bsd-2-clause).
