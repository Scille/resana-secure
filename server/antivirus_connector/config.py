from typing import Dict
from dataclasses import dataclass
import oscrypto

from parsec.api.protocol import OrganizationID
from parsec.backend.config import BaseBlockStoreConfig


@dataclass
class AppConfig:
    sequester_services_decryption_key: Dict[OrganizationID, oscrypto.asymmetric.PrivateKey]
    antivirus_api_url: str
    antivirus_api_key: str
    blockstore_config: BaseBlockStoreConfig
    db_url: str
    db_min_connections: int
    db_max_connections: int