from __future__ import annotations

from typing import Any

from quart import Blueprint, request

from parsec.core.logged_core import LoggedCore

from ..utils import (
    APIException,
    authenticated,
    backend_errors_to_api_exceptions,
    get_user_id_from_email,
)

humans_bp = Blueprint("humans_api", __name__)


@humans_bp.route("/humans", methods=["GET"])
@authenticated
async def search_humans(core: LoggedCore) -> tuple[dict[str, Any], int]:
    bad_fields = []
    query = request.args.get("query")
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        bad_fields.append("page")
    try:
        per_page = int(request.args.get("per_page", 100))
    except (TypeError, ValueError):
        bad_fields.append("per_page")
    omit_revoked_str = request.args.get("omit_revoked", "false").lower()
    if omit_revoked_str == "true":
        omit_revoked = True
    elif omit_revoked_str == "false":
        omit_revoked = False
    else:
        bad_fields.append("omit_revoked")
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        results, total = await core.find_humans(
            query=query, page=page, per_page=per_page, omit_revoked=omit_revoked
        )

    user_info: list[dict[str, Any]] = []
    for user in results:
        assert user.human_handle is not None
        user_info.append(
            {
                "user_id": str(user.user_id),
                "human_handle": {
                    "email": user.human_handle.email,
                    "label": user.human_handle.label,
                },
                "profile": user.profile.str,
                "created_on": user.created_on.to_rfc3339(),
                "revoked_on": user.revoked_on.to_rfc3339() if user.revoked_on else None,
            }
        )
    return (
        {
            "users": user_info,
            "total": total,
        },
        200,
    )


@humans_bp.route("/humans/<string:email>/revoke", methods=["POST"])
@authenticated
async def revoke_user(core: LoggedCore, email: str) -> tuple[dict[str, Any], int]:
    with backend_errors_to_api_exceptions():
        user_id = await get_user_id_from_email(core, email, omit_revoked=True)
        if not user_id:
            raise APIException(404, {"error": "unknown_email"})

        await core.revoke_user(user_id=user_id)

    return {}, 200
