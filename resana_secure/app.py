import re
import secrets
import logging
from typing import List
from contextlib import asynccontextmanager
from quart import current_app
from quart_cors import cors
from quart_trio import QuartTrio
from hypercorn.config import Config as HyperConfig
from hypercorn.trio import serve

from parsec.core.config import CoreConfig

from .cores_manager import CoresManager
from .invites_manager import ClaimersManager, GreetersManager
from .routes.auth import auth_bp
from .routes.humans import humans_bp
from .routes.files import files_bp
from .routes.invite import invite_bp
from .routes.workspaces import workspaces_bp
from .routes.invitations import invitations_bp
from .ltcm import LTCM


@asynccontextmanager
async def app_factory(config: CoreConfig, client_allowed_origins: List[str]):
    app = QuartTrio(__name__, static_folder=None)
    app.config.from_mapping(
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
        CORE_CONFIG=config,
    )

    cors(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(humans_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(invite_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(invitations_bp)

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
        app.ltcm = ltcm  # type: ignore
        app.cores_manager = CoresManager()  # type: ignore
        app.greeters_manager = GreetersManager()  # type: ignore
        app.claimers_manager = ClaimersManager()  # type: ignore
        yield app


async def serve_app(host: str, port: int, config: CoreConfig, client_allowed_origins: List[str]):
    config = HyperConfig.from_mapping(
        {
            "bind": [f"{host}:{port}"],
            "accesslog": logging.getLogger("hypercorn.access"),
            "errorlog": logging.getLogger("hypercorn.error"),
        }
    )

    async with app_factory(config=config, client_allowed_origins=client_allowed_origins) as app:
        await serve(app, config)
