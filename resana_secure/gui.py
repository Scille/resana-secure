from typing import Awaitable, Callable, Optional
from importlib import resources
from contextlib import asynccontextmanager
import trio
import qtrio
import signal
from structlog import get_logger
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtCore import QUrl, Qt

from parsec.core.config import CoreConfig
from parsec.core.ipcinterface import (
    run_ipc_server,
    send_to_ipc_server,
    IPCServerAlreadyRunning,
    IPCServerNotRunning,
    IPCCommand,
)


logger = get_logger()


class Systray(QSystemTrayIcon):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setToolTip("Resana Secure")
        self.menu = QMenu()

        self.menu.addSection("Resana Secure")
        self.open_action = self.menu.addAction("Ouvrir Resana")
        self.close_action = self.menu.addAction("Quitter")

        self.on_open = self.open_action.triggered
        self.on_close = self.close_action.triggered

        self.setContextMenu(self.menu)

        with resources.path("resana_secure", "icon.png") as icon_path:
            icon = QIcon(str(icon_path))
        self.setIcon(icon)

        self.activated.connect(self.on_activated)
        self.show()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.on_open.emit()


class ResanaGuiApp(QApplication):
    def __init__(
        self,
        cancel_scope: trio.CancelScope,
        config: CoreConfig,
        resana_website_url: str,
    ):
        super().__init__([])
        self.config: CoreConfig = config
        self.resana_website_url: str = resana_website_url
        self.tray = Systray(parent=self)
        self.tray.on_close.connect(self.quit)
        self.tray.on_open.connect(self._on_open_clicked)
        self._cancel_scope: trio.CancelScope = cancel_scope

    def _on_open_clicked(self):
        QDesktopServices.openUrl(QUrl(self.resana_website_url))

    def quit(self):
        # Overwrite quit so that it closes the trio loop (that will itself
        # trigger the actual closing of the application)
        self._cancel_scope.cancel()


@asynccontextmanager
async def _run_ipc_server(
    cancel_scope: trio.CancelScope, config: CoreConfig, resana_website_url: str
):
    async def _cmd_handler(_):
        QDesktopServices.openUrl(QUrl(resana_website_url))
        return {"status": "ok"}

    while True:
        try:
            async with run_ipc_server(
                _cmd_handler,
                config.ipc_socket_file,
                win32_mutex_name=config.ipc_win32_mutex_name,
            ):
                yield

        except IPCServerAlreadyRunning:
            # Application is already started, give it our work then
            try:
                await send_to_ipc_server(config.ipc_socket_file, IPCCommand.FOREGROUND)

            except IPCServerNotRunning:
                # IPC server has closed, retry to create our own
                continue

            cancel_scope.cancel()
            await trio.sleep_forever()


async def _qtrio_run(
    trio_main: Callable[[], Awaitable[None]],
    config: CoreConfig,
    resana_website_url: str,
):
    with trio.CancelScope() as cancel_scope:
        # Exits gracefully with a Ctrl+C
        signal.signal(signal.SIGINT, lambda *_: cancel_scope.cancel())
        async with _run_ipc_server(cancel_scope, config, resana_website_url):
            app = ResanaGuiApp(cancel_scope, config, resana_website_url)
            app.setQuitOnLastWindowClosed(False)
            await trio_main()


def run_gui(
    trio_main: Callable[[], Awaitable[None]],
    resana_website_url: str,
    config: CoreConfig,
):

    # Better rendering on high DPI desktops
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    qtrio.run(_qtrio_run, trio_main, config, resana_website_url)
