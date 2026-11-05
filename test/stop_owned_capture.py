"""Stop only processes bound to one fresh owned capture path inside its container."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import time


def owned_processes(observations, base):
    scripts = {base + suffix for suffix in (
        "/src/test/gpt2_train.py", "/src/examples/diagnosis_collectives.py",
        "/src/test/device_context_hold.py", "/src/test/anomaly_injection/npu_background_load.py",
        "/src/test/anomaly_injection/acl_copy_load.py", "/bin/single_process_comm_load",
        "/src/test/diagnose_gpt_local_clusters.py", "/src/test/diagnose_single_gpt40.py")}
    selected = {pid for pid, item in observations.items() if scripts.intersection(item["argv"])}
    while True:
        children = {pid for pid, item in observations.items() if item["parent"] in selected}
        if children <= selected:
            return {pid: observations[pid] for pid in sorted(selected)}
        selected.update(children)


def inspect(proc=Path("/proc")):
    result = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            if fields[0] == "Z":
                continue
            result[int(entry.name)] = dict(parent=int(fields[1]), ticks=fields[19],
                argv=(entry / "cmdline").read_bytes().decode(errors="replace").strip("\0").split("\0"))
        except (OSError, ValueError, IndexError):
            continue
    return result


def terminate(base):
    extra = {"/workspace/gpt2-three-anomalies-20261102-"+str(i) for i in (101, 102, 103)}
    copy_suite = base in {"/workspace/hccl-diagnose-single-20261104-" + str(i)
                         for i in list(range(701, 711)) + list(range(801, 811))}
    if not re.fullmatch(r"/workspace/hccl-diagnose-(?:node03-[0-9-]+|single-20261103-6[0-4][0-9])", base) and base not in extra and not copy_suite:
        raise ValueError("an exact owned attempt path is required")
    initial = owned_processes(inspect(), base)
    if os.getpid() in initial:
        raise ValueError("cleanup process unexpectedly selected itself")
    sent = []
    for sig, seconds in ((signal.SIGTERM, 25), (signal.SIGKILL, 10)):
        current = inspect()
        for pid, original in initial.items():
            if pid in current and current[pid]["ticks"] == original["ticks"]:
                try:
                    os.kill(pid, sig)
                    sent.append(dict(pid=pid, start_ticks=original["ticks"], signal=int(sig)))
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            current = inspect()
            if not any(pid in current and current[pid]["ticks"] == item["ticks"] for pid, item in initial.items()):
                break
            time.sleep(.25)
    remaining = owned_processes(inspect(), base)
    result = dict(base=base, selected=initial, signals=sent, remaining=remaining, stopped=not remaining)
    if remaining:
        raise RuntimeError("own capture processes remain: " + json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    print(json.dumps(terminate(args.base)))


if __name__ == "__main__":
    main()
