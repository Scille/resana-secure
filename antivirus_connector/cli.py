import click
from typing import Optional, Tuple
from collections import namedtuple
from pathlib import Path
from functools import partial
import sys
import logging
import structlog
import trio_asyncio

from parsec.backend.config import BaseBlockStoreConfig
from parsec.backend.blockstore import PostgreSQLBlockStoreConfig
from parsec.backend.cli.utils import blockstore_backend_options

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
        logging.basicConfig(
            format=format, datefmt=datefmt, filename=log_file, level=level
        )
    else:
        logging.basicConfig(
            format=format, datefmt=datefmt, stream=sys.stdout, level=level
        )


@click.command(short_help="Runs the antivirus connector")
@click.option("--port", type=int, default=5775)
@click.option("--host", default="127.0.0.1")
@click.option("--client-origin", type=lambda x: x.split(";"), default="*")
@click.option(
    "-l",
    "--log-level",
    default="INFO",
    type=click.Choice(("DEBUG", "INFO", "WARNING", "ERROR"), case_sensitive=False),
)
@click.option("--log-file", type=Path, default=None)
@click.option(
    "--authority-private-key",
    envvar="ANTIVIRUS_AUTHORITY_PRIVATE_KEY",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--antivirus-api-url", envvar="ANTIVIRUS_API_URL", type=str, required=True
)
@click.option(
    "--antivirus-api-key", envvar="ANTIVIRUS_API_KEY", type=str, required=True
)
@click.option("--db", envvar="ANTIVIRUS_DB_URL", type=str, required=False)
@blockstore_backend_options
def run_cli(
    port: int,
    host: str,
    client_origin: str,
    log_level: str,
    log_file: str,
    authority_private_key: Path,
    antivirus_api_url: str,
    antivirus_api_key: str,
    db: str,
    blockstore: BaseBlockStoreConfig,
):

    _setup_logging(log_level, log_file)
    logger.debug("Starting antivirus-connector !", version=__version__)

    if isinstance(blockstore, PostgreSQLBlockStoreConfig) and not db:
        sys.exit("`--db` argument is required with PostgreSQL blockstore")
    elif not isinstance(blockstore, PostgreSQLBlockStoreConfig) and db:
        logger.warn("`--db` argument is ignored when blockstore is not PostgreSQL")

    config = AppConfig(
        authority_private_key_path=authority_private_key,
        antivirus_api_url=antivirus_api_url,
        antivirus_api_key=antivirus_api_key,
        blockstore_config=blockstore,
        db_url=db,
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
