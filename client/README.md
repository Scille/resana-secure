# Parsec - Resana Secure version

## Submodules

- `submodules/parsec-cloud` contains a copy (using git submodule) of the main Parsec repository.

To update the Parsec submodule to a new version, set the submodules/parsec-cloud repository to where you want it. Submodules act as a link.

```shell
cd submodules/parsec-cloud
# set to the version you want
cd ../..
git add submodules/parsec-cloud
# Commit and push
```

## Release

### 1 - Generate a new release

Make a release branch from `master`:
```shell
git checkout master
git pull
git checkout -b releases/MAJOR.MINOR.PATCH
```

1) Modify version in `resana_secure/_version.py`
2) Modify version in `packaging/snap/snap/snapcraft.yaml`
3) Modify version in `pyproject.toml`
4) Create the release commit

```shell
git commit -a -m "Bump version $VERSION"
git push
```

Then make the corresponding PR and wait for a green CI ;-)

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

### 4 - Test the installer

Install the .exe and start Resana.

Launch the script `test_routes.py` to test the endpoints. For example:

```shell
> python packing/test_routes.py -p parsec://localhost:6888?no_ssl=true -o TestOrg
INFO:test-resana:Bootstraping using `parsec://localhost:6888/TestOrg?no_ssl=true&action=bootstrap_organization`
INFO:test-resana:Authenticating...
INFO:test-resana:[OK] Listing invitations
INFO:test-resana:[OK] Inviting user
INFO:test-resana:[OK] Checking if the new invitation appears
INFO:test-resana:[OK] Claimer retrieve info
INFO:test-resana:[OK] Greeter wait
INFO:test-resana:[OK] Claimer wait
INFO:test-resana:[OK] Greeter wait peer trust
INFO:test-resana:[OK] Claimer check trust
INFO:test-resana:[OK] Greeter check trust
INFO:test-resana:[OK] Claimer wait peer trust
INFO:test-resana:[OK] Claimer finalize
INFO:test-resana:[OK] Greeter finalize
INFO:test-resana:[OK] List users to see new user
INFO:test-resana:[OK] List workspaces
INFO:test-resana:[OK] Adding a new workspace
INFO:test-resana:[OK] List workspace to check that we have one
INFO:test-resana:[OK] Rename the workspace
INFO:test-resana:[OK] Check that the workspace was renamed
INFO:test-resana:[OK] Get the sharing info
INFO:test-resana:[OK] Share the workspace
INFO:test-resana:[OK] Check that the workspace has been shared
INFO:test-resana:[OK] Update role
INFO:test-resana:[OK] Check that role has been updated
INFO:test-resana:[OK] Unshare the workspace
INFO:test-resana:[OK] Make sure that the workspace is no longer shared with bob
INFO:test-resana:[OK] List workspaces
INFO:test-resana:[OK] List folders
INFO:test-resana:[OK] Create a folder
INFO:test-resana:[OK] Check new folder created
INFO:test-resana:[OK] Upload a new file
INFO:test-resana:[OK] Make sure the file appears
INFO:test-resana:[OK] Rename the file
INFO:test-resana:[OK] Make sure the file was renamed
INFO:test-resana:[OK] Delete the file
INFO:test-resana:[OK] Make sure the file was deleted
INFO:test-resana:[OK] List users
INFO:test-resana:[OK] Revoke second user
INFO:test-resana:[OK] Make sure that user was revoked
```

### 5 - Create the release on Github

Once the tag pushed, it can be converted as a release on github using the
["Draft a new release"](https://github.com/Scille/resana-secure/releases) button.

/!\ Don't forget to check "This is a pre-release" if your creating a release candidate !

### 4 - Merge the PR

Merge the PR once the last release for this version has been created.
