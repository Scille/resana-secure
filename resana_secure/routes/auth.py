from base64 import b64decode
from quart import Blueprint, current_app, session

from ..cores_manager import CoreAlreadyLoggedError, CoreUnknownEmailError
from ..utils import check_data, APIException


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
        auth_token = await current_app.cores_manager.loggin(email=email, key=key)
    except CoreUnknownEmailError:
        raise APIException(404, {"error": "bad_auth"})
    except CoreAlreadyLoggedError:
        raise APIException(404, {"error": "already_authenticated"})
    session["logged_in"] = auth_token
    return {}, 200
