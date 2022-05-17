# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

from pathlib import Path

from parsec.core.types import LocalDevice, EntryID


STORAGE_REVISION = 1
USER_STORAGE_NAME = f"user_data-v{STORAGE_REVISION}.sqlite"
WORKSPACE_DATA_STORAGE_NAME = f"workspace_data-v{STORAGE_REVISION}.sqlite"
WORKSPACE_CACHE_STORAGE_NAME = f"workspace_cache-v{STORAGE_REVISION}.sqlite"


def get_user_data_storage_db_path(data_base_dir: Path, device: LocalDevice) -> Path:
    return data_base_dir / device.slug / USER_STORAGE_NAME


def get_workspace_data_storage_db_path(
    data_base_dir: Path, device: LocalDevice, workspace_id: EntryID
) -> Path:
    return data_base_dir / device.slug / str(workspace_id) / WORKSPACE_DATA_STORAGE_NAME


def get_workspace_cache_storage_db_path(
    data_base_dir: Path, device: LocalDevice, workspace_id: EntryID
) -> Path:
    return data_base_dir / device.slug / str(workspace_id) / WORKSPACE_CACHE_STORAGE_NAME
