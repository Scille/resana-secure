import argparse
from pathlib import Path
from functools import partial
import sys
import trio
import logging
import structlog

from parsec.core.types import BackendAddr

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
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--port", type=int, default=5775)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config-dir", type=Path, required=True)
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

    trio_main = partial(
        serve_app,
        host=args.host,
        port=args.port,
        config_dir=args.config_dir,
        client_allowed_origins=args.client_origin,
        backend_addr=args.backend_addr,
    )

    if args.disable_gui:
        trio.run(trio_main)

    else:
        # Inline import to avoid importing pyqt if gui is disabled
        from .gui import run_gui

        run_gui(trio_main=trio_main, resana_website_url=args.resana_website_url)
