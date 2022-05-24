# Parsec - Resana Secure version

## Subtree

- `subtree/parsec-cloud` contains a copy (using git subtree) of the main Parsec reposity.
- `subtree/parsec-cloud/parsec/_version.py` has been modified to add the `+resana` suffix

To update the Parsec subtree to a new version:

.. code-block:: shell

    git subtree pull --squash --prefix='subtree/parsec-cloud' -- 'git@github.com:Scille/parsec-cloud.git' $VERSION
    git subtree pull --squash --prefix='subtree/parsec-extensions' -- 'git@github.com:vxgmichel/parsec-extensions.git' $VERSION

## Release

### 1 - Generate a new release

.. code-block:: shell

    # 1) Modify version in renasa_secure/_version.py
    # 2) Modify version in pyproject.toml
    # 3) git commit -a -m "Bump version $VERSION"

    pushd packaging/win32
    # Ensure we are building from scratch !
    rm -rf build
    # Note the release will use the Python version used to run the script
    "C:\Users\gbleu\AppData\Local\Programs\Python\Python39\python.exe" freeze_program.py ../..
    # Sign the executable, generate the installer and sign it
    set PATH=C:\Program Files (x86)\NSIS;%PATH%
    set PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.18362.0\x64;%PATH%
    python make_installer.py --sign-mode exe

### 2 - Create a tag and push it

.. code-block:: shell

    git tag $VERSION -a -s -m "Release version $VERSION"
    git push origin $VERSION

### 3 - Create the release on Github

Once the tag pushed, it can be converted as a release on github using the
["Draft a new release"](https://github.com/Scille/resana-secure/releases) button.

/!\ Don't forget to check "This is a pre-release" if your creating a release candidate !
