from quart import Blueprint, current_app, session
import base64

from ..cores_manager import (
    CoreNotLoggedError,
    CoreDeviceNotFoundError,
    CoreDeviceInvalidPasswordError,
)
from ..utils import check_data, APIException, get_auth_token
from parsec.api.protocol import OrganizationID


auth_bp = Blueprint("auth_api", __name__)


@auth_bp.route("/<path:subpath>", methods=["OPTIONS"])
async def do_head(subpath):
    return {}, 200


@auth_bp.route("/auth", methods=["POST"])
async def do_auth():
    # Either send a non-encrypted Parsec Key using the field `key`
    # or send the encrypted Parsec Key with the field `encrypted_key` and
    # the user password with the field `user_password`.

    async with check_data() as (data, bad_fields):
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        key = data.get("key")
        encrypted_key = data.get("encrypted_key")
        user_password = data.get("user_password")
        if key and encrypted_key and user_password:
            raise APIException(
                400, {"error": "cannot use both authentication modes at the same time"}
            )
        # In this case we default to `key` being the required one
        if not encrypted_key and not user_password:
            if not isinstance(key, str):
                bad_fields.add("key")
        else:
            try:
                # Check if it's base64 but don't store the result
                base64.b64decode(encrypted_key)
            except (ValueError, TypeError):
                bad_fields.add("encrypted_key")
            if not isinstance(user_password, str):
                bad_fields.add("user_password")

        organization_id = data.get("organization")
        if organization_id is not None:
            try:
                organization_id = OrganizationID(organization_id)
            except (NameError, TypeError, ValueError):
                bad_fields.add("organization")

    try:
        auth_token = await current_app.cores_manager.login(
            email=email,
            key=key,
            user_password=user_password,
            encrypted_key=encrypted_key,
            organization_id=organization_id,
        )

    except CoreDeviceNotFoundError:
        raise APIException(404, {"error": "device_not_found"})
    except CoreDeviceInvalidPasswordError:
        raise APIException(400, {"error": "bad_key"})

    session["logged_in"] = auth_token
    return {"token": auth_token}, 200


@auth_bp.route("/auth", methods=["DELETE"])
async def remove_auth():
    auth_token = get_auth_token()
    if not auth_token:
        return {}, 200
    session.pop("logged_in", None)
    try:
        auth_token = await current_app.cores_manager.logout(auth_token=auth_token)

    except CoreNotLoggedError:
        pass

    return {}, 200
