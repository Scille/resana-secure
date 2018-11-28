from PyQt5.QtCore import pyqtSignal, QCoreApplication, Qt
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt5.QtGui import QColor

from parsec.core.gui.ui.workspace_button import Ui_WorkspaceButton


class WorkspaceButton(QWidget, Ui_WorkspaceButton):
    clicked = pyqtSignal(str)
    share_clicked = pyqtSignal(QWidget)
    details_clicked = pyqtSignal(QWidget)
    delete_clicked = pyqtSignal(QWidget)

    def __init__(self, workspace_name, is_owner, creator, files, shared_with=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.is_owner = is_owner
        self.creator = creator
        self.shared_with = shared_with
        self.name = workspace_name
        for i, f in enumerate(files[:4], 1):
            label = getattr(self, "label_file{}".format(i))
            label.setText(f)
        effect = QGraphicsDropShadowEffect(self)
        effect.setColor(QColor(164, 164, 164))
        effect.setBlurRadius(10)
        effect.setXOffset(4)
        effect.setYOffset(4)
        self.setGraphicsEffect(effect)
        self.button_details.clicked.connect(self.button_details_clicked)
        self.button_share.clicked.connect(self.button_share_clicked)
        self.button_delete.clicked.connect(self.button_delete_clicked)

    def button_details_clicked(self):
        self.details_clicked.emit(self)

    def button_share_clicked(self):
        self.share_clicked.emit(self)

    def button_delete_clicked(self):
        self.delete_clicked.emit(self)

    @property
    def name(self):
        return self.workspace_name

    @name.setter
    def name(self, value):
        self.workspace_name = value
        if self.shared_with:
            if self.is_owner:
                self.label_workspace.setText(
                    QCoreApplication.translate("WorkspacesWidget", "{} (shared)".format(value))
                )
            else:
                self.label_workspace.setText(
                    QCoreApplication.translate(
                        "WorkspacesWidget", "{} (shared by {})".format(value, self.creator)
                    )
                )
        else:
            self.label_workspace.setText(value)

    def mousePressEvent(self, event):
        if event.button() & Qt.LeftButton:
            self.clicked.emit(self.workspace_name)
