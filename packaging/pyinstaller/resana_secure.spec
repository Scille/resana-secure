# Resana Secure Copyright (c) 2021 Scille SAS

import os
from pathlib import Path
from importlib.resources import contents, is_resource
from importlib.util import find_spec


# Cannot use __file__ given we are not in a real .py file
BASEDIR = Path(os.path.abspath(""))


# In all it zeal, Pyinstaller finds itself very smart by not including
# resource data (i.e. non-python files contained within a python package).
# So we have to manually retreive those resource data and explicitly
# tell Pyinstaller it has to ship them...


def collect_package_datas(package_name):
    datas = []
    package_path = Path(find_spec(package_name).submodule_search_locations[0])
    ignored_extensions = {"py", "pyc", "pyo", "pyd"}

    def _collect_recursive(subpackage_stems):
        subpackage_name = ".".join(subpackage_stems)
        for entry_name in contents(subpackage_name):
            if is_resource(subpackage_name, entry_name):
                if '.' not in entry_name or entry_name.rsplit('.', 1)[1] not in ignored_extensions:
                    datas.append(
                        (
                            str(
                                package_path.joinpath(*subpackage_stems[1:], entry_name)
                            ),
                            "/".join(subpackage_stems),
                        )
                    )
            else:
                _collect_recursive([*subpackage_stems, entry_name])

    _collect_recursive([package_name])
    return datas


block_cipher = None


a = Analysis(
    ["launch_script.py"],
    pathex=[str(BASEDIR)],
    binaries=[],
    datas=[
        *collect_package_datas("parsec"),
        *collect_package_datas("resana_secure"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="resana_secure",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon="./icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="resana_secure",
)
