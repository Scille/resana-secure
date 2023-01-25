#! /usr/bin/env python3

import os
import sys
import re
from typing import List
from json import dumps as json_dumps
from urllib.request import Request, urlopen
import argparse
import subprocess
import threading


NOTIFICATION_BASE_MSG = f"Application `{os.environ.get('APP', '<unknown app>')}` (container `{os.environ.get('CONTAINER', '<unknown container>')}`) got error/warning log:\n> "


def notify_webhook(line: str) -> None:
    data = {"text": NOTIFICATION_BASE_MSG + line}
    req = Request(
        args.webhook_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json_dumps(data).encode("utf8"),
    )
    try:
        with urlopen(req):
            pass
    except Exception as exc:
        # Not much we can do...
        print(f"Wehook error !!! cannot send message {data!r}, error: {exc!r}")


def main(cmd: List[str]) -> None:
    regex = re.compile(rb"warning|error", flags=re.IGNORECASE)

    def _listen_log_stream(stream_in, stream_out):
        while True:
            line = stream_in.readline()
            if not line:
                # Command has finished
                return
            if (
                "Database connection lost (PostgreSQL notification query has been lost), retrying in 1.0 seconds"
                in line
            ):
                continue
            stream_out.write(line)
            stream_out.flush()
            if regex.search(line):
                notify_webhook(line.decode("utf8", errors="replace"))

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        listen_stdout_thread = threading.Thread(
            target=_listen_log_stream,
            args=(proc.stdout, sys.stdout.buffer),
            daemon=True,
        )
        listen_stdout_thread.start()
        listen_stderr_thread = threading.Thread(
            target=_listen_log_stream,
            args=(proc.stderr, sys.stderr.buffer),
            daemon=True,
        )
        listen_stderr_thread.start()
        proc.wait()
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", default=os.environ.get("WEBHOOK_ON_LOGS_URL"))
    parser.add_argument("cmd", nargs="+")
    args = parser.parse_args()

    # If Webhook is not configured, do nothing
    if not args.webhook_url:

        def noop(line: str) -> None:
            pass

        globals()["notify_webhook"] = noop
        print("WARNING: Missing `webhook_url` param or `WEBHOOK_ON_LOGS_URL` environ variable !")

    main(cmd=args.cmd)
