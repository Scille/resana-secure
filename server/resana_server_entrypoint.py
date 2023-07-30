#! /usr/bin/env python3

import argparse
import os
import queue
import re
import signal
import subprocess
import sys
import threading
from json import dumps as json_dumps
from typing import List
from urllib.request import Request, urlopen

NOTIFICATION_BASE_MSG = f"Application `{os.environ.get('APP', '<unknown app>')}` (container `{os.environ.get('CONTAINER', '<unknown container>')}`) got error/warning log:\n> "


def notify_webhook(args: argparse.Namespace, line: str) -> None:
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


def run_cmd_with_log_scan(args: argparse.Namespace, cmd: List[str]) -> subprocess.Popen:
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
                notify_webhook(args, line.decode("utf8", errors="replace"))

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", default=os.environ.get("WEBHOOK_ON_LOGS_URL"))
    args = parser.parse_args()

    if not args.webhook_url:

        def noop(args: argparse.Namespace, line: str) -> None:
            pass

        globals()["notify_webhook"] = noop
        print("WARNING: Missing `webhook_url` param or `WEBHOOK_ON_LOGS_URL` environ variable !")

    # SIGTERM is triggered when the app needs to stop, so we give it the same
    # behavior as SIGINT (i.e. raising a KeyboardInterrupt)
    def sigterm_handler(_signo, _stack_frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, sigterm_handler)

    # Run the services

    parsec_proc = run_cmd_with_log_scan(args, ["python", "-m", "resana_backend_run"])
    antivirus_proc = run_cmd_with_log_scan(
        args, ["python", "-m", "antivirus_connector", "--port", "5775"]
    )

    # Run threads to monitor the service...

    procs = (parsec_proc, antivirus_proc)
    proc_queue: queue.Queue[subprocess.Popen] = queue.Queue()

    def _watch_process(proc: subprocess.Popen) -> None:
        proc.wait()
        proc_queue.put(proc)

    for proc in procs:
        threading.Thread(
            target=_watch_process,
            args=(proc,),
            daemon=True,
        ).start()

    # ...wait until a service is stopped, and stop the rest

    try:
        proc_queue.get()
    except KeyboardInterrupt:
        pass

    ret = 0
    for proc in procs:
        proc.terminate()
        proc.wait()
        ret |= proc.returncode

    raise SystemExit(ret)


if __name__ == "__main__":
    main()
