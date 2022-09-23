from pathlib import Path
from dataclasses import dataclass
from parsec.backend.config import BaseBlockStoreConfig


@dataclass
class AppConfig:
    authority_private_key: bytes
    antivirus_api_url: str
    antivirus_api_key: str
    blockstore_config: BaseBlockStoreConfig
    db_url: str
    db_min_connections: int
    db_max_connections: int
