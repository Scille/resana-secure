from __future__ import annotations

import logging
import re
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, cast

import structlog
from hypercorn.config import Config as HyperConfig
from hypercorn.trio import serve as hypercorn_trio_serve
from quart import current_app as quart_current_app
from quart_cors import cors
from quart_rate_limiter import RateLimiter
from quart_trio import QuartTrio

# Expose current_app as a ResanaApp for all modules
if True:  # Hack to please flake8
    current_app = cast("ResanaApp", quart_current_app)

from .config import ResanaConfig
from .converters import WorkspaceConverter
from .cores_manager import CoresManager
from .invites_manager import ClaimersManager, GreetersManager
from .ltcm import LTCM
from .routes.auth import auth_bp
from .routes.files import files_bp
from .routes.humans import humans_bp
from .routes.invitations import invitations_bp
from .routes.invite import invite_bp
from .routes.organization import organization_bp
from .routes.recovery import recovery_bp
from .routes.workspaces import workspaces_bp
from .tgb import TGB

logger = structlog.get_logger()


class ResanaApp(QuartTrio):
    """A QuartTrio app that ensures that the backend is available in `g` global object."""

    ltcm: LTCM
    cores_manager: CoresManager
    greeters_managers: dict[str, GreetersManager]
    claimers_manager: ClaimersManager
    resana_config: ResanaConfig
    hyper_config: HyperConfig
    tgb: TGB | None = None

    async def serve(self) -> None:
        return await hypercorn_trio_serve(self, self.hyper_config)


@asynccontextmanager
async def app_factory(
    config: ResanaConfig,
    client_allowed_origins: List[str],
    with_rate_limiter: bool = True,
    tgb: TGB | None = None,
) -> AsyncIterator[ResanaApp]:
    app = ResanaApp(__name__, static_folder=None)
    app.config.from_mapping(
        # We need a big max content length to accept file upload !
        MAX_CONTENT_LENGTH=2**31,  # 2Go limit
        # Secret key changes each time the application is started, this is
        # fine as long as we only use it for session cookies.
        # The reason for doing this is we serve the api on localhost, so
        # storing the secret on the hard drive in a no go.
        SECRET_KEY=secrets.token_hex(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="strict",
        # Access-Control-Allow-Origin=* and Access-Control-Allow-Credential=include are mutually exclusive
        QUART_CORS_ALLOW_CREDENTIALS="*" not in client_allowed_origins,
        QUART_CORS_ALLOW_ORIGIN=client_allowed_origins,
    )

    app.url_map.converters["WorkspaceID"] = WorkspaceConverter

    cors(app)
    if with_rate_limiter:
        RateLimiter(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(humans_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(invite_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(organization_bp)

    @app.route("/", methods=["GET"])
    async def landing_page() -> tuple[str, int]:
        routes = sorted(
            [
                (rule.methods, re.sub(r"<\w+:(\w+)>", r"{\1}", rule.rule))
                for rule in current_app.url_map.iter_rules()
            ],
            key=lambda x: x[1],
        )
        body = "<h1>Resana Secure - Parsec client</h1>"
        body += "<h2>Available routes</h2>"
        body += "<ul>"
        for methods, url in routes:
            if methods is None:
                continue
            methods_display = ", ".join(methods - {"HEAD", "OPTIONS"})
            if methods_display:
                body += f"<li>{methods_display} <a href={url}>{url}</a></li>"
        body += "</ul>"

        return (
            f"""
<html lang="en">
<head>
    <meta charset="utf-8">
        <title>Resana Secure - Parsec client</title>
</head>
<body>
{body}
</body>
""",
            200,
        )

    async with LTCM.run() as ltcm:
        app.ltcm = ltcm
        app.resana_config = config
        app.cores_manager = CoresManager(
            config=config,
            ltcm=ltcm,
        )
        app.greeters_managers = defaultdict(GreetersManager)
        app.claimers_manager = ClaimersManager()
        app.tgb = tgb
        yield app


@asynccontextmanager
async def serve_app(
    host: str,
    port: int,
    config: ResanaConfig,
    client_allowed_origins: List[str],
    tgb: TGB | None = None,
) -> AsyncIterator[ResanaApp]:
    hyper_config = HyperConfig.from_mapping(
        {
            "bind": [f"{host}:{port}"],
            "accesslog": logging.getLogger("hypercorn.access"),
            "errorlog": logging.getLogger("hypercorn.error"),
            "include_server_header": False,
        }
    )

    async with app_factory(
        config=config,
        client_allowed_origins=client_allowed_origins,
        with_rate_limiter=True,
        tgb=tgb,
    ) as app:
        app.hyper_config = hyper_config
        yield app
