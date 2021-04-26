# Resana Secure (https://parsec.cloud) Copyright (c) 2021 Scille SAS

import re
import argparse
import itertools
import subprocess
from shutil import which
from pathlib import Path


SIGNATURE_AUTHOR = "Scille"
SIGNATURE_DESCRIPTION = f"Resana Secure by {SIGNATURE_AUTHOR}"


BUILD_DIR = Path("build").resolve()
if not which("makensis"):
    raise RuntimeError("makensis command not in PATH !")
if not which("signtool"):
    raise RuntimeError("signtool command not in PATH !")


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

    if args.sign_mode == "none":
        print("### Building installer ###")
        run(f"makensis { BUILD_DIR / 'installer.nsi' }")
        print("/!\\ Installer generated with no signature /!\\")
        installer, = BUILD_DIR.glob("resana_secure-*-setup.exe")
        print(f"{installer} is ready")

    else:
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
        run(f"makensis { BUILD_DIR / 'installer.nsi' }")
        # Sign installer
        print("### Signing installer ###")
        installer, = BUILD_DIR.glob("resana_secure-*-setup.exe")
        sign(installer)
        print(f"{installer} is ready")
