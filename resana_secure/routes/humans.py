from quart import Blueprint, request

from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
)

from ..utils import authenticated, check_data, APIException


humans_bp = Blueprint("humans_api", __name__)


@humans_bp.route("/humans", methods=["GET"])
@authenticated
async def search_humans(core):
    async with check_data() as (_, bad_fields):
        query = request.args.get("query")
        try:
            page = int(request.args.get("page", 1))
        except TypeError:
            bad_fields.append("page")
        try:
            per_page = int(request.args.get("per_page", 100))
        except TypeError:
            bad_fields.append("per_page")
        omit_revoked = request.args.get("omit_revoked", "false").lower()
        if omit_revoked == "true":
            omit_revoked = True
        elif omit_revoked == "false":
            omit_revoked = False
        else:
            bad_fields.append("omit_revoked")

    try:
        results, total = await core.find_humans(
            query=query, page=page, per_page=per_page, omit_revoked=omit_revoked
        )

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return (
        {
            "users": [
                {
                    "user_id": user.user_id.hex,
                    "human_handle": {
                        "email": user.human_handle.email,
                        "label": user.human_handle.label,
                    },
                    "profile": user.profile.value,
                    "created_on": user.created_on.to_iso8601_string(),
                    "revoked_on": user.revoked_on.to_iso8601_string(),
                }
                for user in results
            ],
            "total": total,
        },
        200,
    )


@humans_bp.route("/humans/<string:email>/revoke", methods=["POST"])
async def revoke_user(core, email):
    try:
        results, _ = await core.find_humans(query=email, per_page=1)
        try:
            # TODO: find_humans doesn't guarantee exact match on email
            assert results[0].human_handle is not None and results[0].human_handle.email == email
            recipient = results[0].user_id
        except IndexError:
            raise APIException(404, {"error": "unknown_email"})

        await core.revoke_user(user_id=recipient)

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {}, 200
