from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, AsyncIterator, Awaitable
from contextlib import asynccontextmanager, AbstractAsyncContextManager
import trio
import os
import qtrio
import signal
import multiprocessing
from structlog import get_logger
from PyQt5.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QLineEdit,
    QInputDialog,
    QMessageBox,
)
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtCore import QUrl, pyqtSignal

from .cores_manager import (
    CoreNotLoggedError,
    CoreDeviceNotFoundError,
    CoreDeviceInvalidPasswordError,
    CoreDeviceEncryptedKeyNotFoundError,
    CoresManager,
)

from parsec.core.local_device import (
    AvailableDevice,
)
from parsec.core.config import CoreConfig

from parsec.core.types import DEFAULT_BLOCK_SIZE
from parsec.core.fs import FsPath, WorkspaceFS

from parsec.core.ipcinterface import (
    run_ipc_server,
    send_to_ipc_server,
    IPCServerAlreadyRunning,
    IPCServerNotRunning,
    IPCCommand,
)

from parsec.core.gui.custom_dialogs import QDialogInProcess
from .config import ResanaConfig
from ._version import __version__ as RESANA_VERSION


if TYPE_CHECKING:
    from .app import ResanaApp

logger = get_logger()


class Systray(QSystemTrayIcon):
    device_clicked = pyqtSignal(AvailableDevice, object)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self._nursery: trio.Nursery | None = None
        self._quart_app: ResanaApp | None = None

        self.setToolTip(f"Resana Secure v{RESANA_VERSION}")
        self.menu = QMenu()

        self.menu.addSection("Resana Secure")
        self.open_action = self.menu.addAction("Ouvrir Resana")
        self.login_menu = self.menu.addMenu("Connexion")

        # When the main menu is about to be shown, we fill the list of devices
        # We could do it only when the "Login" menu is about to be shown,
        # but then Qt does not know how much size the submenus are going to take
        # and the device list gets cut.
        self.menu.aboutToShow.connect(self._list_login_menu)
        self.menu.addSeparator()

        self.close_action = self.menu.addAction("Quitter")
        self.open_clicked = self.open_action.triggered
        self.close_clicked = self.close_action.triggered

        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)

    @property
    def nursery(self) -> trio.Nursery:
        assert self._nursery is not None
        return self._nursery

    @property
    def quart_app(self) -> ResanaApp:
        assert self._quart_app is not None
        return self._quart_app

    def _on_device_clicked(self, device: AvailableDevice, token: str | None) -> Callable[[], None]:
        def _internal_on_device_clicked() -> None:
            self.device_clicked.emit(device, token)

        return _internal_on_device_clicked

    def _list_login_menu(self) -> None:
        self.login_menu.clear()

        async def _add_devices_to_login_menu() -> None:
            devices = await self.quart_app.cores_manager.list_available_devices(
                only_offline_available=True
            )
            for (_, _), (device, token) in devices.items():
                assert device.human_handle is not None
                action = self.login_menu.addAction(
                    f"{device.organization_id.str} - {device.human_handle.email} - {'Connecté' if token else 'Non connecté'}"
                )
                action.triggered.connect(self._on_device_clicked(device, token))
            if not devices:
                self.login_menu.addAction("Aucun compte")

        self.nursery.start_soon(_add_devices_to_login_menu)

    def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Does not work on Linux (Debian with XFCE) where DoubleClick is not triggered,
        # resulting in two QSystemTrayIcon.Trigger instead
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_clicked.emit()


