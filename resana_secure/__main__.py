import argparse
from pathlib import Path
from functools import partial
import trio

from parsec.core.types import BackendAddr

from .app import serve_app


def _cook_website_url(url):
    if not url.startswith("https://") and not url.startswith("http://"):
        raise ValueError
    return url


_cook_website_url.__name__ = "http[s] url"  # Used by argparse for help output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--port", type=int, default=5775)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
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
    args = parser.parse_args()

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
        debug=args.debug,
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
