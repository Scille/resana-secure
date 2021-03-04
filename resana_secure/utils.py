from functools import wraps
from contextlib import asynccontextmanager
from quart import jsonify, Response, current_app, session, request
from quart.exceptions import HTTPException
from werkzeug.routing import BaseConverter

from .cores_manager import CoreNotLoggedError


class EntryIDConverter(BaseConverter):
    def to_python(self, value):
        return super().to_python(value)

    def to_url(self, value) -> str:
        return super().to_url(value)


class APIException(HTTPException):
    def __init__(self, status_code, data) -> None:
        super().__init__(status_code, "", "")
        self.data = data

    def get_response(self) -> Response:
        response = jsonify(self.data)
        response.status_code = self.status_code
        return response


def authenticated(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        # global auth_token
        is_auth = session.get("logged_in", "")
        try:
            async with current_app.cores_manager.get_core(is_auth) as core:
                return await fn(*args, core=core, **kwargs)
        except CoreNotLoggedError:
            raise APIException(401, {"error": "authentication_requested"})

    return wrapper


@asynccontextmanager
async def check_data():
    if not request.is_json:
        raise APIException(400, {"error": "json_body_expected"})
    data = await request.get_json()
    bad_fields = set()
    yield data, bad_fields
    if bad_fields:
        raise APIException(400, {"error": "bad_data", "fields": list(bad_fields)})
