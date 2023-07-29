from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any, cast

from quart import Blueprint, session
from quart_rate_limiter import rate_limit

from parsec.api.protocol import OrganizationID

from ..app import current_app
from ..cores_manager import (
    CoreDeviceInvalidPasswordError,
    CoreDeviceNotFoundError,
    CoreNotLoggedError,
    CoresManager,
)
from ..utils import APIException, Parser, get_auth_token, get_data

auth_bp = Blueprint("auth_api", __name__)


@auth_bp.route("/<path:subpath>", methods=["OPTIONS"])
async def do_head(subpath: str) -> tuple[dict[str, Any], int]:
    return {}, 200


@auth_bp.route("/auth", methods=["POST"])
# Limited to 2 request per second, 20 per minute
# 1 for OPTION + 1 for POST request from browser
@rate_limit(2, timedelta(seconds=1))
@rate_limit(20, timedelta(minutes=1))
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

    if (
        args["key"] is not None
        and args["encrypted_key"] is not None
        and args["user_password"] is not None
    ):
        raise APIException(400, {"error": "cannot use both authentication modes at the same time"})
    if args["key"] is None:
        if not (args["encrypted_key"] and args["user_password"]):
            raise APIException.from_bad_fields(
                ["encrypted_key"] if not args["encrypted_key"] else ["user_password"]
            )
        else:
            try:
                # Check if it's base64 but don't store the result
                base64.b64decode(args["encrypted_key"])
            except (ValueError, TypeError) as exc:
                raise APIException.from_bad_fields(["encrypted_key"]) from exc

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


@auth_bp.route("/auth/all", methods=["DELETE"])
async def remove_all_auth() -> tuple[dict[str, Any], int]:
    cores_manager = cast(CoresManager, current_app.cores_manager)
    try:
        await cores_manager.logout_all()

    except CoreNotLoggedError:
        pass

    return {}, 200
