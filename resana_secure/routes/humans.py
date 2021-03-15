from quart import Blueprint, request

from ..utils import authenticated, backend_errors_to_api_exceptions, APIException


humans_bp = Blueprint("humans_api", __name__)


@humans_bp.route("/humans", methods=["GET"])
@authenticated
async def search_humans(core):
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
    omit_revoked = request.args.get("omit_revoked", "false").lower()
    if omit_revoked == "true":
        omit_revoked = True
    elif omit_revoked == "false":
        omit_revoked = False
    else:
        bad_fields.append("omit_revoked")
    if bad_fields:
        raise APIException(400, {"error": "bad_arguments", "fields": list(bad_fields)})

    with backend_errors_to_api_exceptions():
        results, total = await core.find_humans(
            query=query, page=page, per_page=per_page, omit_revoked=omit_revoked
        )

    return (
        {
            "users": [
                {
                    "user_id": str(user.user_id),
                    "human_handle": {
                        "email": user.human_handle.email,
                        "label": user.human_handle.label,
                    },
                    "profile": user.profile.value,
                    "created_on": user.created_on.to_iso8601_string(),
                    "revoked_on": user.revoked_on.to_iso8601_string() if user.revoked_on else None,
                }
                for user in results
            ],
            "total": total,
        },
        200,
    )


@humans_bp.route("/humans/<string:email>/revoke", methods=["POST"])
@authenticated
async def revoke_user(core, email):
    with backend_errors_to_api_exceptions():
        results, _ = await core.find_humans(query=email)
        # find_humans doesn't guarantee exact match on email, so manually filter just to be sure
        recipient = next(
            (
                r.user_id
                for r in results
                if r.human_handle is not None and r.human_handle.email == email
            ),
            None,
        )
        if not recipient:
            raise APIException(404, {"error": "unknown_email"})

        await core.revoke_user(user_id=recipient)

    return {}, 200
