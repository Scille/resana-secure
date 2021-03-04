import argparse
from pathlib import Path
import trio
import secrets
from functools import partial
from typing import List
from quart_cors import cors
from quart_trio import QuartTrio
from contextlib import asynccontextmanager

from .cores_manager import CoresManager
from .routes.auth import auth_bp
from .routes.files import files_bp
from .routes.invite import invite_bp
from .routes.workspaces import workspaces_bp
from .routes.invitations import invitations_bp
from .ltcm import LTCM


@asynccontextmanager
async def app_factory(config_dir: Path, client_allowed_origins: List[str]):
    app = QuartTrio(__name__, static_folder=None)
    cors(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(invite_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(invitations_bp)

    app.config.from_mapping(
        # Secret key changes each time the application is started, this is
        # fine as long as we only use it for session cookies.
        # The reason for doing this is we serve the api on localhost, so
        # storing the secret on the hard drive in a no go.
        SECRET_KEY=secrets.token_hex(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="strict",
        QUART_CORS_ALLOW_CREDENTIALS=True,
        QUART_CORS_ALLOW_ORIGIN=client_allowed_origins,
        CORE_CONFIG_DIR=config_dir,
    )
    async with LTCM.run() as ltcm:
        app.ltcm = ltcm  # type: ignore
        app.cores_manager = CoresManager()  # type: ignore
        yield app


async def main(host, port, debug, client_allowed_origins, config_dir):
    async with app_factory(
        config_dir=config_dir, client_allowed_origins=client_allowed_origins
    ) as app:
        await app.run_task(host=host, port=port, debug=debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--client-origin", type=lambda x: x.split(";"), default=["*"])
    parser.add_argument("--config-dir", type=Path, required=True)
    args = parser.parse_args()
    trio.run(
        partial(
            main,
            port=args.port,
            host=args.host,
            debug=args.debug,
            client_allowed_origins=args.client_origin,
            config_dir=args.config_dir,
        )
    )
