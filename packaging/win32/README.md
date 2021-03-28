NSIS installer for Resana Secure
================================

Inspired by (Deluge NSIS installer)[https://github.com/deluge-torrent/deluge/blob/3f9ae337932da550f2623daa6dedd9c3e0e5cfb3/packaging/win32/Win32%20README.txt]


Build steps
-----------


### 1 - Build the application

First make sure you are within a cmd.exe shell with visual studio configured
for the target architecture you want to build.

Example for Visual Studio 2017 with amd64 target:
```shell
$ "C:\Program Files (x86)\Microsoft Visual Studio\2017\Community\VC\Auxiliary\Build\vcvarsall.bat"  amd64
```

Run the `freeze_program.py` Python script with the path to the Resana Secure sources to use:
```shell
$ python freeze_program.py ../..
```

Note the Python version embedded inside the build will be taken from the interpreter
you run the script with.
For this reason, you must run the script with a Python interpreter of the same
architecture than the one configured for visual studio.

On top of the build, the script will generate `install_files.nsh`, `uninstall_files.nsh`
and `BUILD.tmp` files that will be used by the packaging nsis script.


### 2 - Package the application

First download WinFSP installer that will be packaged in the installer:
```shell
$ curl -L https://github.com/billziss-gh/winfsp/releases/download/v1.7/winfsp-1.7.20172.msi -o winfsp-1.7.20172.msi
```

Run the NSIS script `installer.nsi`:
```shell
$ "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
```

This will generate a `build\resana_secure-<version>-<platform>-setup.exe` installer.


### 3 - Sign the application

Those instructions are depending on the certificate method we are using at the Parsec team, hence they are incomplete.

#### Install signtool
The `signtool` command is part of the Windows SDK : https://developer.microsoft.com/en-us/windows/downloads/windows-10-sdk/

#### Add signtool to path
Can be done for example doing ```@set PATH=C:\Program Files (x86)\Windows Kits\10\bin\$VERSION\x64;%PATH%```

#### Sign an executable
```signtool sign /n Scille /t http://time.certum.pl /fd sha256 /d "Resana Secure by Scille" /v $EXECUTABLE```
