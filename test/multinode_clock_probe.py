#!/usr/bin/env python3
"""Bounded, opt-in CPU clock probes; no NPU tasks or clock-setting commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import socketserver
import threading
import time


def raw_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


class ProbeServer:
    def __init__(self, address, port, capture_id, node_id, peers):
        owner = self
        self.capture_id, self.node_id, self.peers = capture_id, node_id, set(peers)
        self.after_done = set()
        self.lock = threading.Lock()

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(5)
                while True:
                    line = self.rfile.readline(4097)
                    received = raw_ns()
                    if not line:
                        return
                    if len(line) > 4096:
                        return
                    request = json.loads(line)
                    if (request.get("capture_id") != owner.capture_id or request.get("node_id") not in owner.peers
                            or request.get("phase") not in {"before", "after", "after_done"}):
                        self.wfile.write(b'{"error":"capture/peer/phase mismatch"}\n')
                        self.wfile.flush()
                        return
                    response = dict(capture_id=owner.capture_id, reference_node=owner.node_id,
                                    sequence=request["sequence"], reference_recv_ns=received,
                                    reference_send_ns=raw_ns())
                    self.wfile.write((json.dumps(response) + "\n").encode())
                    self.wfile.flush()
                    if request["phase"] == "after_done":
                        with owner.lock:
                            owner.after_done.add(request["node_id"])

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

            def handle_error(self, request, address):
                pass  # Malformed/disconnected peers do not terminate the collector.

        self.server = Server((address, port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def wait_for_after(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.after_done == self.peers:
                    return True
            time.sleep(0.05)
        return False

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def probe_batch(address, port, capture_id, node_id, reference_node, phase, *, samples=16, timeout=30):
    if phase not in {"before", "after"} or not 4 <= samples <= 256 or timeout <= 0:
        raise ValueError("invalid clock probe configuration")
    deadline = time.monotonic() + timeout
    while True:
        try:
            connection = socket.create_connection((address, port), timeout=min(timeout, 5))
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    records = []
    with connection:
        connection.settimeout(min(timeout, 5))
        with connection.makefile("rwb") as stream:
            for sequence in range(samples + (phase == "after")):
                request = dict(capture_id=capture_id, node_id=node_id, sequence=sequence,
                               phase="after_done" if sequence == samples else phase)
                encoded = (json.dumps(request) + "\n").encode()
                start = raw_ns()
                stream.write(encoded)
                stream.flush()
                line = stream.readline(4097)
                stop = raw_ns()
                if len(line) > 4096 or not line:
                    raise ValueError("invalid clock probe response")
                reply = json.loads(line)
                if (reply.get("capture_id") != capture_id or reply.get("reference_node") != reference_node
                        or reply.get("sequence") != sequence or "error" in reply):
                    raise ValueError("clock probe response identity mismatch")
                if sequence < samples:
                    records.append(dict(local_send_ns=start, local_recv_ns=stop,
                        reference_recv_ns=reply["reference_recv_ns"], reference_send_ns=reply["reference_send_ns"]))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("serve", "probe"))
    parser.add_argument("--address", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--reference-node", default="node0")
    parser.add_argument("--peers", default="")
    parser.add_argument("--phase", choices=("before", "after"), default="before")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite clock evidence")
    data = dict(schema_version=1, clock="CLOCK_MONOTONIC_RAW", capture_id=args.capture_id,
                node_id=args.node_id, reference_node=args.reference_node)
    if args.mode == "serve":
        if args.node_id != args.reference_node:
            parser.error("server must be the reference node")
        with ProbeServer(args.address, args.port, args.capture_id, args.node_id, args.peers.split(",")) as server:
            data["before_raw_ns"] = raw_ns()
            print("Clock probe server ready", flush=True)
            if not server.wait_for_after(args.timeout):
                raise TimeoutError("not all peers finished their after probes")
            data["after_raw_ns"] = raw_ns()
    else:
        data[args.phase] = probe_batch(args.address, args.port, args.capture_id, args.node_id,
                                      args.reference_node, args.phase, timeout=args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
