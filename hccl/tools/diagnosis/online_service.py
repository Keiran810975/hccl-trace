"""Run the online collector and an independent iteration-report worker."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, suppress
import hmac
import json
from math import isfinite
import os
from pathlib import Path
import socketserver
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

from .online_tracker import OnlineTracker
from .report_paths import load_paths, require_separate


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
                received = time.monotonic_ns()
                with self.server.lock:
                    if self.server.write_error is not None or self.server.finished:
                        return
                    now = time.monotonic_ns()
                    self.server.lock_wait_ns += now-received
                    self.server.max_lock_wait_ns = max(self.server.max_lock_wait_ns, now-received)
                    if not self.server.write_frame(row, now):
                        return
                    identity = next_identity
                    if row.get("event") == "run_end":
                        state = self.server.tracker.streams[row["rank_id"]]
                        accepted = state.session == row["session_id"] and state.valid and state.ended and state.seq == row["seq"]
                        ack = dict(event="run_end_ack", session_id=row["session_id"], seq=row["seq"], accepted=accepted)
                if row.get("event") == "run_end":
                    self.wfile.write((json.dumps(ack) + "\n").encode())
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

    def __init__(self, address, *, tracker, telemetry, events, measurements=None, health_file=None,
                 expected_ranks=None, expected_collectives=None, token=None):
        if address[0] not in {"127.0.0.1", "localhost"} and not token:
            raise ValueError("non-loopback collectors require HCCL_TRACE_ONLINE_TOKEN")
        self.tracker, self.telemetry, self.events = tracker, telemetry, events
        if measurements is not None:
            self.tracker.observe_measurement = lambda row: _write(measurements, row)
        self.health_file = health_file
        self.expected_ranks, self.expected_collectives = expected_ranks, expected_collectives
        self.finished = False
        self.lock_wait_ns = self.max_lock_wait_ns = self.ingested = 0
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

    def write_frame(self, row, now):
        try:
            _write(self.telemetry, dict(row, collector_seen_ns=now))
            try:
                self.tracker.ingest(row, now)
                self.ingested += 1
            finally:
                self.flush_events()
            if (row.get("event") == "run_end" and self.expected_ranks is not None
                    and all(self.tracker.streams.get(r) and self.tracker.streams[r].ended
                            for r in range(self.expected_ranks))):
                self.finish_run(now)
        except OSError as exc:
            self.write_error = exc
            return False
        return True

    def finish_run(self, now):
        if self.finished:
            return
        self.tracker.finish(now)
        self.flush_events()
        if self.health_file is not None:
            health = self.tracker.health(self.expected_ranks, self.expected_collectives)
            health.update(ingested_frames=self.ingested, collector_lock_wait_ns=self.lock_wait_ns,
                          collector_max_lock_wait_ns=self.max_lock_wait_ns)
            _write(self.health_file, health)
        self.finished = True

    def service_actions(self):
        with self.lock:
            if self.write_error is not None:
                raise self.write_error
            self.tracker.tick(time.monotonic_ns())
            self.flush_events()


def add_arguments(parser):
    parser.add_argument("run_id", metavar="RUN_ID", help="match capture --run-id")
    parser.add_argument("--config", type=Path, help="report path configuration (default: ./config.yaml)")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7341)
    parser.add_argument("--output", "-o", type=Path, help="override the alert directory (online_output_dir/RUN_ID)")
    parser.add_argument("--hang-timeout", type=float, default=30.)
    parser.add_argument("--heartbeat-ttl", type=float, default=5.)
    parser.add_argument("--transport-grace", type=float, default=2.)
    parser.add_argument("--baseline-window", type=int, default=20)
    parser.add_argument("--warmup-iterations", type=int, default=10)
    parser.add_argument("--expected-ranks", type=int, help="global ranks 0..N-1 for final completeness audit")
    parser.add_argument("--expected-collectives", type=int, help="total target CollOps including warmup")
    parser.add_argument("--capture", type=Path, help="finalized capture root (default: runs/RUN_ID)")
    parser.add_argument("--iteration-snapshots", type=Path, help="root containing separately sealed iter-N captures")
    reports = parser.add_mutually_exclusive_group()
    reports.add_argument("--no-detailed-reports", action="store_true", help="only write online Hang/Slow alerts")
    reports.add_argument("--report-output", type=Path, help="override online_report_output_dir/RUN_ID")
    parser.add_argument("--slow-tasks-only", action="store_true",
                        help="publish S2 task/step observations without dependency graphs or propagation")
    parser.add_argument("--task-batches", type=Path,
                        help="read sealed, exactly bound Rank task batches for incremental S2 first reports")
    parser.add_argument("--report-drain-seconds", type=float, default=120,
                        help="maximum time to drain iteration reports when the collector stops")


@contextmanager
def _report_worker(args, output, report_output, job_id):
    if report_output is None:
        yield
        return
    report_output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix="hccl-online-reports-") as temporary:
        stop = Path(temporary)/"closed"
        capture = args.capture or Path("runs")/job_id
        command = [sys.executable, "-m", "hccl.tools.diagnosis.online_reports",
                   "--directory", str(output.resolve()), "--report-directory", str(report_output.resolve()),
                   "--job-id", job_id, "--capture", str(capture.resolve()),
                   "--stop", str(stop), "--drain-seconds", str(args.report_drain_seconds),
                   "--parent-pid", str(os.getpid())]
        if args.iteration_snapshots is not None:
            command += ["--snapshots", str(args.iteration_snapshots.resolve())]
        if args.slow_tasks_only:
            command += ["--slow-tasks-only"]
        if args.task_batches is not None:
            command += ["--task-batches", str(args.task_batches.resolve())]
        if args.expected_ranks is not None:
            command += ["--expected-ranks", str(args.expected_ranks)]
        with subprocess.Popen(command, start_new_session=os.name == "posix") as worker:
            try:
                yield
            finally:
                stop.touch()
                try:
                    code = worker.wait(timeout=args.report_drain_seconds+5)
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        if os.name == "posix":
                            os.killpg(worker.pid, signal.SIGTERM)
                        else:
                            worker.terminate()
                    try:
                        worker.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        with suppress(ProcessLookupError):
                            if os.name == "posix":
                                os.killpg(worker.pid, signal.SIGKILL)
                            else:
                                worker.kill()
                        worker.wait()
                    code = worker.returncode
                    with (report_output/"diagnostics.jsonl").open("a", encoding="utf-8") as log:
                        _write(log, dict(run_id=job_id, status="worker_drain_timeout"))
                if code:
                    print(f"iteration report worker exited with {code}; raw online alerts retained", file=sys.stderr)


def run(args):
    from .multi_node_trace import _name

    job_id = _name(args.run_id)
    if args.slow_tasks_only and args.no_detailed_reports:
        raise ValueError("--slow-tasks-only requires the background report worker")
    if args.task_batches is not None and (args.no_detailed_reports or args.iteration_snapshots is not None
                                          or args.capture is not None):
        raise ValueError("--task-batches is a separate task-only input; do not combine capture or disable reports")
    paths = load_paths(args.config)
    output = args.output or paths.for_run("online", job_id)
    report_output = None
    if not args.no_detailed_reports:
        report_output = args.report_output or paths.for_run("online_reports", job_id)
        require_separate(output, report_output)
        if args.task_batches is not None:
            require_separate(output, args.task_batches)
            require_separate(report_output, args.task_batches)
        if report_output.exists() or report_output.is_symlink():
            raise FileExistsError("refusing to reuse online report directory: " + str(report_output))
    if any(v is not None and v < 1 for v in (args.expected_ranks, args.expected_collectives)):
        raise ValueError("expected counts must be positive")
    if not isfinite(args.report_drain_seconds) or not 0 <= args.report_drain_seconds <= 900:
        raise ValueError("report drain must be between 0 and 900 seconds")
    tracker = OnlineTracker(job_id, hang_timeout=args.hang_timeout,
        heartbeat_ttl=args.heartbeat_ttl, transport_grace=args.transport_grace,
        baseline_window=args.baseline_window, warmup_iterations=args.warmup_iterations)
    token = os.environ.get("HCCL_TRACE_ONLINE_TOKEN")
    if args.listen not in {"127.0.0.1", "localhost"} and not token:
        raise ValueError("non-loopback collectors require HCCL_TRACE_ONLINE_TOKEN")
    with ExitStack() as stack:
        output.mkdir(parents=True, exist_ok=False)
        telemetry = stack.enter_context((output / "telemetry.jsonl").open("x", encoding="utf-8", buffering=1))
        events = stack.enter_context((output / "events.jsonl").open("x", encoding="utf-8", buffering=1))
        measurements = stack.enter_context((output / "measurements.jsonl").open("x", encoding="utf-8", buffering=1))
        health = stack.enter_context((output / "run_health.jsonl").open("x", encoding="utf-8", buffering=1))
        server = stack.enter_context(Collector((args.listen, args.port), tracker=tracker,
            telemetry=telemetry, events=events, measurements=measurements, health_file=health,
            expected_ranks=args.expected_ranks, expected_collectives=args.expected_collectives, token=token))
        stack.enter_context(_report_worker(args, output, report_output, job_id))
        print(f"Online collector listening on {server.server_address[0]}:{server.server_address[1]}; output={output.resolve()}",
              flush=True)
        if report_output is not None:
            print(f"Online iteration reports: {report_output.resolve()}", flush=True)
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.signal(signal.SIGTERM, signal.default_int_handler)
            stack.callback(signal.signal, signal.SIGTERM, previous_handler)
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass
        finally:
            if server.write_error is None:
                with server.lock:
                    server.finish_run(time.monotonic_ns())
    return 0
