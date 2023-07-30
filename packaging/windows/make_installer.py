# Resana Secure (https://parsec.cloud) Copyright (c) 2021 Scille SAS

import argparse
import itertools
import re
import subprocess
from pathlib import Path
from shutil import which

SIGNATURE_AUTHOR = "Scille"
SIGNATURE_DESCRIPTION = f"Resana Secure by {SIGNATURE_AUTHOR}"

BASE_DIR = Path(__name__).resolve().parent

BUILD_DIR = Path("build").resolve()


def run(cmd, **kwargs):
    print(f">>> {cmd}")
    ret = subprocess.run(cmd, shell=True, **kwargs)
    ret.check_returncode()
    return ret


def is_signed(target):
    ret = subprocess.run(["signtool", "verify", "/pa", str(target)], capture_output=True)
    return ret.returncode == 0


def sign(target):
    run(
        f'signtool sign /n "{SIGNATURE_AUTHOR}" /t http://time.certum.pl /fd sha256 /d "{SIGNATURE_DESCRIPTION}" /v {target}'
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build&sign Resana Secure installer")
    parser.add_argument(
        "--sign-mode", choices=("all", "exe", "none"), default="none", type=lambda x: x.lower()
    )
    args = parser.parse_args()

    assert which("makensis"), "makensis command not in PATH !"

    if args.sign_mode == "none":
        print("### Building installer ###")
        run(f"makensis { BASE_DIR / 'installer.nsi' }")
        print("/!\\ Installer generated with no signature /!\\")
        (installer,) = BUILD_DIR.glob("resana_secure-*-setup.exe")
        print(f"{installer} is ready")

    else:
        assert which("signtool"), "signtool command not in PATH !"

        build_manifest = (BUILD_DIR / "manifest.ini").read_text()
        match = re.match(r"^target = \"(.*)\"$", build_manifest, re.MULTILINE)
        if not match:
            raise SystemExit("Build manifest not found, aborting")
        freeze_program = Path(match.group(1))
        # Retrieve frozen program and sign all .dll and .exe
        print("### Signing application executable ###")
        sign(freeze_program / "resana_secure.exe")
        # Make sure everything is signed
        if args.sign_mode == "all":
            print("### Checking all shipped exe/dll are signed ###")
            not_signed = []
            for file in itertools.chain(
                freeze_program.rglob("*.exe"), freeze_program.rglob("*.dll")
            ):
                if not is_signed(file):
                    not_signed.append(file)
                    print("Unsigned file detected:", file)
            if not_signed:
                raise SystemExit("Some file are not signed, aborting")
        # Generate installer
        print("### Building installer ###")
        run(f"makensis { BASE_DIR / 'installer.nsi' }")
        # Sign installer
        print("### Signing installer ###")
        (installer,) = BUILD_DIR.glob("resana_secure-*-setup.exe")
        sign(installer)
        print(f"{installer} is ready")
