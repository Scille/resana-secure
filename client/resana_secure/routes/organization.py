from __future__ import annotations

from quart import Blueprint

from typing import Any

import platform
import binascii
import base64

from parsec.core.invite import (
    bootstrap_organization,
    InviteNotFoundError,
    InviteAlreadyUsedError,
)
from parsec._parsec import SequesterVerifyKeyDer, save_device_with_password_in_config
from parsec.core.types import BackendOrganizationBootstrapAddr
from parsec.core.fs.storage.user_storage import user_storage_non_speculative_init
from parsec.api.protocol import HumanHandle, DeviceLabel
from ..utils import APIException, backend_errors_to_api_exceptions, get_data, Parser
from ..app import current_app

organization_bp = Blueprint("organization_api", __name__)


@organization_bp.route("/organization/bootstrap", methods=["POST"])
async def organization_bootstrap() -> tuple[dict[str, Any], int]:
    data = await get_data()
    parser = Parser()
    parser.add_argument("email", type=str, required=True)
    parser.add_argument("key", type=str, new_name="password", required=True)
    parser.add_argument(
        "organization_url",
        converter=BackendOrganizationBootstrapAddr.from_url,
        required=True,
    )
    parser.add_argument("sequester_verify_key", type=str)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    try:
        human_handle = HumanHandle(label="-unknown-", email=args["email"])
    except (ValueError, TypeError) as exc:
        raise APIException.from_bad_fields(["email"]) from exc
    if args["sequester_verify_key"]:
        try:
            sequester_key = SequesterVerifyKeyDer(base64.b64decode(args["sequester_verify_key"]))
        except (ValueError, TypeError, binascii.Error) as exc:
            raise APIException.from_bad_fields(["sequester_verify_key"]) from exc
    else:
        sequester_key = None

    try:
        device_label = DeviceLabel(platform.node() or "-unknown-")
    except ValueError:
        device_label = DeviceLabel("-unknown-")

    with backend_errors_to_api_exceptions():
        try:
            new_device = await bootstrap_organization(
                args["organization_url"],
                human_handle=human_handle,
                device_label=device_label,
                sequester_authority_verify_key=sequester_key,
            )
            # The organization is brand new, of course there is no existing
            # remote user manifest, hence our placeholder is non-speculative.
            await user_storage_non_speculative_init(
                data_base_dir=current_app.resana_config.core_config.data_base_dir,
                device=new_device,
            )
            save_device_with_password_in_config(
                config_dir=current_app.resana_config.core_config.config_dir,
                device=new_device,
                password=args["password"],
            )
        except InviteAlreadyUsedError:
            raise APIException(400, {"error": "organization_already_bootstrapped"})
        except InviteNotFoundError:
            raise APIException(404, {"error": "unknown_organization"})

    return {}, 200
