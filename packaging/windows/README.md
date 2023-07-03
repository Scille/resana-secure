NSIS installer for Resana Secure
================================

Inspired by (Deluge NSIS installer)[https://github.com/deluge-torrent/deluge/blob/3f9ae337932da550f2623daa6dedd9c3e0e5cfb3/packaging/win32/Win32%20README.txt]


Build steps
-----------


### 1 - Build the application

Run the `freeze_program.py` Python script with the path to the Resana Secure sources to use:
```shell
python freeze_program.py ../../client
```

Note the Python version embedded inside the build will be taken from the interpreter
you run the script with.

On top of the build, the script will generate `install_files.nsh`, `uninstall_files.nsh`
and `manifest.ini` files that will be used by the packaging nsis script.
It will also download a WinFSP installer which is also needed by the packaging nsis script.


### 2 - Package the application

#### Install dependencies

Under the hood, the packaging script uses `makensis` and `signtool` commands.

The `makensis` command is part of NSIS: https://nsis.sourceforge.io/Main_Page
The `signtool` command is part of the Windows SDK : https://developer.microsoft.com/en-us/windows/downloads/windows-10-sdk/

On top of that, make sure they are in your `PATH` before running the script:

```shell
$ set PATH=C:\Program Files (x86)\NSIS;%PATH%
$ set PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.18362.0\x64;%PATH%
```

#### Run the packaging script

Run the `make_installer.py` Python script:
```shell
$ python make_installer.py --sign-mode=exe
```
