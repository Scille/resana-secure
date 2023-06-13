from typing import Dict
from dataclasses import dataclass
import oscrypto

from parsec.api.protocol import SequesterServiceID
from parsec.backend.config import BaseBlockStoreConfig


@dataclass
class AppConfig:
    sequester_services_decryption_key: Dict[SequesterServiceID, oscrypto.asymmetric.PrivateKey]
    antivirus_api_url: str
    antivirus_api_key: str
    antivirus_api_cert: str
    blockstore_config: BaseBlockStoreConfig
    db_url: str
    db_min_connections: int
    db_max_connections: int
