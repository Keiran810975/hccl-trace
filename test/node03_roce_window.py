"""One real Node0/NPU4 RoCE shaping window with a separate rollback timer."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

# The frozen timer copy lives under network/, rather than src/test/.
if Path(__file__).parent.name == "network":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/test"))
if __package__:
    from .node03_device_guard import scope, write
    from .roce_shaping_smoke import TOOL, parse_shaping
else:
    from node03_device_guard import scope, write
    from roce_shaping_smoke import TOOL, parse_shaping


DEVICE, SIBLING, LIMIT = 9, 8, 20000
COUNTERS = ("mac_tx_total_oct_num", "mac_rx_total_oct_num", "roce_tx_all_pkt_num", "roce_rx_all_pkt_num")


def raw_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


def counters(text):
    values = {}
    for line in text.splitlines():
        key, colon, value = line.partition(":")
        if key in COUNTERS:
            if key in values or not colon or not value.strip().isdigit():
                raise ValueError("invalid or duplicated native RoCE counter")
            values[key] = int(value)
    if set(values) != set(COUNTERS):
        raise ValueError("required native RoCE counters are missing")
    return values


def baseline_active(evidence):
    if (evidence.get("node_id") != "node0" or evidence.get("user_rank") != 0
            or evidence.get("physical_device_id") != DEVICE or evidence.get("runtime_device_id") != 1
            or not evidence.get("foreground_only") or not evidence.get("numerics_passed")):
        raise ValueError("verified foreground-only baseline port identity required")
    before, after = evidence["before"], evidence["after"]
    if (any(after[k] < before[k] for k in COUNTERS)
            or after["mac_tx_total_oct_num"] - before["mac_tx_total_oct_num"] < 1024**2
            or after["roce_tx_all_pkt_num"] <= before["roce_tx_all_pkt_num"]):
        raise ValueError("baseline does not prove an active outgoing RoCE foreground port")


def card_processes(text, card):
    at = text.lower().find("process id")
    if at < 0:
        raise ValueError("no authoritative NPU process report")
    found = set()
    for cells in csv.reader(text[at:].splitlines(), delimiter="|"):
        cells = [s.strip() for s in cells if s.strip()]
        if not cells:
            continue
        identity = cells[0].split()
        if len(identity) == 2 and all(s.isdigit() for s in identity) and int(identity[0]) == card:
            if len(cells) > 1 and cells[1].isdigit():
                found.add(int(cells[1]))
        elif len(identity) >= 3 and all(s.isdigit() for s in identity[:3]) and int(identity[0]) == card:
            found.add(int(identity[2]))
    return found


class Window:
    def __init__(self, root):
        self.root = scope(root)
        if socket.gethostname().split(".")[0] != "liteserver-560t-0":
            raise ValueError("network shaping scope is only the allocated Node0 physical port9")
        self.directory = self.root / "network"
        self.control = self.root / "gpt-output/private"
        self.snapshot = self.directory / "snapshot.json"

    def run(self, command, check=True):
        result = subprocess.run(command, text=True, capture_output=True, timeout=20)
        if self.directory.is_dir():
            with (self.directory / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(command=command, returncode=result.returncode, stdout=result.stdout,
                    stderr=result.stderr, raw_ns=raw_ns())) + "\n")
        if check and result.returncode:
            raise RuntimeError("network guard command failed: " + result.stderr[-800:] + result.stdout[-800:])
        return result.stdout

    def query(self):
        return counters(self.run([TOOL, "-i", str(DEVICE), "-stat", "-g"]))

    def shaping(self, device):
        return parse_shaping(self.run([TOOL, "-i", str(device), "-shaping", "-g"]))

    def set(self, device, limit):
        if device not in {DEVICE, SIBLING}:
            raise ValueError("network port outside the authorized owned card")
        self.run([TOOL, "-i", str(device), "-shaping", "-s", "bw_limit", str(limit)])

    def stop_timer(self, unit):
        self.run(["systemctl", "stop", unit + ".timer"], check=False)
        if self.run(["systemctl", "is-active", unit + ".timer"], check=False).strip() not in {"inactive", "unknown"}:
            raise RuntimeError("network recovery timer is still active")

    def restore(self):
        state = json.loads(self.snapshot.read_text())
        if state["device"] != DEVICE or state["sibling"] != SIBLING or state["limit_mbps"] != LIMIT:
            raise ValueError("network restoration scope mismatch")
        for device in (DEVICE, SIBLING):
            original = state["original"][str(device)]
            current = self.shaping(device)
            if current != original:
                if current["limit_mbps"] != LIMIT or current["maximum_mbps"] != original["maximum_mbps"]:
                    raise RuntimeError("unknown concurrent port configuration; refusing to clobber it")
                self.set(device, original["limit_mbps"])
            if self.shaping(device) != original:
                raise RuntimeError("network port did not restore")
        write(self.directory / "restored.json", dict(restored_verified=True, finished_raw_ns=raw_ns()))

    def own_processes(self):
        expected = []
        for path in (self.root / "hold/device-1.json", self.root / "gpt-output/runtime/rank-0.json"):
            expected.append(json.loads(path.read_text())["pid"])
        text = self.run(["npu-smi", "info"])
        observed = card_processes(text, 4)
        if not observed or not observed <= set(expected):
            raise ValueError("unknown process on the shared target whole card; do not shape it")

    def watch(self):
        evidence = json.loads((self.root / "input/network-baseline.json").read_text())
        baseline_active(evidence)
        config = json.loads((self.root / "input/case.json").read_text())["injection"]
        if (config["kind"] != "bandwidth_limit" or config["target_rank"] != 0 or config["limit_mbps"] != LIMIT
                or config["physical_device_id"] != DEVICE or config["physical_node"] != "node0"):
            raise ValueError("unexpected network case")
        self.directory.mkdir(mode=0o700)
        self.control.mkdir(parents=True, exist_ok=True)
        original = {str(d): self.shaping(d) for d in (DEVICE, SIBLING)}
        if any(x["limit_mbps"] != 200000 for x in original.values()):
            raise ValueError("the actual original ports must be uncapped before this test")
        state = dict(device=DEVICE, sibling=SIBLING, original=original, limit_mbps=LIMIT,
                     unit="hccl-roce-" + self.root.name.removeprefix("hccl-diagnose-"))
        write(self.snapshot, state)
        shutil.copy2(Path(__file__), self.directory / "guard.py")
        command = ["systemd-run", "--unit=" + state["unit"], "--on-active=3600s", "--timer-property=AccuracySec=1s",
                   "--property=Type=oneshot", "/usr/bin/python3", str(self.directory / "guard.py"), "restore", "--root", str(self.root)]
        self.run(command)
        if self.run(["systemctl", "is-active", state["unit"] + ".timer"]).strip() != "active":
            raise RuntimeError("network recovery timer not active")
        result = dict(applied_verified=False, restored_verified=False, foreground_path_verified=True)
        try:
            # Exercise the same restorer while nothing has changed, before enabling the trigger.
            probe = state["unit"] + "-probe"
            rehearsal = command.copy()
            rehearsal[1], rehearsal[2] = "--unit=" + probe, "--on-active=2s"
            self.run(rehearsal)
            for _ in range(25):
                if (self.directory / "restored.json").exists():
                    break
                time.sleep(1)
            if not json.loads((self.directory / "restored.json").read_text())["restored_verified"]:
                raise RuntimeError("independent network recovery rehearsal failed")
            self.stop_timer(probe)
            (self.control / "network-guard-ready").touch()
            deadline = time.monotonic() + 1200
            while not (self.control / "start").exists():
                if (self.control / "abort").exists() or time.monotonic() > deadline:
                    raise TimeoutError("network injection start never arrived")
                time.sleep(.01)
            self.own_processes()
            if (self.control / "stop").exists():
                raise RuntimeError("network injection window already ended")
            if any(self.shaping(d) != original[str(d)] for d in (DEVICE, SIBLING)):
                raise RuntimeError("port settings changed before apply")
            if (self.control / "stop").exists():
                raise RuntimeError("network window elapsed during pre-apply checks")
            result["apply_started_raw_ns"] = raw_ns()
            self.set(DEVICE, LIMIT)
            if self.shaping(DEVICE)["limit_mbps"] != LIMIT or self.shaping(SIBLING) != original[str(SIBLING)]:
                raise RuntimeError("requested port limit or sibling isolation did not verify")
            result.update(applied_verified=True, started_raw_ns=raw_ns(), before=self.query())
            while not (self.control / "stop").exists():
                if (self.control / "abort").exists() or time.monotonic() > deadline:
                    raise TimeoutError("network injection stop never arrived")
                time.sleep(.01)
            result.update(finished_raw_ns=raw_ns(), after=self.query())
        except BaseException as error:
            result["error"] = str(error)
            raise
        finally:
            self.restore()
            result["restored_verified"] = True
            write(self.control / "network-result.json", result)
            (self.control / "network-restored").touch()
            self.stop_timer(state["unit"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("query", "watch", "restore"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise PermissionError("authorized host root is required for real RoCE shaping")
    window = Window(args.root)
    if args.action == "query":
        print(json.dumps(window.query()))
    elif args.action == "restore":
        window.restore()
    else:
        with (args.root.parent / ".hccl-diagnose-roce.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            window.watch()


if __name__ == "__main__":
    main()
