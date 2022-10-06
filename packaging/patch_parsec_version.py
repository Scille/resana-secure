import re


VERSION_FILE = "modules/parsec-cloud/parsec/_version.py"


def patch_version():
    lines = []

    with open(VERSION_FILE, "r") as fd:
        lines = fd.readlines()

    new_lines = []
    version_line_found = False
    for line in lines:
        match = re.search(r'__version__\W=\W"(.*)"', line)
        if match:
            version_line_found = True
            new_lines.append(f'__version__ = "{match.group(1)}+resana"\n')
        else:
            new_lines.append(line)
    assert version_line_found
    content = "".join(new_lines)
    with open(VERSION_FILE, "w+") as fd:
        fd.write(content)


if __name__ == "__main__":
    patch_version()
