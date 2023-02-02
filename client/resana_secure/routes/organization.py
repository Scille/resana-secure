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
from parsec.api.protocol import HumanHandle, DeviceLabel
from ..utils import APIException, backend_errors_to_api_exceptions, get_data, parse_arg, BadField
from ..app import current_app

organization_bp = Blueprint("organization_api", __name__)


@organization_bp.route("/organization/bootstrap", methods=["POST"])
async def organization_bootstrap() -> tuple[dict[str, Any], int]:
    data = await get_data()
    email = parse_arg(data, "email", type=str)
    password = parse_arg(data, "key", type=str)
    backend_addr = parse_arg(
        data,
        "organization_url",
        type=BackendOrganizationBootstrapAddr,
        convert=BackendOrganizationBootstrapAddr.from_url,
    )
    sequester_key_raw = parse_arg(data, "sequester_verify_key", type=str, missing=None)
    if (
        isinstance(email, BadField)
        or isinstance(password, BadField)
        or isinstance(backend_addr, BadField)
        or isinstance(sequester_key_raw, BadField)
    ):
        raise APIException.from_bad_fields([email, password, backend_addr, sequester_key_raw])

    try:
        human_handle = HumanHandle(label="-unknown-", email=email)
    except (ValueError, TypeError):
        raise APIException.from_bad_fields([BadField(name="email")])
    if sequester_key_raw:
        try:
            sequester_key = SequesterVerifyKeyDer(base64.b64decode(sequester_key_raw))
        except (ValueError, TypeError, binascii.Error):
            raise APIException.from_bad_fields([BadField(name="sequester_verify_key")])
    else:
        sequester_key = None

    try:
        device_label = DeviceLabel(platform.node() or "-unknown-")
    except ValueError:
        device_label = DeviceLabel("-unknown-")

    with backend_errors_to_api_exceptions():
        try:
            new_device = await bootstrap_organization(
                backend_addr,
                human_handle=human_handle,
                device_label=device_label,
                sequester_authority_verify_key=sequester_key,
            )
            save_device_with_password_in_config(
                config_dir=current_app.resana_config.core_config.config_dir,
                device=new_device,
                password=password,
            )
        except InviteAlreadyUsedError:
            raise APIException(400, {"error": "organization_already_bootstrapped"})
        except InviteNotFoundError:
            raise APIException(404, {"error": "unknown_organization"})

    return {}, 200
