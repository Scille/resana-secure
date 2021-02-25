# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from zxcvbn import zxcvbn

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QValidator
from PyQt5.QtWidgets import QWidget

from parsec.core.gui.lang import translate as _

from parsec.core.gui.ui.password_strength_widget import Ui_PasswordStrengthWidget
from parsec.core.gui.ui.password_choice_widget import Ui_PasswordChoiceWidget


PASSWORD_CSS = {
    0: "color: #333333; background-color: none;",
    1: "color: #F44336; background-color: none;",
    2: "color: #F44336; background-color: none;",
    3: "color: #F1962B; background-color: none;",
    4: "color: #8BC34A; background-color: none;",
    5: "color: #8BC34A; background-color: none;",
}


def get_password_strength_text(password_score):
    PASSWORD_STRENGTH_TEXTS = [
        _("TEXT_PASSWORD_VALIDATION_TOO_SHORT"),
        _("TEXT_PASSWORD_VALIDATION_VERY_WEAK"),
        _("TEXT_PASSWORD_VALIDATION_WEAK"),
        _("TEXT_PASSWORD_VALIDATION_AVERAGE"),
        _("TEXT_PASSWORD_VALIDATION_GOOD"),
        _("TEXT_PASSWORD_VALIDATION_EXCELLENT"),
    ]
    return PASSWORD_STRENGTH_TEXTS[password_score]


def get_password_strength(password):
    if len(password) < 8:
        return 0
    result = zxcvbn(password)
    return result["score"] + 1


class PasswordStrengthWidget(QWidget, Ui_PasswordStrengthWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def on_password_change(self, text):
        if not text:
            self.hide()
            return
        score = get_password_strength(text)
        self.label.setText(
            _("TEXT_PASSWORD_VALIDATION_PASSWORD_STRENGTH_strength").format(
                strength=get_password_strength_text(score)
            )
        )
        self.label.setStyleSheet(PASSWORD_CSS[score])
        self.show()


class PasswordChoiceWidget(QWidget, Ui_PasswordChoiceWidget):
    info_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        pwd_str_widget = PasswordStrengthWidget()
        self.layout_password_strength.addWidget(pwd_str_widget)
        self.line_edit_password.textChanged.connect(pwd_str_widget.on_password_change)
        self.line_edit_password.textChanged.connect(self._check_match)
        self.line_edit_password_check.textChanged.connect(self._check_match)
        self.line_edit_password_check.editingFinished.connect(self._on_editing_finished)
        self.label_mismatch.hide()

    def _check_match(self, text=""):
        password = self.line_edit_password.text()
        password_check = self.line_edit_password_check.text()
        if (
            password
            and password_check
            and password == password_check
            and get_password_strength(password) > 0
        ):
            self.line_edit_password_check.setProperty("validity", QValidator.Acceptable)
            self.line_edit_password_check.setToolTip(_("TEXT_PASSWORD_CHECK_MATCH"))
            self.line_edit_password_check.style().polish(self.line_edit_password_check)
            self.label_mismatch.hide()
        else:
            if password and password_check and password != password_check:
                self.line_edit_password_check.setProperty("validity", QValidator.Intermediate)
                self.line_edit_password_check.setToolTip(_("TEXT_PASSWORD_CHECK_NO_MATCH"))
                self.line_edit_password_check.style().polish(self.line_edit_password_check)
                self.label_mismatch.show()
            else:
                self.line_edit_password_check.setProperty("validity", QValidator.Acceptable)
                self.line_edit_password_check.setToolTip(_("TEXT_PASSWORD_CHECK_MATCH"))
                self.line_edit_password_check.style().polish(self.line_edit_password_check)
                self.label_mismatch.hide()
        self.info_changed.emit()

    def _on_editing_finished(self):
        password = self.line_edit_password.text()
        password_check = self.line_edit_password_check.text()
        if password and password_check and password != password_check:
            self.line_edit_password_check.setProperty("validity", QValidator.Invalid)
            self.line_edit_password_check.style().polish(self.line_edit_password_check)
            self.label_mismatch.show()

    @property
    def password(self):
        return self.line_edit_password.text()

    def is_valid(self):
        password = self.line_edit_password.text()
        password_check = self.line_edit_password_check.text()
        return (
            password
            and password_check
            and password == password_check
            and get_password_strength(password) > 0
        )
