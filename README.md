# Parsec - Resana Secure repository

## Modules

- `client` contains the resana-secure client
- `server` contains different modules used for the server (antivirus-connector, IP filtering, ...)

Separation is made because `client` relies heavily on `parsec-cloud` (and has the project as a submodule) while `server` can use the version on pypi.
