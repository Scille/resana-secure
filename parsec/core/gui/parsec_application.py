# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QFile, QEvent
from PyQt5.QtGui import QFont, QFontDatabase, QPalette, QColor
from structlog import get_logger


logger = get_logger()


class ParsecApp(QApplication):
    connected_devices = set()

    def __init__(self):
        super().__init__(["-stylesheet"])
        self.setOrganizationName("Scille")
        self.setOrganizationDomain("parsec.cloud")
        self.setApplicationName("Parsec")
        pal = self.palette()
        pal.setColor(QPalette.Link, QColor(0x00, 0x92, 0xFF))
        pal.setColor(QPalette.LinkVisited, QColor(0x00, 0x70, 0xDD))
        self.setPalette(pal)

    def event(self, e):
        """Handle macOS FileOpen events."""
        if e.type() != QEvent.FileOpen or e.url().scheme() != "parsec":
            return super().event(e)
        try:
            url = e.url().url()
            mw = self.get_main_window()
            if not mw:
                pass
            else:
                mw.new_instance_needed.emit(url)
        except Exception:
            logger.exception("Url handling failed")

        return True

    def load_stylesheet(self, res=":/styles/styles/main.css"):
        rc = QFile(res)
        rc.open(QFile.ReadOnly)
        content = rc.readAll().data()
        self.setStyleSheet(str(content, "utf-8"))

    def load_font(self, font="Montserrat"):
        QFontDatabase.addApplicationFont(":/fonts/fonts/Montserrat.ttf")
        QFontDatabase.addApplicationFont(":/fonts/fonts/Roboto-Regular.ttf")
        f = QFont(font)
        self.setFont(f)

    @classmethod
    def add_connected_device(cls, org_id, device_id):
        cls.connected_devices.add((org_id, device_id))

    @classmethod
    def remove_connected_device(cls, org_id, device_id):
        cls.connected_devices.discard((org_id, device_id))

    @classmethod
    def is_device_connected(cls, org_id, device_id):
        return (org_id, device_id) in cls.connected_devices

    @classmethod
    def has_active_modal(cls):
        if cls.activeModalWidget():
            return True
        mw = cls.get_main_window()
        if not mw:
            return False
        for win in mw.children():
            if win.objectName() == "GreyedDialog":
                return True
        return False

    @classmethod
    def get_main_window(cls):
        # Avoid recursive imports
        from .main_window import MainWindow

        for win in cls.topLevelWidgets():
            if isinstance(win, MainWindow):
                return win
        return None
