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

    # Given `manifest.ini` is often generated on the CI, then consumed on a dev machine
    # to sign the release, we must provide paths as relative (given there is no guarantee
    # both machine will put the build at the same place).
    # However when running the build we'd rather work with absolute paths, so we patch
    # the file on the fly here !
    build_manifest = (BUILD_DIR / "manifest.ini").read_text()
    manifest_ini_need_path = False

    # 1) Patch `target`` field
    match = re.search(r"^target = \"(.*)\"$", build_manifest, re.MULTILINE)
    assert match, "`target` field not found in manifest.ini"
    maybe_relative_path = Path(match.group(1))
    if maybe_relative_path.is_absolute():
        freeze_program = maybe_relative_path
    else:
        manifest_ini_need_path = True
        freeze_program = BUILD_DIR / match.group(1)
    assert (
        freeze_program.exists()
    ), f"`target` field in manifest.ini point to an invalid path: `{freeze_program}`"
    build_manifest = (
        build_manifest[: match.start()]
        + 'target = "'
        + str(freeze_program.absolute())
        + build_manifest[match.end() - 1 :]
    )

    # 2) Patch `winfsp_installer_path`` field
    match = re.search(r"^winfsp_installer_path = \"(.*)\"$", build_manifest, re.MULTILINE)
    assert match, "`winfsp_installer_path` field not found in manifest.ini"
    maybe_relative_path = Path(match.group(1))
    if maybe_relative_path.is_absolute():
        winfsp_installer_path = maybe_relative_path
    else:
        manifest_ini_need_path = True
        winfsp_installer_path = BUILD_DIR / match.group(1)
    assert (
        winfsp_installer_path.exists()
    ), f"`winfsp_installer_path` field in manifest.ini point to an invalid path: `{winfsp_installer_path}`"
    build_manifest = (
        build_manifest[: match.start()]
        + 'winfsp_installer_path = "'
        + str(winfsp_installer_path.absolute())
        + build_manifest[match.end() - 1 :]
    )

    # 3) Finally overwrite the manifest (needed by `installer.nsi`)
    if manifest_ini_need_path:
        print("### Patching manifest.ini to turn paths absolute ###")
        (BUILD_DIR / "manifest.ini").write_text(build_manifest)

    if args.sign_mode == "none":
        print("### Building installer ###")
        run(f"makensis { BASE_DIR / 'installer.nsi' }")
        print("/!\\ Installer generated with no signature /!\\")
        (installer,) = BUILD_DIR.glob("resana_secure-*-setup.exe")
        print(f"{installer} is ready")
    else:
        assert which("signtool"), "signtool command not in PATH !"

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
