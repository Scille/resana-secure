from __future__ import annotations

import re
import secrets
import logging
from typing import AsyncIterator, List
from contextlib import asynccontextmanager

import trio
import trio_typing
from quart import current_app, ctx
from quart_cors import cors
from quart_trio import QuartTrio
from hypercorn.config import Config as HyperConfig
from hypercorn.trio import serve as hypercorn_trio_serve

from parsec.core.config import CoreConfig

from .cores_manager import CoresManager
from .invites_manager import ClaimersManager, GreetersManager
from .routes.auth import auth_bp
from .routes.humans import humans_bp
from .routes.files import files_bp
from .routes.invite import invite_bp
from .routes.workspaces import workspaces_bp
from .routes.invitations import invitations_bp
from .routes.recovery import recovery_bp
from .routes.organization import organization_bp
from .ltcm import LTCM


class ResanaApp(QuartTrio):
    """A QuartTrio app that ensures that the backend is available in `g` global object."""

    ltcm: LTCM
    cores_manager: CoresManager
    greeters_manager: GreetersManager
    claimers_manager: ClaimersManager
    core_config: CoreConfig
    hyper_config: HyperConfig
    task_status: trio_typing.TaskStatus

    def app_context(self) -> ctx.AppContext:
        app_context = super().app_context()
        app_context.g.ltcm = self.ltcm
        app_context.g.cores_manager = self.cores_manager
        app_context.g.greeters_manager = self.greeters_manager
        app_context.g.claimers_manager = self.claimers_manager
        app_context.g.core_config = self.core_config
        return app_context

    async def serve(self):
        return await hypercorn_trio_serve(self, self.hyper_config, task_status=self.task_status)


@asynccontextmanager
async def app_factory(
    config: CoreConfig, client_allowed_origins: List[str]
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

    cors(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(humans_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(invite_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(organization_bp)

    @app.route("/", methods=["GET"])
    async def landing_page():
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
        app.core_config = config
        app.cores_manager = CoresManager(core_config=config, ltcm=ltcm)
        app.greeters_manager = GreetersManager()
        app.claimers_manager = ClaimersManager()
        yield app


@asynccontextmanager
async def serve_app(
    host: str,
    port: int,
    config: CoreConfig,
    client_allowed_origins: List[str],
    task_status: trio_typing.TaskStatus = trio.TASK_STATUS_IGNORED,
) -> AsyncIterator[ResanaApp]:
    hyper_config = HyperConfig.from_mapping(
        {
            "bind": [f"{host}:{port}"],
            "accesslog": logging.getLogger("hypercorn.access"),
            "errorlog": logging.getLogger("hypercorn.error"),
        }
    )

    async with app_factory(config=config, client_allowed_origins=client_allowed_origins) as app:
        app.hyper_config = hyper_config
        app.task_status = task_status
        yield app
