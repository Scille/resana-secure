from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

import attr

from parsec.core.config import CoreConfig


class _CoreConfig(CoreConfig):
    @property
    def ipc_socket_file(self) -> Path:
        return self.data_base_dir / "resana-secure.lock"


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ResanaConfig:
    core_config: _CoreConfig
    rie_server_addrs: List[Tuple[str, int | None]] = []
    check_conformity: bool = False

    def evolve(self, **kwargs: Any) -> ResanaConfig:
        return attr.evolve(self, **kwargs)
