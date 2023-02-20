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
from ..utils import APIException, get_auth_token, get_data, Parser
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
    parser = Parser()
    parser.add_argument("email", type=str, required=True)
    parser.add_argument("key", type=str)
    parser.add_argument("encrypted_key", type=str)
    parser.add_argument("user_password", type=str)
    parser.add_argument("organization", converter=OrganizationID)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    if args["key"] and args["encrypted_key"] and args["user_password"]:
        raise APIException(400, {"error": "cannot use both authentication modes at the same time"})
    if not args["encrypted_key"] and not args["user_password"]:
        if not isinstance(args["key"], str):
            raise APIException.from_bad_fields(["key"])
    elif args["encrypted_key"] and args["user_password"]:
        try:
            # Check if it's base64 but don't store the result
            base64.b64decode(args["encrypted_key"])
        except (ValueError, TypeError):
            raise APIException.from_bad_fields(["encrypted_key"])
        if not isinstance(args["user_password"], str):
            raise APIException.from_bad_fields(["user_password"])
    else:
        raise APIException.from_bad_fields(
            ["encrypted_key"] if not args["encrypted_key"] else ["user_password"]
        )

    cores_manager = cast(CoresManager, current_app.cores_manager)
    try:
        auth_token = await cores_manager.login(
            email=args["email"],
            key=args["key"],
            user_password=args["user_password"],
            encrypted_key=args["encrypted_key"],
            organization_id=args["organization"],
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
