from typing import Awaitable, Callable, Optional
from importlib import resources
from contextlib import asynccontextmanager
import trio
from structlog import get_logger
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QFileDialog
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtCore import pyqtSignal, QUrl

from parsec.core.config import CoreConfig
from parsec.core.ipcinterface import (
    run_ipc_server,
    send_to_ipc_server,
    IPCServerAlreadyRunning,
    IPCServerNotRunning,
    IPCCommand,
)
import multiprocessing
from parsec.core.gui.custom_dialogs import QDialogInProcess


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


class TrioQtApplication(QApplication):
    _run_in_qt_loop = pyqtSignal(object)

    foreground_needed = pyqtSignal()
    save_file_requested = pyqtSignal(object, object, object)

    def __init__(self, config: CoreConfig):
        super().__init__([])
        self.config = config

        def _exec_fn(fn):
            fn()

        self._run_in_qt_loop.connect(_exec_fn)
        self._trio_main_cancel_scope: Optional[trio.CancelScope] = None
        self._quit_cb: Callable = super().quit
        self.save_file_requested.connect(self._on_save_file_requested)
        self.nursery = None

    async def _save_file(self, save_path, workspace_fs, file_path):
        async with await trio.open_file(save_path, "wb") as dest_fd:
            async with await workspace_fs.open_file(file_path, "rb") as wk_fd:
                await dest_fd.write(await wk_fd.read())
                print("FILE SAVED")

    def _on_save_file_requested(self, core, workspace_fs, file_path):
        dest, _ = QDialogInProcess.getSaveFileName(None, "WHERE TO?")
        print("SAVE FILE TO", dest)
        self.nursery.start_soon(self._save_file, dest, workspace_fs, file_path)

    def exec_(self, trio_main, *args, **kwargs):
        def _run_sync_soon_threadsafe(fn):
            self._run_in_qt_loop.emit(fn)

        def _trio_done(trio_main_outcome):
            try:
                trio_main_outcome.unwrap()
            except Exception:
                logger.exception("Unexpected exception")

            # Call the *real* quit()
            self._quit_cb()

        async def _trio_main():
            with trio.CancelScope() as self._trio_main_cancel_scope:
                async with self._run_ipc_server():
                    try:
                        async with trio.open_nursery() as nursery:
                            self.nursery = nursery
                            await trio_main()
                    finally:
                        self._trio_main_cancel_scope = None

        def _start_trio():
            trio.lowlevel.start_guest_run(
                _trio_main,
                run_sync_soon_threadsafe=_run_sync_soon_threadsafe,
                done_callback=_trio_done,
            )

        self._run_in_qt_loop.emit(_start_trio)
        return super().exec_(*args, **kwargs)

    def quit(self):
        # Overwrite quit so that it closes the trio loop (that will itself
        # trigger the actual closing of the application)
        if self._trio_main_cancel_scope:
            self._trio_main_cancel_scope.cancel()
        else:
            self._quit_cb()

    @asynccontextmanager
    async def _run_ipc_server(self):
        async def _cmd_handler(cmd):
            self.foreground_needed.emit()
            return {"status": "ok"}

        while True:
            try:
                async with run_ipc_server(
                    _cmd_handler,
                    self.config.ipc_socket_file,
                    win32_mutex_name=self.config.ipc_win32_mutex_name,
                ):
                    yield

            except IPCServerAlreadyRunning:
                # Application is already started, give it our work then
                try:
                    await send_to_ipc_server(self.config.ipc_socket_file, IPCCommand.FOREGROUND)

                except IPCServerNotRunning:
                    # IPC server has closed, retry to create our own
                    continue

                # We have successfuly noticed the other running application,
                # time to close ourself
                self.quit()
                # Wait for our coroutine to be cancelled
                await trio.sleep_forever()


def run_gui(trio_main: Callable[[], Awaitable[None]], resana_website_url: str, config: CoreConfig):
    multiprocessing.set_start_method("spawn")

    with QDialogInProcess.manage_pools():
        app = TrioQtApplication(config)
        app.setQuitOnLastWindowClosed(False)
        tray = Systray()

        tray.on_close.connect(app.quit)

        def _open_resana_website():
            QDesktopServices.openUrl(QUrl(resana_website_url))

        tray.on_open.connect(_open_resana_website)
        app.foreground_needed.connect(_open_resana_website)

        app.exec_(trio_main)
