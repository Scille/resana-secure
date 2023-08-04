# Resana Secure (https://parsec.cloud) Copyright (c) 2021 Scille SAS

import argparse
import os
import platform
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

BUILD_DIR = Path("build").resolve()

WINFSP_URL = "https://github.com/billziss-gh/winfsp/releases/download/v1.8/winfsp-1.8.20304.msi"
WINFSP_HASH = "8d6f2c519f3f064881b576452fbbd35fe7ad96445aa15d9adcea1e76878b4f00"
TOOLS_VENV_DIR = BUILD_DIR / "tools_venv"
PYINSTALLER_VENV_DIR = BUILD_DIR / "pyinstaller_venv"
WHEELS_DIR = BUILD_DIR / "wheels"

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
PYTHON_EXECUTABLE = sys.executable


def get_archslug():
    bits, _ = platform.architecture()
    return "win32" if bits == "32bit" else "win64"


def run(cmd, **kwargs):
    print(f">>> {cmd}")
    # Need to flush stdout & stderr before executing the command to have the output correctly ordered
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_call(cmd, shell=True, **kwargs)


def main(program_source: Path):
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"### Detected Python version {PYTHON_VERSION} ###")

    # Retrieve program version
    global_dict: dict[str, str] = {}
    exec((program_source / "resana_secure/_version.py").read_text(), global_dict)
    program_version = global_dict.get("__version__")
    print(f"### Detected Resana Secure version {program_version} ###")

    winfsp_installer = BUILD_DIR / WINFSP_URL.rsplit("/", 1)[1]
    if not winfsp_installer.is_file():
        print("### Fetching WinFSP installer (will be needed by NSIS packager later) ###")
        req = urlopen(WINFSP_URL)
        data = req.read()
        assert sha256(data).hexdigest() == WINFSP_HASH
        winfsp_installer.write_bytes(data)

    # It's complicated to control the virtualenv's path when using Poetry.
    # Instead we manually create the virtualenv, install Poetry inside it, then
    # use Poetry to install Parsec and dependencies

    # Bootstrap tools virtualenv
    if not TOOLS_VENV_DIR.is_dir():
        print("### Create tool virtualenv ###")
        run(f"python -m venv {TOOLS_VENV_DIR}")
        run(f"{ TOOLS_VENV_DIR / 'Scripts/python' } -m pip install pip --upgrade")
        run(f"{ TOOLS_VENV_DIR / 'Scripts/python' } -m pip install poetry --upgrade")

    # Bootstrap PyInstaller virtualenv
    if not PYINSTALLER_VENV_DIR.is_dir():
        print(
            "### Installing Resana Secure, Parsec, dependencies & PyInstaller in temporary virtualenv ###"
        )
        run(f"{ PYTHON_EXECUTABLE } -m venv {PYINSTALLER_VENV_DIR}")

    run(
        f"{ TOOLS_VENV_DIR.absolute() / 'Scripts/python' } -m poetry install --with=packaging --no-interaction",
        cwd=program_source.absolute(),
        env={
            **os.environ,
            "VIRTUAL_ENV": str(PYINSTALLER_VENV_DIR.absolute()),
            "POETRY_VIRTUALENVS_PATH": str(PYINSTALLER_VENV_DIR.absolute()),
        },
    )

    pyinstaller_build = BUILD_DIR / "pyinstaller_build"
    pyinstaller_dist = BUILD_DIR / "pyinstaller_dist"
    if not pyinstaller_dist.is_dir():
        print("### Use Pyinstaller to generate distribution ###")
        spec_file = Path(__file__).joinpath("..", "pyinstaller.spec").resolve()
        run(
            f"{ PYINSTALLER_VENV_DIR / 'Scripts/python' } -m PyInstaller {spec_file} --distpath {pyinstaller_dist} --workpath {pyinstaller_build}"
        )

    target_dir = BUILD_DIR / f"resana_secure-{program_version}-{get_archslug()}"
    if target_dir.exists():
        raise SystemExit(f"{target_dir} already exists, exiting...")
    shutil.move(pyinstaller_dist / "resana_secure", target_dir)

    # # Include LICENSE file
    # # (target_dir / "LICENSE.txt").write_text((program_source / "LICENSE").read_text())

    # Create build info file for NSIS installer
    # Path must be provided relative, otherwise we cannot generate this on the CI and
    # run the `make_installer.py` on dev machine (required to have the installer&binary signed)
    (BUILD_DIR / "manifest.ini").write_text(
        f'target = "{target_dir.relative_to(BUILD_DIR)}"\n'
        f'program_version = "{program_version}"\n'
        f'python_version = "{PYTHON_VERSION}"\n'
        f'platform = "{get_archslug()}"\n'
        f'winfsp_installer_name = "{winfsp_installer.name}"\n'
        f'winfsp_installer_path = "{winfsp_installer.relative_to(BUILD_DIR)}"\n'
    )

    # Create the install and uninstall file list for NSIS installer
    target_files = []

    def _recursive_collect_target_files(curr_dir):
        subdirs = []
        for entry in curr_dir.iterdir():
            if entry.is_dir():
                subdirs.append(entry)
            else:
                target_files.append((False, entry.relative_to(target_dir)))
        for subdir in subdirs:
            target_files.append((True, subdir.relative_to(target_dir)))
            _recursive_collect_target_files(subdir)

    _recursive_collect_target_files(target_dir)

    install_files_lines = ["; Files to install", 'SetOutPath "$INSTDIR\\"']
    curr_dir = Path(".")
    for target_is_dir, target_file in target_files:
        if target_is_dir:
            install_files_lines.append(f'SetOutPath "$INSTDIR\\{target_file}"')
            curr_dir = target_file
        else:
            assert curr_dir == target_file.parent
            install_files_lines.append(f'File "${{PROGRAM_FREEZE_BUILD_DIR}}\\{target_file}"')
    (BUILD_DIR / "install_files.nsh").write_text("\n".join(install_files_lines))

    uninstall_files_lines = ["; Files to uninstall"]
    for target_is_dir, target_file in reversed(target_files):
        if target_is_dir:
            uninstall_files_lines.append(f'RMDir "$INSTDIR\\{target_file}"')
        else:
            uninstall_files_lines.append(f'Delete "$INSTDIR\\{target_file}"')
    (BUILD_DIR / "uninstall_files.nsh").write_text("\n".join(uninstall_files_lines))


def check_python_version():
    if PYTHON_VERSION == "3.7.7":
        raise RuntimeError(
            "CPython 3.7.7 is broken for packaging (see https://bugs.python.org/issue39930)"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freeze Resana Secure")
    parser.add_argument("program_source", type=Path)
    parser.add_argument("--disable-check-python", action="store_true")
    args = parser.parse_args()
    if not args.disable_check_python:
        check_python_version()
    main(args.program_source)
