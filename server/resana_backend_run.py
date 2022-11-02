from functools import wraps

from parsec.backend import asgi
from parsec.backend.cli import run_cmd
from parsec.backend.asgi import app_factory, BackendQuartTrio

from asgi_ip_filtering import AsgiIpFilteringMiddleware


def patch_app_factory() -> None:
    """Monkeypatch `parsec.backend.asgi.app_factory`"""

    @wraps(app_factory)
    def patched_app_factory(*args, **kwargs) -> BackendQuartTrio:  # type: ignore[no-untyped-def, no-any-unimported, misc]
        app = app_factory(*args, **kwargs)
        app.asgi_app = AsgiIpFilteringMiddleware(app.asgi_app)
        return app

    asgi.app_factory = patched_app_factory


if __name__ == "__main__":
    patch_app_factory()
    run_cmd()
