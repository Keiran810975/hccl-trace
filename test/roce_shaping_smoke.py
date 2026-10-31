#!/usr/bin/env python3
"""One authorized Node0/NPU4 RoCE configuration smoke test, not a traffic test."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time


TOOL = "/usr/local/Ascend/driver/tools/hccn_tool"
PARENT = Path("/home/commTeam/zjy/zjy-new-workspace")
DEVICE = 9
SIBLING = 8
LIMIT = 100000


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_shaping(value: str) -> dict:
    match = re.fullmatch(r"\s*bw_limit\[(\d+) Mbps\],\s*bw_max\[(\d+) Mbps\],"
                         r"\s*bw_cur\[(\d+) Mbps\]\s*", value)
    if not match:
        raise ValueError("unexpected shaping query format")
    result = dict(zip(("limit_mbps", "maximum_mbps", "current_mbps"), map(int, match.groups())))
    if not 10000 <= result["limit_mbps"] <= result["maximum_mbps"] <= 200000:
        raise ValueError("unexpected shaping range; do not modify this port")
    return result


def require_idle_card(value: str) -> None:
    if "No running processes found in NPU 4" not in value:
        raise ValueError("NPU4 is occupied or its process report is missing")
    card, memory = None, []
    for line in value.splitlines():
        match = re.match(r"\|\s*(\d+)\s+Ascend910\b", line)
        if match:
            card = int(match.group(1))
        usage = re.search(r"(\d+)\s*/\s*(\d+)\s*\|$", line)
        if card == 4 and usage and int(usage.group(2)) == 65536:
            memory.append(int(usage.group(1)))
    if len(memory) != 2 or max(memory) >= 4096:
        raise ValueError("both NPU4 chips must have verified idle HBM")


def require_zero_traffic(value: str) -> None:
    matches = re.findall(r"Bandwidth (TX|RX):\s*([0-9]+\.[0-9]+) MB/sec", value)
    if len(matches) != 2 or {x[0] for x in matches} != {"TX", "RX"}:
        raise ValueError("missing or ambiguous port traffic query")
    if any(float(number) != 0 for _, number in matches):
        raise ValueError("target card has existing RoCE traffic")


def run(argv: list[str], out: Path, label: str, check: bool = True) -> subprocess.CompletedProcess:
    started = time.time_ns()
    result = subprocess.run(argv, input="", capture_output=True, text=True, timeout=12)
    write_json(out / (label + "-" + str(started) + ".json"), dict(argv=argv, started_ns=started,
        ended_ns=time.time_ns(), returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
    if check:
        result.check_returncode()
    return result


def query(device: int, out: Path, label: str) -> dict:
    return parse_shaping(run([TOOL, "-i", str(device), "-shaping", "-g"], out, label).stdout)


def safe_directory(path: Path) -> Path:
    path = path.resolve()
    if path.parent != PARENT or not re.fullmatch(r"roce-shaping-smoke-[0-9-]+", path.name):
        raise ValueError("use a new owned smoke-test directory")
    return path


def restore(snapshot: Path, receipt: Path) -> None:
    out = safe_directory(snapshot.parent)
    state = json.loads(snapshot.read_text(encoding="utf-8"))
    if state["device"] != DEVICE or set(state["original"]) != {str(DEVICE), str(SIBLING)}:
        raise ValueError("unexpected restoration scope")
    verified = {}
    for device in (DEVICE, SIBLING):
        original = state["original"][str(device)]
        current = query(device, out, "restore-query")
        if current != original:
            # Restore only this test's own requested value, never an unrelated new configuration.
            if current["limit_mbps"] != LIMIT or current["maximum_mbps"] != original["maximum_mbps"]:
                raise RuntimeError("unexpected concurrent port change; manual review required")
            run([TOOL, "-i", str(device), "-shaping", "-s", "bw_limit", str(original["limit_mbps"])],
                out, "restore-set")
        verified[str(device)] = query(device, out, "restore-verify")
        if verified[str(device)] != original:
            raise RuntimeError("original port configuration was not restored")
    write_json(receipt, dict(restored=True, verified=verified, completed_ns=time.time_ns()))


def precheck(out: Path, label: str) -> None:
    require_idle_card(run(["npu-smi", "info"], out, label + "-occupancy").stdout)
    template = ('{"running":{{json .State.Running}},"privileged":{{json .HostConfig.Privileged}},'
                '"devices":{{json .HostConfig.Devices}}}')
    info = json.loads(run(["docker", "inspect", "--format", template, "zjy-new"],
                          out, label + "-container").stdout)
    if not info["running"] or info["privileged"]:
        raise ValueError("own nonprivileged zjy-new must be running")
    devices = {x["PathOnHost"] for x in info["devices"]}
    if not {"/dev/davinci8", "/dev/davinci9"} <= devices:
        raise ValueError("NPU4 is not assigned to our own container")
    for device in (SIBLING, DEVICE):
        require_zero_traffic(run([TOOL, "-i", str(device), "-bandwidth", "-g"],
                                out, label + "-traffic").stdout)


def timer(out: Path, unit: str, seconds: int, receipt: Path) -> None:
    run(["systemd-run", "--unit=" + unit, "--on-active=" + str(seconds) + "s",
         "--timer-property=AccuracySec=1s", "--property=Type=oneshot", "/usr/bin/python3",
         str(Path(__file__).resolve()), "--restore-only", str(out / "snapshot.json"),
         "--receipt", str(receipt)], out, "arm-timer")
    if run(["systemctl", "is-active", unit + ".timer"], out, "timer-state").stdout.strip() != "active":
        raise RuntimeError("independent recovery timer is not active")


def stop_timer(out: Path, unit: str) -> None:
    run(["systemctl", "stop", unit + ".timer"], out, "stop-timer", check=False)
    state = run(["systemctl", "is-active", unit + ".timer"], out, "stopped-timer-state", check=False)
    if state.stdout.strip() not in {"inactive", "unknown"}:
        raise RuntimeError("recovery timer is still active or in an unexpected state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--restore-only", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise PermissionError("use the existing authorized host root entry for independent rollback")
    if args.restore_only:
        snapshot = args.restore_only.resolve()
        if snapshot.name != "snapshot.json" or not args.receipt or args.receipt.resolve().parent != snapshot.parent:
            raise ValueError("restoration files must stay inside the smoke directory")
        restore(snapshot, args.receipt.resolve())
        return 0
    if not args.execute or not args.directory:
        raise ValueError("explicit --execute and new directory are required")
    out = safe_directory(args.directory)
    if (out / "snapshot.json").exists() or (out / "result.json").exists():
        raise ValueError("do not reuse a smoke attempt")
    if not out.is_dir() or not shutil.which("runuser"):
        raise ValueError("owned directory and runuser must exist")
    with (out / "smoke.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        precheck(out, "initial-1")
        time.sleep(30)
        precheck(out, "initial-2")
        original = {str(d): query(d, out, "original") for d in (SIBLING, DEVICE)}
        if any(x != dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000)
               for x in original.values()):
            raise ValueError("smoke is restricted to two currently uncapped 200G ports")
        write_json(out / "snapshot.json", dict(device=DEVICE, sibling=SIBLING, original=original,
            hostname=socket.gethostname(), source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            explicit_user_authorization=True, requested_limit_mbps=LIMIT, created_ns=time.time_ns()))
        unit = "hccl-roce-smoke-" + out.name.removeprefix("roce-shaping-smoke-")
        probe = out / "recovery-rehearsal.json"
        timer(out, unit + "-probe", 2, probe)
        for _ in range(15):
            if probe.is_file():
                break
            time.sleep(1)
        if not probe.is_file() or not json.loads(probe.read_text())["restored"]:
            raise RuntimeError("independent recovery rehearsal failed; do not change the port")
        stop_timer(out, unit + "-probe")
        timer(out, unit + "-restore", 75, out / "timer-restored.json")
        result = dict(status="failed", device=DEVICE, card=4, original=original,
                      requested_limit_mbps=LIMIT, traffic_effect_verified=False,
                      limitation="Configuration-only smoke; no foreground workload or traffic generator.")
        def interrupted(signum, frame):
            raise InterruptedError("interrupted; restoring port: " + str(signum))
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, interrupted)
        try:
            precheck(out, "immediate")
            if any(query(d, out, "before-apply") != original[str(d)] for d in (SIBLING, DEVICE)):
                raise ValueError("port configuration changed since snapshot")
            argv = [TOOL, "-i", str(DEVICE), "-shaping", "-s", "bw_limit", str(LIMIT)]
            result["apply_started_ns"] = time.time_ns()
            ordinary = run([shutil.which("runuser"), "-u", "commTeam", "--"] + argv,
                           out, "apply-ordinary-user", check=False)
            current = query(DEVICE, out, "ordinary-verify")
            result["ordinary_user_returncode"] = ordinary.returncode
            result["ordinary_user_effective"] = current["limit_mbps"] == LIMIT
            if ordinary.returncode or current["limit_mbps"] != LIMIT:
                if current != original[str(DEVICE)]:
                    raise RuntimeError("unexpected partial setting; restore rather than retry")
                run(argv, out, "apply-host-root")
                result["applied_by"] = "host-root"
            else:
                result["applied_by"] = "commTeam"
            result["apply_ended_ns"] = time.time_ns()
            result["limited"] = query(DEVICE, out, "limited-verify")
            result["sibling_limited"] = query(SIBLING, out, "sibling-verify")
            if result["limited"]["limit_mbps"] != LIMIT:
                raise RuntimeError("setting did not read back the requested limit")
            if result["sibling_limited"] != original[str(SIBLING)]:
                raise RuntimeError("setting affected sibling port; restoring the entire checked card")
            time.sleep(3)
            result["limited_after_hold"] = query(DEVICE, out, "hold-verify")
            if result["limited_after_hold"] != result["limited"]:
                raise RuntimeError("limit changed during short hold")
            result["status"] = "configuration_passed"
        except BaseException as error:
            result["error"] = str(error)
            raise
        finally:
            try:
                restore(out / "snapshot.json", out / "restored.json")
                result["restored"] = True
                stop_timer(out, unit + "-restore")
            except BaseException as error:
                result["status"] = "restore_failed"
                result["restored"] = False
                result["restore_error"] = str(error)
                raise
            finally:
                result["finished_ns"] = time.time_ns()
                write_json(out / "result.json", result)
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
