import argparse
from typing import Optional
from pathlib import Path
from functools import partial
import os
import sys
import trio
import logging
import structlog

from parsec.core.types import BackendAddr
from parsec.core.config import CoreConfig

from .app import serve_app


def _cook_website_url(url: str) -> str:
    if not url.startswith("https://") and not url.startswith("http://"):
        raise ValueError
    return url


_cook_website_url.__name__ = "http[s] url"  # Used by argparse for help output


def _setup_logging(log_level: str) -> None:
    # The infamous logging configuration...

    def _structlog_renderer(_, __, event_dict):
        event = event_dict.pop("event", "")
        args = ", ".join(f"{k}: {repr(v)}" for k, v in event_dict.items())
        return f"{event} ({args})"

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
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )


def build_config(backend_addr: BackendAddr, config_dir: Optional[Path] = None) -> CoreConfig:
    home = Path.home()
    mountpoint_base_dir = Path.home() / "Resana-Secure"

    if os.name == "nt":
        appdata = Path(os.environ["APPDATA"])
        data_base_dir = appdata / "resana_secure/data"
        cache_base_dir = appdata / "resana_secure/cache"
        config_dir = config_dir or appdata / "resana_secure/config"

    else:
        path = os.environ.get("XDG_DATA_HOME") or f"{home}/.local/share"
        data_base_dir = Path(path) / "resana_secure"

        path = os.environ.get("XDG_CACHE_HOME") or f"{home}/.cache"
        cache_base_dir = Path(path) / "resana_secure"

        path = os.environ.get("XDG_CONFIG_HOME") or f"{home}/.config"
        config_dir = config_dir or Path(path) / "resana_secure"

    return CoreConfig(
        config_dir=config_dir,
        data_base_dir=data_base_dir,
        cache_base_dir=cache_base_dir,
        mountpoint_base_dir=mountpoint_base_dir,
        # Use a mock to disable mountpoint instead of relying on this option
        mountpoint_enabled=True,
        ipc_win32_mutex_name="resana_secure",
        ipc_socket_file=data_base_dir / "resana_secure.lock",
        preferred_org_creation_backend_addr=backend_addr,
    )


def run_cli():
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--port", type=int, default=5775)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument(
        "--backend-addr",
        type=BackendAddr.from_url,
        default="parsec://resana-secure.numerique.gouv.fr",
    )
    parser.add_argument("--client-origin", type=lambda x: x.split(";"), default=["*"])
    parser.add_argument(
        "--resana-website-url", type=_cook_website_url, default="https://resana.numerique.gouv.fr/"
    )
    parser.add_argument("--disable-gui", action="store_true")
    parser.add_argument("--disable-mountpoint", action="store_true")
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    args = parser.parse_args()

    _setup_logging(args.log_level)

    if args.disable_mountpoint:
        # TODO: Parsec core factory should allow to do that
        from parsec.core.mountpoint import manager

        def _get_mountpoint_runner_mocked():
            async def _nop_runner(*args, **kwargs):
                None

            return _nop_runner

        manager.get_mountpoint_runner = _get_mountpoint_runner_mocked

    config = build_config(backend_addr=args.backend_addr, config_dir=args.config_dir)

    trio_main = partial(
        serve_app,
        host=args.host,
        port=args.port,
        config=config,
        client_allowed_origins=args.client_origin,
    )

    if args.disable_gui:
        trio.run(trio_main)

    else:
        # Inline import to avoid importing pyqt if gui is disabled
        from .gui import run_gui

        run_gui(trio_main=trio_main, resana_website_url=args.resana_website_url, config=config)
