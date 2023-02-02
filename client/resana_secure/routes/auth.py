from __future__ import annotations

from typing import cast, Any
from quart import Blueprint, session
from datetime import timedelta
from quart_rate_limiter import rate_limit
import base64

from parsec.api.protocol import OrganizationID
from ..cores_manager import (
    CoresManager,
    CoreNotLoggedError,
    CoreDeviceNotFoundError,
    CoreDeviceInvalidPasswordError,
)
from ..utils import APIException, get_auth_token, get_data, parse_arg, BadField
from ..app import current_app


auth_bp = Blueprint("auth_api", __name__)


@auth_bp.route("/<path:subpath>", methods=["OPTIONS"])
async def do_head(subpath: str) -> tuple[dict[str, Any], int]:
    return {}, 200


@auth_bp.route("/auth", methods=["POST"])
# Limited to 1 request per second, 10 per minute
@rate_limit(1, timedelta(seconds=1))
@rate_limit(10, timedelta(minutes=1))
async def do_auth() -> tuple[dict[str, Any], int]:
    # Either send a non-encrypted Parsec Key using the field `key`
    # or send the encrypted Parsec Key with the field `encrypted_key` and
    # the user password with the field `user_password`.
    data = await get_data()
    email = parse_arg(data, "email", type=str)
    key = parse_arg(data, "key", type=str, missing=None)
    encrypted_key = parse_arg(data, "encrypted_key", type=str, missing=None)
    user_password = parse_arg(data, "user_password", type=str, missing=None)
    organization_id = parse_arg(
        data, "organization", type=OrganizationID, convert=OrganizationID, missing=None
    )
    if (
        isinstance(email, BadField)
        or isinstance(key, BadField)
        or isinstance(encrypted_key, BadField)
        or isinstance(user_password, BadField)
        or isinstance(organization_id, BadField)
    ):
        raise APIException.from_bad_fields([key, encrypted_key, user_password, organization_id])
    if key and encrypted_key and user_password:
        raise APIException(400, {"error": "cannot use both authentication modes at the same time"})
    if not encrypted_key and not user_password:
        if not isinstance(key, str):
            raise APIException.from_bad_fields([BadField(name="key")])
    elif encrypted_key and user_password:
        try:
            # Check if it's base64 but don't store the result
            base64.b64decode(encrypted_key)
        except (ValueError, TypeError):
            raise APIException.from_bad_fields([BadField(name="encrypted_key")])
        if not isinstance(user_password, str):
            raise APIException.from_bad_fields([BadField(name="user_password")])
    else:
        raise APIException.from_bad_fields(
            [BadField(name="encrypted_key")]
            if not encrypted_key
            else [BadField(name="user_password")]
        )

    cores_manager = cast(CoresManager, current_app.cores_manager)
    try:
        auth_token = await cores_manager.login(
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
async def remove_auth() -> tuple[dict[str, Any], int]:
    auth_token = get_auth_token()
    if not auth_token:
        return {}, 200
    session.pop("logged_in", None)
    cores_manager = cast(CoresManager, current_app.cores_manager)
    try:
        await cores_manager.logout(auth_token=auth_token)

    except CoreNotLoggedError:
        pass

    return {}, 200
