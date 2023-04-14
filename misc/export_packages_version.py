#! /usr/bin/env python3
"""
Export packages versions from a "poetry.lock" or "Cargo.lock" file
"""

import argparse
import re
import sys

PYTHON_PREFIX = "PIP"
PYTHON_OUTPUT = "pip_package_list.txt"

RUST_PREFIX = "RUST"
RUST_OUTPUT = "rust_package_list.txt"


def main(pathfile: str) -> None:
    if re.match("^.*poetry.lock$", pathfile):
        output, prefix = PYTHON_OUTPUT, PYTHON_PREFIX
    elif re.match("^.*Cargo.lock$", pathfile):
        output, prefix = RUST_OUTPUT, RUST_PREFIX
    else:
        sys.exit("Error: Only 'poetry.lock' and 'Cargo.lock' files are accepted")

    export_package_versions(pathfile, output, prefix)


def export_package_versions(filename_lock: str, filename_output: str, prefix: str) -> None:
    with open(filename_lock, mode="r", encoding="utf8") as lockfile:
        with open(filename_output, mode="w", encoding="utf8") as output:
            content = "".join(lockfile.readlines())
            sections = content.split("\n\n")
            package_regex = re.compile(
                '^.*name = "(?P<package>.*)"\nversion = "(?P<version>.*)".*$', re.MULTILINE
            )
            for section in sections:
                if section.startswith("[[package]]"):
                    m = package_regex.search(section)
                    if m:
                        package = m.group("package")
                        version = m.group("version")
                        output.write(f"{prefix}:{package}|{version}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="a 'poetry.lock' or 'Cargo.lock' file")
    args = parser.parse_args()

    main(args.filename)
