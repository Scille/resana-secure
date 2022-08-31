import re

VERSION_FILE = "modules/parsec-cloud/parsec/_version.py"

def patch_version():
    lines = []

    with open(VERSION_FILE, "r") as fd:
        lines = fd.readlines()

    new_lines = []
    for line in lines:
        if line.startswith("__version__ = "):
            line = line[:-1]
            m = re.search(r'__version__ = "(v\d{1,2}\.\d{1,2}\.\d{1,2})(?:\+[a-z]+)?"', line)
            assert m is not None
            assert len(m.groups()) == 1
            new_lines.append(f'__version__ = "{m.group(1)}+resana"\n')
        else:
            new_lines.append(line)
    content = "".join(new_lines)
    with open(VERSION_FILE, "w+") as fd:
        fd.write(content)


if __name__ == "__main__":
    patch_version()