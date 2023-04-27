# Parsec - Resana Secure repository

## Modules

- `client` contains the resana-secure client
- `server` contains different modules used for the server (antivirus-connector, IP filtering, ...)

Separation is made because `client` relies heavily on `parsec-cloud` (and has the project as a submodule) while `server` can use the version on pypi.

## Development

### Developing client side

First the submodule needs to be set as a python package

```shell
git submodule update --init --recursive
```

Then,

```shell
poetry shell
poetry install
```

Make sure you have a matching python version, if not install it through `pyenv`.

The `run_testenv` script from Parsec can be used to set a local backend for testing within the `client` directory.

From `/client`, in `/submodules/parsec-cloud`:

Install dependencies for the script:

```shell
poetry install -E core -E backend
```

then,

On Windows:

```shell
./tests/scripts/run_testenv.bat
```

On Linux and MacOS:

```shell
source ./tests/scripts/run_testenv.sh
```

The client can then be launched

```shell
RESANA_DEBUG_GUI=true python -m resana_secure --config $XDG_CONFIG_HOME/parsec --rie-server-addr localhost:6888
```

`XDG_CONFIG_HOME` is generated with the `run_testenv` script, and `RESANA_DEBUG_GUI` enables the (small but functional) GUI to easily log in and log out devices.

The available routes can be found in the [api.md](https://github.com/Scille/resana-secure/blob/master/client/api.md) file, and can be called with commands such as:

```shell
curl -X POST http://127.0.0.1:5775/auth -H 'Content-Type: application/json' -d '{"email":"alice@example.com","key":"test"}'
```
or
```shell
curl -X GET http://127.0.0.1:5775/workspaces -H "Authorization: Bearer <AUTH_ID>"
```