class ResanaGuiApp(QApplication):
    message_requested = pyqtSignal(str, str)
    save_file_requested = pyqtSignal(WorkspaceFS, FsPath)
    file_rejected = pyqtSignal(FsPath)

    def __init__(
        self,
        config: ResanaConfig,
        resana_website_url: str,
    ):
        super().__init__([])
        self.config: ResanaConfig = config
        self.resana_website_url: str = resana_website_url

        self.tray = Systray(parent=self)

        self.tray.close_clicked.connect(self.close)
        self.tray.open_clicked.connect(self._on_open_clicked)
        self.tray.device_clicked.connect(self._on_device_clicked)

        self.save_file_requested.connect(self._on_save_file_requested)

        self._nursery: trio.Nursery | None = None
        self._cancel_scope: trio.CancelScope | None = None
        self._quart_app: ResanaApp | None = None

        self.setApplicationName("Resana Secure")
        self.setApplicationDisplayName("Resana Secure")
        self.setApplicationVersion(RESANA_VERSION)

        with resources.path("resana_secure", "icon.png") as icon_path:
            icon = QIcon(str(icon_path))
            self.tray.setIcon(icon)
            self.setWindowIcon(icon)

        self.message_requested.connect(
            lambda title, msg: self.tray.showMessage(title, msg, self.windowIcon())
        )
        self.file_rejected.connect(self._on_file_rejected)

        # Show the tray only after setting an icon to avoid a warning
        self.tray.show()

    @property
    def nursery(self) -> trio.Nursery:
        assert self._nursery is not None
        return self._nursery

    @property
    def cancel_scope(self) -> trio.CancelScope:
        assert self._cancel_scope is not None
        return self._cancel_scope

    @property
    def quart_app(self) -> ResanaApp:
        assert self._quart_app is not None
        return self._quart_app

    # Mypy don't support completely property, see https://github.com/python/mypy/issues/1465
    @nursery.setter  # type: ignore[no-redef,attr-defined]
    def nursery(self, nursery: trio.Nursery) -> None:
        self._nursery = nursery
        self.tray._nursery = nursery

    # Mypy don't support completely property, see https://github.com/python/mypy/issues/1465
    @cancel_scope.setter  # type: ignore[no-redef,attr-defined]
    def cancel_scope(self, cancel_scope: trio.CancelScope) -> None:
        self._cancel_scope = cancel_scope

    # Mypy don't support completely property, see https://github.com/python/mypy/issues/1465
    @quart_app.setter  # type: ignore[no-redef,attr-defined]
    def quart_app(self, quart_app: ResanaApp) -> None:
        self._quart_app = quart_app
        self.tray._quart_app = quart_app

    def _on_file_rejected(self, file_path: FsPath) -> None:
        self.message_requested.emit(
            "Fichier malicieux détecté",
            f"Le fichier `{file_path}` a été détecté comme malicieux. Il ne sera pas synchronisé.",
        )

    async def _on_login_clicked(self, device: AvailableDevice, password: str) -> None:
        assert device.human_handle is not None
        try:
            await self.quart_app.cores_manager.login(
                email=device.human_handle.email,
                organization_id=device.organization_id,
                user_password=password,
            )
            self.message_requested.emit(
                "Connexion",
                f"Vous êtes connecté(e) à {device.organization_id.str} - {device.human_handle.email}.",
            )
        except CoreDeviceInvalidPasswordError:
            QMessageBox.warning(None, "Erreur", "Mot de passe incorrect.")
        except CoreDeviceNotFoundError:
            QMessageBox.warning(None, "Erreur", "Impossible de se connecter.")
        except CoreDeviceEncryptedKeyNotFoundError:
            QMessageBox.warning(
                None,
                "Erreur",
                "Vous devez vous connecter au moins une fois au serveur Resana pour utiliser l'authentification hors-ligne.",
            )

    async def _on_logout_clicked(self, token: str) -> None:
        try:
            await self.quart_app.cores_manager.logout(token)
            self.message_requested.emit("Déconnexion", "Vous avez été déconnecté(e).")
        except CoreNotLoggedError:
            # Can happen in some weird cases if the user was logged out
            # in another way. Better to not show anything.
            pass

    def _on_device_clicked(self, device: AvailableDevice, token: str | None) -> None:
        assert device.human_handle is not None
        if token:
            answer = QMessageBox.question(
                None,
                "Déconnexion",
                f"Êtes-vous sûr de vouloir vous déconnecter de {device.organization_id.str} - {device.human_handle.email} ?",
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.nursery.start_soon(self._on_logout_clicked, token)
        else:
            password, ok = QInputDialog.getText(
                None,  # type: ignore[arg-type]
                "Mot de passe requis",
                f"Veuillez entrer le mot de passe pour {device.organization_id.str} - {device.human_handle.email}.",
                echo=QLineEdit.EchoMode.Password,
            )
            if ok and password:
                self.nursery.start_soon(self._on_login_clicked, device, password)
        self.save_file_requested.connect(self._on_save_file_requested)

    def _on_save_file_requested(self, workspace_fs: WorkspaceFS, path: FsPath) -> None:
        async def _save_file(save_path: str, workspace_fs: WorkspaceFS, file_path: FsPath) -> None:
            try:
                self.message_requested.emit(
                    "Téléchargement",
                    f"Le fichier {file_path.name.str} est en cours de téléchargement.\nIl sera ouvert automatiquement.",
                )
                async with await trio.open_file(save_path, "wb") as dest_fd:
                    async with await workspace_fs.open_file(file_path, "rb") as wk_fd:
                        while data := await wk_fd.read(size=DEFAULT_BLOCK_SIZE):
                            await dest_fd.write(data)
            except Exception:
                self.message_requested.emit(
                    "Erreur",
                    f"Impossible de télécharger le fichier {file_path.name.str}.",
                )
                logger.exception("Failed to save the file with mountpoints deactivated")
            else:
                await trio.to_thread.run_sync(
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(save_path)))
                )

        dest, _ = QDialogInProcess.getSaveFileName(
            None,
            f"Sauvegarde du fichier {path.name.str}",
            str(Path.home() / path.name.str),
        )
        if dest:
            self.nursery.start_soon(_save_file, dest, workspace_fs, path)

    def _on_open_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl(self.resana_website_url))

    def close(self) -> None:
        self.closeAllWindows()
        self.cancel_scope.cancel()


