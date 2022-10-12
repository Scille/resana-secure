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
import signal


NOTIFICATION_BASE_MSG = (
    f"Application `{os.environ.get('APP', '<unknown app>')}` (container `{os.environ.get('CONTAINER', '<unknown container>')}`) got error/warning log:\n> "
)


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


def run_cmd_with_log_scan(cmd: List[str]) -> subprocess.Popen:
    regex = re.compile(rb"warning|error", flags=re.IGNORECASE)

    def _listen_log_stream(stream_in, stream_out):
        while True:
            line = stream_in.readline()
            if not line:
                # Command has finished
                return
            stream_out.write(line)
            stream_out.flush()
            if regex.search(line):
                notify_webhook(line.decode("utf8", errors="replace"))

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
    return proc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", default=os.environ.get("WEBHOOK_ON_LOGS_URL"))
    args = parser.parse_args()

    if not args.webhook_url:
        def noop(line: str) -> None:
            pass
        globals()["notify_webhook"] = noop
        print(
            "WARNING: Missing `webhook_url` param or `WEBHOOK_ON_LOGS_URL` environ variable !"
        )

    # SIGTERM is triggered when the app needs to stop, so we give it the same
    # behavior as SIGINT (i.e. raising a KeyboardInterrupt)
    def sigterm_handler(_signo, _stack_frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sigterm_handler)

    parsec_proc = run_cmd_with_log_scan(["parsec", "backend", "run"])
    antivirus_proc = run_cmd_with_log_scan(["python", "-m", "antivirus_connector", "--port", "5775"])

    try:
        parsec_proc.wait()
        antivirus_proc.wait()
    except (KeyboardInterrupt, EOFError):
        # If we are here, we are required to finish asap
        parsec_proc.terminate()
        antivirus_proc.terminate()
        parsec_proc.wait()
        antivirus_proc.wait()
