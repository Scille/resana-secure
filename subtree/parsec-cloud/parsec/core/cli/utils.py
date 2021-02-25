# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os
import click
from typing import List
from functools import wraps
from pathlib import Path

from parsec.logging import configure_logging, configure_sentry_logging
from parsec.core.config import get_default_config_dir, load_config
from parsec.core.local_device import (
    AvailableDevice,
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)


def core_config_options(fn):
    @click.option("--config-dir", type=click.Path(exists=True, file_okay=False))
    @click.option(
        "--log-level",
        "-l",
        default="WARNING",
        envvar="PARSEC_LOG_LEVEL",
        type=click.Choice(("DEBUG", "INFO", "WARNING", "ERROR")),
    )
    @click.option("--log-format", "-f", type=click.Choice(("CONSOLE", "JSON")))
    @click.option("--log-file", "-o")
    @wraps(fn)
    def wrapper(config_dir, *args, **kwargs):
        assert "config" not in kwargs

        configure_logging(
            log_level=kwargs["log_level"],
            log_format=kwargs["log_format"],
            log_file=kwargs["log_file"],
        )

        config_dir = Path(config_dir) if config_dir else get_default_config_dir(os.environ)
        config = load_config(config_dir, debug="DEBUG" in os.environ)

        if config.telemetry_enabled and config.sentry_url:
            configure_sentry_logging(config.sentry_url)

        kwargs["config"] = config
        return fn(**kwargs)

    return wrapper


def format_available_devices(devices: List[AvailableDevice]) -> str:
    # Try to shorten the slughash to make it easier to work with
    slughashes = [d.slughash for d in devices]
    for slughash_len in range(3, 64):
        if len({h[:slughash_len] for h in slughashes}) == len(slughashes):
            break

    out = []
    for device in devices:
        display_slughash = click.style(device.slughash[:slughash_len], fg="yellow")
        out.append(
            f"{display_slughash} - {device.organization_id}: {device.user_display} @ {device.device_display}"
        )
    return "\n".join(out)


def core_config_and_device_options(fn):
    @core_config_options
    @click.option(
        "--device",
        "-D",
        required=True,
        envvar="PARSEC_DEVICE",
        help="Device to use designed by it ID, see `list_devices` command to get the available IDs",
    )
    @click.option("--password", "-P", envvar="PARSEC_DEVICE_PASSWORD")
    @wraps(fn)
    def wrapper(**kwargs):
        config = kwargs["config"]
        password = kwargs["password"]
        device_slughash = kwargs.pop("device")

        all_available_devices = list_available_devices(config.config_dir)
        devices = []
        for device in all_available_devices:
            if device.slughash.startswith(device_slughash):
                devices.append(device)

        if not devices:
            raise SystemExit(
                f"Device `{device_slughash}` not found, available devices:\n"
                f"{format_available_devices(all_available_devices)}"
            )
        elif len(devices) > 1:
            raise SystemExit(
                f"Multiple devices found for `{device_slughash}`:\n"
                f"{format_available_devices(devices)}"
            )

        try:
            if password is None:
                password = click.prompt("password", hide_input=True)
            device = load_device_with_password(devices[0].key_file_path, password)

        except LocalDeviceError as exc:
            raise SystemExit(f"Cannot load device {device_slughash}: {exc}")

        kwargs["device"] = device
        return fn(**kwargs)

    return wrapper
