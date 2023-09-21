from functools import wraps

from asgi_ip_filtering import AsgiIpFilteringMiddleware
from asgi_ip_filtering_by_organization import AsgiIpFilteringByOrganizationMiddleware

from parsec.backend import asgi
from parsec.backend.asgi import BackendQuartTrio, app_factory
from parsec.backend.cli import run_cmd


def patch_app_factory() -> None:
    """Monkeypatch `parsec.backend.asgi.app_factory`"""

    @wraps(app_factory)
    def patched_app_factory(*args, **kwargs) -> BackendQuartTrio:  # type: ignore[no-untyped-def, no-any-unimported, misc]
        # Middleware is applied in reverse order
        # Here, the request goes through:
        # - `AsgiIpFilteringMiddleware``
        # - `AsgiIpFilteringByOrganizationMiddleware`
        # - `BackendQuartTrio`
        # Before reaching the route logic and coming back.
        app = app_factory(*args, **kwargs)
        app.asgi_app = AsgiIpFilteringByOrganizationMiddleware(app.asgi_app)
        app.asgi_app = AsgiIpFilteringMiddleware(app.asgi_app)
        return app

    asgi.app_factory = patched_app_factory


if __name__ == "__main__":
    patch_app_factory()
    run_cmd()
