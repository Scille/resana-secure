from pathlib import Path

import oscrypto.asymmetric
from parsec.backend.config import BaseBlockStoreConfig


class AppConfig:
    def __init__(
        self,
        authority_private_key_path: Path,
        antivirus_api_url: str,
        antivirus_api_key: str,
        blockstore_config: BaseBlockStoreConfig,
        db_url: str,
    ):
        self.authority_private_key = oscrypto.asymmetric.load_private_key(
            authority_private_key_path.read_bytes()
        )
        self.antivirus_api_url = antivirus_api_url
        self.antivirus_api_key = antivirus_api_key
        self.blockstore_config = blockstore_config
        self.db_url = db_url
