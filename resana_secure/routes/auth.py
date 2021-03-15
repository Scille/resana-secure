from base64 import b64decode
from quart import Blueprint, current_app, session

from ..cores_manager import CoreNotLoggedError, CoreDeviceNotFoundError, CoreDeviceInvalidKeyError
from ..utils import check_data, APIException, get_auth_token


auth_bp = Blueprint("auth_api", __name__)


@auth_bp.route("/<path:subpath>", methods=["OPTIONS"])
async def do_head(subpath):
    return {}, 200


@auth_bp.route("/auth", methods=["POST"])
async def do_auth():
    async with check_data() as (data, bad_fields):
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        key = data.get("key")
        try:
            key = b64decode(key)
        except (TypeError, ValueError):
            bad_fields.add("key")

    try:
        auth_token = await current_app.cores_manager.login(email=email, key=key)

    except CoreDeviceNotFoundError:
        raise APIException(404, {"error": "bad_email"})
    except CoreDeviceInvalidKeyError:
        raise APIException(400, {"error": "bad_key"})

    session["logged_in"] = auth_token
    return {"token": auth_token}, 200


@auth_bp.route("/auth", methods=["DELETE"])
async def remove_auth():
    auth_token = get_auth_token()
    if not auth_token:
        return {}, 200
    session.pop("logged_in")
    try:
        auth_token = await current_app.cores_manager.logout(auth_token=auth_token)

    except CoreNotLoggedError:
        pass

    return {}, 200
