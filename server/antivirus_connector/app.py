import logging
import re
from contextlib import asynccontextmanager
from typing import List

from hypercorn.config import Config as HyperConfig
from hypercorn.trio import serve
from quart import current_app
from quart_cors import cors
from quart_trio import QuartTrio

from parsec.backend.blockstore import blockstore_factory
from parsec.backend.postgresql.handler import PGHandler
from parsec.event_bus import EventBus
from parsec.utils import open_service_nursery

from .config import AppConfig
from .routes import bp


@asynccontextmanager
async def run_pg_db_handler(db_url, min_connections, max_connections):
    if not db_url:
        yield None
    else:
        event_bus = EventBus()
        dbh = PGHandler(db_url, min_connections, max_connections, event_bus)

        async with open_service_nursery() as nursery:
            await dbh.init(nursery)
            try:
                yield dbh
            finally:
                await dbh.teardown()


@asynccontextmanager
async def app_factory(config: AppConfig, blockstore, client_allowed_origins: List[str]):
    app = QuartTrio(__name__, static_folder=None)

    app.config.from_mapping(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="strict",
        # Maximum size of content. Limit is the same as Quart's default (16MB)
        # but I'd rather have it explicitly set.
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        # Access-Control-Allow-Origin=* and Access-Control-Allow-Credential=include are mutually exclusive
        QUART_CORS_ALLOW_CREDENTIALS="*" not in client_allowed_origins,
        QUART_CORS_ALLOW_ORIGIN=client_allowed_origins,
        APP_CONFIG=config,
        BLOCKSTORE=blockstore,
    )

    cors(app)
    app.register_blueprint(bp)

    @app.route("/", methods=["GET"])
    async def landing_page():
        routes = sorted(
            [
                (rule.methods, re.sub(r"<\w+:(\w+)>", r"{\1}", rule.rule))
                for rule in current_app.url_map.iter_rules()
            ],
            key=lambda x: x[1],
        )
        body = "<h1>Antivirus connector</h1>"
        body += "<h2>Available routes</h2>"
        body += "<ul>"
        for methods, url in routes:
            methods_display = ", ".join(methods - {"HEAD", "OPTIONS"})
            if methods_display:
                body += f"<li>{methods_display} <a href={url}>{url}</a></li>"
        body += "</ul>"

        return (
            f"""
<html lang="en">
<head>
    <meta charset="utf-8">
        <title>Antivirus connector</title>
</head>
<body>
{body}
</body>
""",
            200,
        )

    yield app


async def serve_app(host: str, port: int, config: AppConfig, client_allowed_origins: List[str]):
    hyper_config = HyperConfig.from_mapping(
        {
            "bind": [f"{host}:{port}"],
            "accesslog": logging.getLogger("hypercorn.access"),
            "errorlog": logging.getLogger("hypercorn.error"),
        }
    )

    async with run_pg_db_handler(
        config.db_url, config.db_min_connections, config.db_max_connections
    ) as dbh:
        blockstore = blockstore_factory(config=config.blockstore_config, postgresql_dbh=dbh)
        async with app_factory(
            config=config,
            blockstore=blockstore,
            client_allowed_origins=client_allowed_origins,
        ) as app:
            await serve(app, hyper_config)
