# Early monkey patches

import sys
import os
from typing import Any, cast
from importlib.abc import Traversable

from parsec.core.types import LocalDevice


def _monkeypatch_parsec_version() -> None:
    # Globally patch parsec version to add `+resana`
    import parsec._version

    version = parsec._version.__version__
    parsec._version.__version__ = f"{version}+resana"


def _monkeypatch_user_agent() -> None:
    from ._version import __version__
    import parsec.api.transport
    import parsec.core.backend_connection.proxy

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


def _monkeypatch_drive_icon() -> None:
    if sys.platform != "win32":
        return

    from parsec.core import win_registry

    def _get_drive_icon_path(device: LocalDevice) -> Traversable:
        from PyQt5.QtWidgets import QApplication
        from .gui import ResanaGuiApp
        from .cores_manager import is_org_hosted_on_rie

        qt_app = cast(ResanaGuiApp, QApplication.instance())

        icon = "quake.ico"
        if is_org_hosted_on_rie(device.organization_addr, qt_app.config.rie_server_addrs):
            icon = "doom.ico"

        return cast(Traversable, os.path.join(os.getcwd(), icon))

    win_registry._get_drive_icon_path = _get_drive_icon_path


_monkeypatch_user_agent()
_monkeypatch_parsec_version()
_monkeypatch_greyed_dialog()
_monkeypatch_drive_icon()
