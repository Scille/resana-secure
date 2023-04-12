#! /usr/bin/env python3

import argparse
import re


def main(pathfile: str) -> None:
    is_python = False
    is_rust = False
    if re.match("^.*poetry.lock$", pathfile):
        is_python = True
    elif re.match("^.*Cargo.lock$", pathfile):
        is_rust = True
    else:
        print("Only poetry.lock and Cargo.lock files are accepted")
        return

    with open(pathfile, mode="r") as file:
        filename_output = "pip_package_list.txt" if is_python else "rust_package_list.txt"
        with open(filename_output, mode="w") as output:
            content = "".join(file.readlines())
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
                        if is_python:
                            output.write(f"PIP:{package}|{version}\n")
                        if is_rust:
                            output.write(f"RUST:{package}|{version}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    main(args.filename)
