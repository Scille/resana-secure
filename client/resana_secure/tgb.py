from __future__ import annotations

import ctypes
import os
import platform
from enum import IntEnum

try:
    import tgbverifier  # type: ignore[import]
except ImportError:
    if platform.system() == "Windows":
        print("TGBVerified is not available")


class TGBException(Exception):
    pass


class TGB:
    DLL_PATH = "%programfiles%/TheGreenBow/TheGreenBow Secure Connection Agent/tgb_conformity.dll"
    SIGNER = "THEGREENBOW"

    class ConformityGet(IntEnum):
        OK = 0
        UNKNOWN_ID = 1
        INVALID_ARGUMENTS = 2
        INTERNAL_ERROR = 3

    class ConformityType(IntEnum):
        FIREWALL = 1
        ANTIVIRUS = 2

    class ConformityLevel(IntEnum):
        Level1 = 1
        Level2 = 2
        Level3 = 3
        Level4 = 4
        Good = 4

    def __init__(self) -> None:
        self._signed = False
        self._antivirus_compliant = False
        self._firewall_compliant = False
        self._dll_handle: ctypes.CDLL | None = None
        self.dll_path = os.path.expandvars(TGB.DLL_PATH)

    def load_dll(self) -> None:
        try:
            self._dll_handle = ctypes.cdll.LoadLibrary(self.dll_path)
        except OSError:
            raise TGBException(f"Could not load DLL `{self.dll_path}`")

    def compute(self) -> None:
        self._signed = self._get_dll_signed()
        self._antivirus_compliant = self._get_antivirus_compliance()
        self._firewall_compliant = self._get_firewall_compliance()

    def _get_dll_signed(self) -> bool:
        return tgbverifier.is_signed(self.dll_path)

    def _process_return_status(self, return_status: int) -> None:
        if return_status == TGB.ConformityGet.INTERNAL_ERROR:
            raise TGBException("TGB Agent internal error")
        elif return_status == TGB.ConformityGet.INVALID_ARGUMENTS:
            raise TGBException("Invalid argument when calling TGB Agent, should not happen")
        elif return_status == TGB.ConformityGet.UNKNOWN_ID:
            raise TGBException("Unknown ID when calling TGB Agent, should not happend")

    def _get_compliance(self, conformity_type: TGB.ConformityType) -> bool:
        assert self._dll_handle is not None

        try:
            get_conformity_func = self._dll_handle.TGBGetConformityItem
            free_comment_func = self._dll_handle.TGBFreeCommentString
        except AttributeError:
            raise TGBException(
                f"Missing required functions `TGBGetConformityItem` or `TGBFreeCommentString` from `{self.dll_path}`"
            )

        level = ctypes.c_int()
        comment = ctypes.c_char_p()
        status = get_conformity_func(
            conformity_type.value, ctypes.byref(level), ctypes.byref(comment)
        )

        if comment:
            free_comment_func(comment)

        self._process_return_status(status)
        return level.value == TGB.ConformityLevel.Good.value

    def _get_antivirus_compliance(self) -> bool:
        return self._get_compliance(TGB.ConformityType.ANTIVIRUS)

    def _get_firewall_compliance(self) -> bool:
        return self._get_compliance(TGB.ConformityType.FIREWALL)

    @property
    def is_signed(self) -> bool:
        return self._signed

    @property
    def is_antivirus_compliant(self) -> bool:
        return self._antivirus_compliant

    @property
    def is_firewall_compliant(self) -> bool:
        return self._firewall_compliant

    def is_compliant(self) -> bool:
        return self._signed and self._antivirus_compliant and self._firewall_compliant


if __name__ == "__main__":

    def get_symbol(val: bool) -> str:
        return "\N{CHECK MARK}" if val else "\N{HEAVY BALLOT X}"

    tgb = TGB()
    tgb.load_dll()

    print(
        f"""
        {get_symbol(tgb.is_signed)} Signature
        {get_symbol(tgb.is_antivirus_compliant)} Antivirus
        {get_symbol(tgb.is_firewall_compliant)} Firewall
    """
    )
