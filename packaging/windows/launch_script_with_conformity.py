# Resana Secure Copyright (c) 2021 Scille SAS

import json
import multiprocessing
import os
import sys
from pathlib import Path

# Enable freeze support for supporting the multiprocessing module
# This is useful for running qt dialogs in subprocesses.
# We do this before even importing third parties in order to increase performance.
multiprocessing.freeze_support()


from resana_secure.cli import run_cli

config_dir = (Path(os.environ["APPDATA"]) / "resana_secure").absolute()
log_file = config_dir / "resana_secure.log"

# Config file is just a convoluted way of passing params to sys.argv
args = sys.argv[1:]
args.append("--check-conformity")
config_file_path = config_dir / "config.json"
try:
    conf = json.loads(config_file_path.read_text())
    if isinstance(conf, dict):
        for key, value in conf.items():
            if isinstance(key, str) and isinstance(value, str):
                args.append(f"--{key.replace('_', '-')}")
                args.append(value)
except FileNotFoundError:
    pass
except (OSError, json.JSONDecodeError) as exc:
    try:
        with open(log_file, "a") as fd:
            fd.write(f"Ignoring invalid configuration file {config_file_path}: {repr(exc)}\n")
    except Exception:
        pass

run_cli(args=args, default_log_level="WARNING", default_log_file=log_file)
