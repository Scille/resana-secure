from __future__ import annotations

from werkzeug.routing import BaseConverter

from parsec.api.data import EntryID

from .utils import APIException


class WorkspaceConverter(BaseConverter):
    def to_python(self, value: str) -> EntryID:
        try:
            workspace_id = EntryID.from_hex(value)
        except ValueError:
            raise APIException(404, {"error": "unknown_workspace"})
        return workspace_id

    def to_url(self, value: str) -> str:
        return value
