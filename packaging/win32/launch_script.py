# Resana Secure Copyright (c) 2021 Scille SAS

import os
import sys
import json
from pathlib import Path

from resana_secure.cli import run_cli


config_dir = (Path(os.environ["APPDATA"]) / "resana_secure").absolute()
log_file = config_dir / "resana_secure.log"

# Config file is just a convoluted way of passing params to sys.argv
args = sys.argv[1:]
try:
    conf = json.loads((config_dir / "config.json").read_text())
    if isinstance(conf, dict):
        for key, value in conf.items():
            if isinstance(key, str) and isinstance(value, str):
                args.append(f"--{key.replace('_', '-')}")
                args.append(value)
except (OSError, json.JSONDecodeError):
    pass


run_cli(args=args, default_log_level="WARNING", default_log_file=log_file)
