# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest

from parsec.core.fs.local_folder_fs import LocalFolderFS
from parsec.core.fs.workspacefs.file_transactions import FileTransactions
from parsec.core.fs.workspacefs.entry_transactions import EntryTransactions
from parsec.core.fs.remote_loader import RemoteLoader
from parsec.core.types import WorkspaceEntry, LocalWorkspaceManifest

from tests.common import freeze_time


@pytest.fixture
def local_folder_fs_factory(event_bus):
    def _local_folder_fs_factory(device, local_storage):
        return LocalFolderFS(device, local_storage, event_bus)

    return _local_folder_fs_factory


@pytest.fixture
def local_folder_fs(local_folder_fs_factory, alice, alice_local_storage):
    return local_folder_fs_factory(alice, alice_local_storage)


@pytest.fixture
def file_transactions_factory(event_bus, remote_devices_manager_factory):
    def _file_transactions_factory(device, local_storage, backend_cmds):
        remote_devices_manager = remote_devices_manager_factory(device)
        remote_loader = RemoteLoader(backend_cmds, remote_devices_manager, local_storage)
        return FileTransactions(local_storage, remote_loader, event_bus)

    return _file_transactions_factory


@pytest.fixture
def file_transactions(file_transactions_factory, alice, alice_local_storage, alice_backend_cmds):
    return file_transactions_factory(alice, alice_local_storage, alice_backend_cmds)


@pytest.fixture
def entry_transactions_factory(event_bus, remote_devices_manager_factory):
    def _entry_transactions_factory(device, local_storage, backend_cmds):
        remote_devices_manager = remote_devices_manager_factory(device)
        remote_loader = RemoteLoader(backend_cmds, remote_devices_manager, local_storage)

        with freeze_time("2000-01-01"):
            workspace_entry = WorkspaceEntry("test")
            workspace_manifest = LocalWorkspaceManifest(device.device_id)
        local_storage.set_dirty_manifest(workspace_entry.access, workspace_manifest)
        return EntryTransactions(device, workspace_entry, local_storage, remote_loader, event_bus)

    return _entry_transactions_factory


@pytest.fixture
def entry_transactions(entry_transactions_factory, alice, alice_local_storage, alice_backend_cmds):
    return entry_transactions_factory(alice, alice_local_storage, alice_backend_cmds)
