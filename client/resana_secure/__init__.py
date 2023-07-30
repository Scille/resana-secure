# Early monkey patches

from typing import Any, cast


def _monkeypatch_parsec_version() -> None:
    # Globally patch parsec version to add `+resana`
    import parsec._version

    version = parsec._version.__version__
    parsec._version.__version__ = f"{version}+resana"


def _monkeypatch_user_agent() -> None:
    import parsec.api.transport
    import parsec.core.backend_connection.proxy

    from ._version import __version__

    USER_AGENT = f"resana-secure/{__version__}"
    parsec.api.transport.USER_AGENT = USER_AGENT
    parsec.core.backend_connection.proxy.USER_AGENT = USER_AGENT


def _monkeypatch_greyed_dialog() -> None:
    from parsec.core.gui.custom_dialogs import GreyedDialog

    def _paint_event(*args: Any) -> None:
        pass

    # The dialog opens with a grey rectangle. In Parsec, it serves as a transparent
    # background that covers the whole window to prevent its use (makes the dialog modal).
    # In Resana, we have no window to cover so we don't draw the grey rectangle.
    cast(Any, GreyedDialog).paintEvent = _paint_event


_monkeypatch_user_agent()
_monkeypatch_parsec_version()
_monkeypatch_greyed_dialog()
