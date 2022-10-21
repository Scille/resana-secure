import click
import os
from typing import Optional, Tuple, List
from pathlib import Path
from functools import partial
import sys
import logging
import structlog
import trio_asyncio
import oscrypto.asymmetric

from parsec.api.protocol import OrganizationID
from parsec.backend.config import BaseBlockStoreConfig
from parsec.backend.blockstore import PostgreSQLBlockStoreConfig
from parsec.backend.cli.utils import _parse_blockstore_params

from .app import serve_app, AppConfig
from ._version import __version__


logger = structlog.get_logger()


def _setup_logging(log_level: str, log_file: Optional[Path]) -> None:
    # The infamous logging configuration...

    def _structlog_renderer(_, __, event_dict):
        event = event_dict.pop("event", "")
        if event_dict:
            args = ", ".join(f"{k}: {repr(v)}" for k, v in event_dict.items())
            return f"{event} ({args})"
        else:
            return event

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _structlog_renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    format = "%(asctime)s %(levelname)s %(name)s - %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"
    level = getattr(logging, log_level)
    if log_file:
        log_file.parent.mkdir(exist_ok=True, parents=True)
        logging.basicConfig(format=format, datefmt=datefmt, filename=log_file, level=level)
    else:
        logging.basicConfig(format=format, datefmt=datefmt, stream=sys.stdout, level=level)


def _parse_sequester_service_private_key_param(
    param: str,
) -> Tuple[OrganizationID, oscrypto.asymmetric.PrivateKey]:
    try:
        raw_id, raw_pem = param.split(":", 1)
        organization_id = OrganizationID(raw_id)
    except ValueError:
        # We absolutely want to avoid leaking the key with a potentially uncatched exception
        raise SystemExit(
            "Invalid --sequester-service-private-key, expected format `<sequester_id>:<pem_key>`"
        )

    # Good enough check to make sure that the key is a RSA key in a PEM format
    if "-----BEGIN RSA PRIVATE KEY-----" not in raw_pem:
        raise SystemExit(
            "Invalid --sequester-service-private-key, missing PEM RSA header for key part"
        )

    try:
        # `oscrypto.asymmetric.load_private_key` treats argument as a file if its type is str and
        # as the raw key if it's bytes, hence the encode.
        service_private_key = oscrypto.asymmetric.load_private_key(raw_pem.encode())
    except Exception:
        # We absolutely want to avoid leaking the key with a potentially uncatched exception
        raise SystemExit("Invalid --sequester-service-private-key, failed to load key part")

    return organization_id, service_private_key


@click.command(short_help="Runs the antivirus connector")
@click.option("--port", type=int, default=5775, envvar="ANTIVIRUS_CONNECTOR_PORT")
@click.option("--host", default="127.0.0.1", envvar="ANTIVIRUS_CONNECTOR_HOST")
@click.option(
    "--client-origin",
    type=lambda x: x.split(";"),
    default="*",
    envvar="ANTIVIRUS_CONNECTOR_CLIENT_ORIGIN",
)
@click.option(
    "-l",
    "--log-level",
    default="INFO",
    type=click.Choice(("DEBUG", "INFO", "WARNING", "ERROR"), case_sensitive=False),
    envvar="ANTIVIRUS_CONNECTOR_LOG_LEVEL",
)
@click.option("--log-file", type=Path, default=None, envvar="ANTIVIRUS_CONNECTOR_LOG_FILE")
@click.option(
    "--sequester-service-private-key",
    type=_parse_sequester_service_private_key_param,
    multiple=True,
    help="Sequester service's private RSA key (encoded in PEM format) used to decrypt the incoming data\nShould be passed as `<organization_id>:<pem_key>`",
)
@click.option("--antivirus-api-url", envvar="ANTIVIRUS_CONNECTOR_API_URL", type=str, required=True)
@click.option("--antivirus-api-key", envvar="ANTIVIRUS_CONNECTOR_API_KEY", type=str, required=True)
@click.option("--db", envvar="ANTIVIRUS_CONNECTOR_DB", type=str, required=False)
@click.option(
    "--db-min-connections",
    default=5,
    show_default=True,
    envvar="ANTIVIRUS_CONNECTOR_DB_MIN_CONNECTIONS",
    help="Minimal number of connections to the database",
)
@click.option(
    "--db-max-connections",
    default=7,
    show_default=True,
    envvar="ANTIVIRUS_CONNECTOR_DB_MAX_CONNECTIONS",
    help="Maximum number of connections to the database",
)
@click.option(
    "--blockstore",
    "-b",
    required=True,
    multiple=True,
    callback=lambda ctx, param, value: _parse_blockstore_params(value),
    envvar="ANTIVIRUS_CONNECTOR_BLOCKSTORE",
    metavar="CONFIG",
    help="Blockstore configuration",
)
def run_cli(
    port: int,
    host: str,
    client_origin: str,
    log_level: str,
    log_file: Path,
    sequester_service_private_key: List[Tuple[OrganizationID, oscrypto.asymmetric.PrivateKey]],
    antivirus_api_url: str,
    antivirus_api_key: str,
    db: str,
    db_min_connections: int,
    db_max_connections: int,
    blockstore: BaseBlockStoreConfig,
):
    if not sequester_service_private_key:
        var = os.environ.get("ANTIVIRUS_CONNECTOR_SEQUESTER_SERVICE_PRIVATE_KEY")
        if var:
            sequester_service_private_key = [
                _parse_sequester_service_private_key_param(x) for x in var.split(";")
            ]

    _setup_logging(log_level, log_file)
    logger.debug("Starting antivirus-connector !", version=__version__)

    if isinstance(blockstore, PostgreSQLBlockStoreConfig) and not db:
        raise SystemExit("`--db` argument is required with PostgreSQL blockstore")
    elif not isinstance(blockstore, PostgreSQLBlockStoreConfig) and db:
        logger.warning("`--db` argument is ignored when blockstore is not PostgreSQL")

    # Some HTTP servers will perform the redirection automatically in case of double slashes
    # but the antivirus API does not.
    if antivirus_api_url.endswith("/"):
        antivirus_api_url = antivirus_api_url[:-1]

    config = AppConfig(
        sequester_services_decryption_key=dict(sequester_service_private_key),
        antivirus_api_url=antivirus_api_url,
        antivirus_api_key=antivirus_api_key,
        blockstore_config=blockstore,
        db_url=db,
        db_min_connections=db_min_connections,
        db_max_connections=db_max_connections,
    )

    trio_main = partial(
        serve_app,
        host=host,
        port=port,
        config=config,
        client_allowed_origins=client_origin,
    )

    trio_asyncio.run(trio_main)


if __name__ == "__main__":
    run_cli()
