# Resana Secure Copyright (c) 2021 Scille SAS

import os
import sys
from pathlib import Path

from resana_secure.cli import run_cli

if not sys.argv[1:]:
    sys.argv += [
        "--log-level",
        "WARNING",
        "--log-file",
        str(Path(os.environ["APPDATA"]).joinpath("resana_secure/resana_secure.log").absolute()),
    ]
run_cli()
