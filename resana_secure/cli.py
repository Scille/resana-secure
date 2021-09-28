import argparse
from typing import Optional, Tuple
from pathlib import Path
from functools import partial
import os
import sys
import trio
import logging
import structlog

from parsec.core.config import CoreConfig
from parsec.core.backend_connection.transport import force_proxy_url, force_proxy_pac_url

from .app import serve_app


def _cook_website_url(url: str) -> str:
    if not url.startswith("https://") and not url.startswith("http://"):
        raise ValueError
    return url


_cook_website_url.__name__ = "http[s] url"  # Used by argparse for help output


def _setup_logging(log_level: str, log_file: Optional[Path]) -> None:
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

    format = "%(asctime)s %(levelname)s %(name)s - %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"
    level = getattr(logging, log_level)
    if log_file:
        log_file.parent.mkdir(exist_ok=True, parents=True)
        logging.basicConfig(format=format, datefmt=datefmt, filename=log_file, level=level)
    else:
        logging.basicConfig(format=format, datefmt=datefmt, stream=sys.stdout, level=level)


def get_default_dirs() -> Tuple[Path, Path, Path, Path]:
    mountpoint_base_dir = Path.home() / "Resana-Secure"

    if os.name == "nt":
        appdata = Path(os.environ["APPDATA"])
        data_base_dir = appdata / "resana_secure/data"
        cache_base_dir = appdata / "resana_secure/cache"
        config_dir = appdata / "resana_secure/config"

    else:
        home = Path.home()

        path = os.environ.get("XDG_DATA_HOME") or f"{home}/.local/share"
        data_base_dir = Path(path) / "resana_secure"

        path = os.environ.get("XDG_CACHE_HOME") or f"{home}/.cache"
        cache_base_dir = Path(path) / "resana_secure"

        path = os.environ.get("XDG_CONFIG_HOME") or f"{home}/.config"
        config_dir = Path(path) / "resana_secure"

    return mountpoint_base_dir, data_base_dir, cache_base_dir, config_dir


def run_cli(args=None, default_log_level: str = "INFO", default_log_file: Optional[Path] = None):
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--port", type=int, default=5775)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--client-origin", type=lambda x: x.split(";"), default=["*"])
    parser.add_argument(
        "--resana-website-url",
        type=_cook_website_url,
        metavar="URL",
        default="https://resana.numerique.gouv.fr/",
    )
    parser.add_argument("--disable-gui", action="store_true")
    parser.add_argument("--disable-mountpoint", action="store_true")
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default=default_log_level
    )
    parser.add_argument("--log-file", type=Path, default=default_log_file)
    parser.add_argument(
        "--force-proxy", type=_cook_website_url, metavar="URL", help="Force use of proxy server"
    )
    parser.add_argument(
        "--force-proxy-pac",
        type=_cook_website_url,
        metavar="URL",
        help="Force use of server provided proxy .PAC configuration",
    )
    args = parser.parse_args(args=args)

    if args.force_proxy and args.force_proxy_pac:
        raise SystemExit("`--force-proxy-pac` and `--force-proxy` are mutually exclusive")
    if args.force_proxy:
        force_proxy_url(args.force_proxy)
    if args.force_proxy_pac:
        force_proxy_pac_url(args.force_proxy_pac)

    (
        mountpoint_base_dir,
        default_data_base_dir,
        cache_base_dir,
        default_config_dir,
    ) = get_default_dirs()
    config_dir = args.config or default_config_dir
    data_base_dir = args.data or default_data_base_dir

    config = CoreConfig(
        config_dir=config_dir,
        data_base_dir=data_base_dir,
        cache_base_dir=cache_base_dir,
        # Only used on linux (Windows mounts with drive letters)
        mountpoint_base_dir=mountpoint_base_dir,
        # Use a mock to disable mountpoint instead of relying on this option
        mountpoint_enabled=True,
        ipc_win32_mutex_name="resana-secure",
        ipc_socket_file=data_base_dir / "resana-secure.lock",
        preferred_org_creation_backend_addr=None,
    )

    _setup_logging(args.log_level, args.log_file)

    if args.disable_mountpoint:
        # TODO: Parsec core factory should allow to do that
        from parsec.core.mountpoint import manager

        def _get_mountpoint_runner_mocked():
            async def _nop_runner(*args, **kwargs):
                None

            return _nop_runner

        manager.get_mountpoint_runner = _get_mountpoint_runner_mocked

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
