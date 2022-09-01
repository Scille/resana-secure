# Parsec - Resana Secure version

## Submodules

- `modules/parsec-cloud` contains a copy (using git submodule) of the main Parsec reposity.

To update the Parsec subtree to a new version, set the modules/parsec-cloud repository to where you want it. Submodules act as a link.

```shell
cd modules/parsec-cloud
git fetch && # set to the version you want
cd ../..
git add modules/parsec-cloud
# Commit and push
```

## Release

### 1 - Generate a new release

On the master branch:

1) Modify version in renasa_secure/_version.py
2) Modify version in pyproject.toml
3) Create the release commit

```shell
git commit -a -m "Bump version $VERSION"
git push
```

Then wait for a green CI ;-)

### 2 - Create a tag and push it

```shell
git tag $VERSION -a -s -m "Release version $VERSION"
git push origin $VERSION
```

### 3 - Generate the installer

1) Download the artifact from the tag's CI run.
2) Extract the artifact output in `packaging/windows/build`
3) Run `make_installer.py`

```shell
pushd packaging/windows
# Ensure we are building from scratch !
rm -rf build
# <Extract the CI artifact>
# Sign the executable, generate the installer and sign it
set PATH=C:\Program Files (x86)\NSIS;%PATH%
set PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.18362.0\x64;%PATH%
python make_installer.py --sign-mode exe
```

### 3 - Create the release on Github

Once the tag pushed, it can be converted as a release on github using the
["Draft a new release"](https://github.com/Scille/resana-secure/releases) button.

/!\ Don't forget to check "This is a pre-release" if your creating a release candidate !
