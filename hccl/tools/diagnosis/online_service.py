"""Run the opt-in HCCL online collector. The offline CLI is independent."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hmac
import json
import os
from pathlib import Path
import socketserver
import threading
import time

from .online_tracker import OnlineTracker


MAX_FRAME = 64 * 1024


def _write(file, row):
    file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


class Handler(socketserver.StreamRequestHandler):
    timeout = 120

    def handle(self):
        identity = None
        try:
            while True:
                data = self.rfile.readline(MAX_FRAME + 1)
                if not data or len(data) > MAX_FRAME or not data.endswith(b"\n"):
                    break
                row = json.loads(data)
                if not isinstance(row, dict) or not self.server.authenticated(row.pop("auth", None)):
                    break
                next_identity = row.get("rank_id"), row.get("session_id")
                if identity is not None and next_identity != identity:
                    break
                with self.server.lock:
                    if self.server.write_error is not None:
                        return
                    now = time.monotonic_ns()
                    self.server.tracker.ingest(row, now)
                    identity = next_identity
                    if not self.server.write_frame(dict(row, collector_seen_ns=now)):
                        return
        except (OSError, ValueError, RecursionError):
            # Invalid or disconnected streams cannot prove H1.
            pass
        finally:
            if identity is not None:
                with self.server.lock:
                    self.server.tracker.disconnect(*identity)


class Collector(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, *, tracker, telemetry, events, token=None):
        if address[0] not in {"127.0.0.1", "localhost"} and not token:
            raise ValueError("non-loopback collectors require HCCL_TRACE_ONLINE_TOKEN")
        self.tracker, self.telemetry, self.events = tracker, telemetry, events
        self.token = token.encode() if token else None
        self.lock = threading.Lock()
        self.write_error = None
        super().__init__(address, Handler)

    def authenticated(self, candidate):
        if self.token is None:
            return True
        return isinstance(candidate, str) and hmac.compare_digest(self.token, candidate.encode())

    def flush_events(self):
        for row in self.tracker.drain():
            _write(self.events, row)

    def write_frame(self, row):
        try:
            _write(self.telemetry, row)
            self.flush_events()
        except OSError as exc:
            self.write_error = exc
            return False
        return True

    def service_actions(self):
        with self.lock:
            if self.write_error is not None:
                raise self.write_error
            self.tracker.tick(time.monotonic_ns())
            self.flush_events()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7341)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hang-timeout", type=float, default=30.)
    parser.add_argument("--heartbeat-ttl", type=float, default=5.)
    parser.add_argument("--transport-grace", type=float, default=2.)
    parser.add_argument("--baseline-window", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        tracker = OnlineTracker(args.job_id, hang_timeout=args.hang_timeout,
            heartbeat_ttl=args.heartbeat_ttl, transport_grace=args.transport_grace,
            baseline_window=args.baseline_window)
        token = os.environ.get("HCCL_TRACE_ONLINE_TOKEN")
        if args.listen not in {"127.0.0.1", "localhost"} and not token:
            raise ValueError("non-loopback collectors require HCCL_TRACE_ONLINE_TOKEN")
        with ExitStack() as stack:
            args.output.mkdir(parents=True, exist_ok=False)
            telemetry = stack.enter_context((args.output / "telemetry.jsonl").open("x", encoding="utf-8", buffering=1))
            events = stack.enter_context((args.output / "events.jsonl").open("x", encoding="utf-8", buffering=1))
            server = stack.enter_context(Collector((args.listen, args.port), tracker=tracker,
                                                    telemetry=telemetry, events=events, token=token))
            print(f"Online collector listening on {server.server_address[0]}:{server.server_address[1]}", flush=True)
            try:
                server.serve_forever(poll_interval=.2)
            except KeyboardInterrupt:
                pass
    except (OSError, ValueError, OverflowError) as exc:
        parser.exit(1, f"collector: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
