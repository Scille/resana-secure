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
from parsec._parsec import SequesterVerifyKeyDer
from parsec.core.types import BackendOrganizationBootstrapAddr
from parsec.api.protocol import HumanHandle, DeviceLabel
from parsec.core.local_device import save_device_with_password_in_config
from ..utils import APIException, backend_errors_to_api_exceptions, check_data
from ..app import current_app

organization_bp = Blueprint("organization_api", __name__)


@organization_bp.route("/organization/bootstrap", methods=["POST"])
async def organization_bootstrap() -> tuple[dict[str, Any], int]:
    async with check_data() as (data, bad_fields):
        email = data.get("email")
        try:
            human_handle = HumanHandle(label="-unknown-", email=email)
        except (ValueError, TypeError):
            # We provide the label ourselve, error can only mean an invalid email
            bad_fields.add("email")
        password = data.get("key")
        if not isinstance(password, str):
            bad_fields.add("key")
        organization_url = data.get("organization_url")
        try:
            backend_addr = BackendOrganizationBootstrapAddr.from_url(organization_url)
        except ValueError:
            bad_fields.add("organization_url")
        sequester_key = data.get("sequester_verify_key")
        if sequester_key:
            try:
                sequester_key = SequesterVerifyKeyDer(base64.b64decode(sequester_key))
            except (ValueError, TypeError, binascii.Error):
                bad_fields.add("sequester_verify_key")

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