@asynccontextmanager
async def _run_ipc_server(
    cancel_scope: trio.CancelScope, config: CoreConfig, resana_website_url: str
) -> AsyncIterator[None]:
    async def _cmd_handler(_: object) -> dict[str, str]:
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


def _patch_cores_manager(cores_manager: CoresManager) -> None:
    """Testing Resana with offline login can be a bit of a drag,
    because devices need to be created using an encrypted key.
    For testing purposes only, we can set the variable `RESANA_DEBUG_GUI=true`
    which patches `login` and `list_available_devices` from the cores manager so
    that the `user_password` that should normally be used to decrypt the parsec
    key will be used as the key instead.
    """

    if os.environ.get("RESANA_DEBUG_GUI", "false").lower() != "true":
        return

    import types

    real_login = cores_manager.login
    real_list_available_devices = cores_manager.list_available_devices

    def _patched_login(self: object, *args: Any, **kwargs: Any) -> Awaitable[str]:
        # Replacing `key` by `user_password`
        if kwargs.get("user_password"):
            pwd = kwargs.pop("user_password")
            kwargs["key"] = pwd
        return real_login(*args, **kwargs)

    async def _patched_list_available_devices(self: object, *args: object, **kwargs: object) -> Any:
        # Set `only_offline_available` to False
        return await real_list_available_devices(only_offline_available=False)

    # Since it's all just a big hack, we can tell mypy to shut up
    cores_manager.login = types.MethodType(_patched_login, cores_manager)  # type: ignore[assignment]
    cores_manager.list_available_devices = types.MethodType(  # type: ignore[assignment]
        _patched_list_available_devices, cores_manager
    )


async def _qtrio_run(
    app: ResanaGuiApp,
    quart_app_context: Callable[[], AbstractAsyncContextManager[ResanaApp]],
    config: ResanaConfig,
    resana_website_url: str,
) -> None:
    # Mypy don't support property setter ?
    with trio.CancelScope() as app.cancel_scope:  # type: ignore[misc]
        # Exits gracefully with a Ctrl+C

        signal.signal(signal.SIGINT, lambda *_: app.close())

        async with _run_ipc_server(app.cancel_scope, config.core_config, resana_website_url):
            # Mypy don't support property setter ?
            async with trio.open_nursery() as app.nursery:  # type: ignore[misc]

                # Mypy don't support property setter ?
                async with quart_app_context() as app.quart_app:  # type: ignore[misc]

                    _patch_cores_manager(app.quart_app.cores_manager)

                    app.setQuitOnLastWindowClosed(False)
                    await app.quart_app.serve()


def run_gui(
    quart_app_context: Callable[[], AbstractAsyncContextManager[ResanaApp]],
    resana_website_url: str,
    config: ResanaConfig,
) -> None:

    # In theory this should lead to better rendering on high dpi desktop
    # but it seems to make absolutely no difference.
    # Keeping the comments here just in case

    # from PyQt5.QtCore import Qt
    # QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    # QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    # QApplication.setHighDpiScaleFactorRoundingPolicy(
    #    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    # )

    multiprocessing.set_start_method("spawn")

    with QDialogInProcess.manage_pools():
        app = ResanaGuiApp(
            config=config,
            resana_website_url=resana_website_url,
        )
        qtrio.run(_qtrio_run, app, quart_app_context, config, resana_website_url)
