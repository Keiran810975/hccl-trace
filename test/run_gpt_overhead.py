"""One authorized Node0 four-rank overhead test, without injections or retries."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import statistics
import subprocess
import time

if __package__:
    from .gpt2_diagnosis_suite import WORKLOAD
    from .node03_device_guard import Guard, OVERHEAD_ROOT, PACKAGE, write
else:
    from gpt2_diagnosis_suite import WORKLOAD
    from node03_device_guard import Guard, OVERHEAD_ROOT, PACKAGE, write


ROOT = Path("/home/commTeam/zjy/zjy-new-workspace") / OVERHEAD_ROOT
ASSETS = "/workspace/gpt2-single-node0-50-20261029-001"
PYTHON = "/project/venvs/hccl-py311/bin/python"
ORDERS = (("off", "semantic", "profile"), ("profile", "off", "semantic"),
          ("semantic", "profile", "off"), ("off", "profile", "semantic"),
          ("semantic", "off", "profile"), ("profile", "semantic", "off"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_mapping(text):
    rows = [line.split() for line in text.splitlines()]
    for card, runtime, physical in ((4, 1, 9), (5, 3, 11), (6, 5, 13), (7, 7, 15)):
        expected = [str(card), "1", str(runtime), str(physical), "Ascend910"]
        if rows.count(expected) != 1:
            raise ValueError("runtime-to-physical mapping changed")


def entry_code(base, name, command):
    return ("import json,os;from pathlib import Path;"
        "assert os.getpgid(0)==os.getpid() and os.getsid(0)==os.getpid(),'dedicated docker exec group required';"
        "p=Path(" + repr(base + "/numerics/" + name + "/launcher.json") + ");"
        "p.parent.mkdir(parents=True,exist_ok=True);"
        "p.write_text(json.dumps(dict(pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().split(') ',1)[1].split()[19]))+'\\n');"
        "argv=" + repr(command) + ";os.execvp(argv[0],argv)")


def metrics(samples):
    if (len(samples) != 4 or sorted(r["rank"] for r in samples) != list(range(4))
            or any(r["status"] != "passed" or r["warmup"] != 10 or r["iters"] != 50
                or len(r["iteration_ns"]) != 50 or any(type(t) is not int or t <= 0 for t in r["iteration_ns"])
                or not r["parameter_update_observed"] for r in samples)
            or any(r["parameter_samples"] != samples[0]["parameter_samples"]
                or r["initialization"] != samples[0]["initialization"] for r in samples)):
        raise ValueError("all four replicas must pass the unchanged 10+50 workload")
    return dict(rank_mean_ns=[statistics.mean(r["iteration_ns"]) for r in samples],
        maximum_rank_mean_ns=statistics.mean(max(r["iteration_ns"][i] for r in samples) for i in range(50)))


def summarize(rows):
    if len(rows) != 18 or {(r["block"], r["mode"]) for r in rows} != {
            (b, m) for b in range(6) for m in ("off", "semantic", "profile")}:
        raise ValueError("all eighteen unique predeclared samples are required")
    groups = {m: [r["maximum_rank_mean_ns"] for r in rows if r["mode"] == m]
              for m in ("off", "semantic", "profile")}
    pairs = []
    for b in range(6):
        block = {r["mode"]: r["maximum_rank_mean_ns"] for r in rows if r["block"] == b}
        pairs.append(dict(block=b, **{m + "_percent": (block[m] / block["off"] - 1) * 100
            for m in ("semantic", "profile")}))
    return dict(samples_per_mode=6, paired=pairs,
        mode_mean_ms={m: statistics.mean(v) / 1e6 for m, v in groups.items()},
        paired_mean_percent={m: statistics.mean(p[m + "_percent"] for p in pairs) for m in ("semantic", "profile")},
        paired_median_percent={m: statistics.median(p[m + "_percent"] for p in pairs) for m in ("semantic", "profile")},
        baseline_max_over_min=max(groups["off"]) / min(groups["off"]),
        baseline_unstable=max(groups["off"]) / min(groups["off"]) > 1.25,
        scope="same attested Host/Device and public DDP observer; incremental trace/msprof cost, not uninstrumented native DDP",
        iteration_metric="mean of per-formal-iteration maximum of four synchronized rank durations")


def run(root):
    if root != ROOT or os.geteuid() != 0 or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("only the authorized Node0 root and host-root entry are allowed")
    if (root / "state.json").exists():
        raise ValueError("never restart a used overhead test")
    plan = json.loads((root / "plan.json").read_text())
    if (plan["mode_order_by_block"] != [list(v) for v in ORDERS]
            or plan["physical_cards"] != [4, 5, 6, 7] or plan["workload_seed"] != 20261028
            or plan["workload_configuration"] != dict(WORKLOAD, iters=50)):
        raise ValueError("frozen overhead plan changed")
    source = json.loads((root / "source-snapshot.json").read_text())["files"]
    if any(digest(root / "src" / name) != value for name, value in source.items()):
        raise ValueError("source snapshot changed")
    guard, base = Guard(root), "/workspace/" + root.name
    state = dict(status="prechecking", requested=18, completed=[], active=None,
        plan_sha256=digest(root / "plan.json"), source_snapshot_sha256=digest(root / "source-snapshot.json"),
        started_unix_ns=time.time_ns(), restoration_verified=False, external_processes_stopped=False)
    if (root / "prestart-v1/state.json").exists():
        state["prior_preflight"] = "prestart-v1/state.json; zero training and no device lease"
    if (root / "launcher-v2/state.json").exists():
        state["prior_launcher_failure"] = "launcher-v2/state.json; zero training, original device state independently restored"
    write(root / "state.json", state)
    deadline = time.monotonic() + 5400
    shell = ("set -e\nsource /usr/local/Ascend/ascend-toolkit/set_env.sh\n"
        "export ASCEND_OPP_PATH=" + ASSETS + "/a3-runtime/opp\n"
        "export LD_LIBRARY_PATH=" + base + "/deploy/lib64:" + ASSETS + "/a3-runtime/aarch64-linux/lib64:"
        + ASSETS + "/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n"
        "export PYTHONPATH=" + base + "/src:" + ASSETS + "/deps\n"
        "export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO='level0:ring;level1:ring;level2:ring'\n"
        "export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n"
        "export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0\n"
        "unset ASCEND_RT_VISIBLE_DEVICES\n")

    def cancel_owned(name):
        code = ("import json,os,signal,time;from pathlib import Path\n"
            "directory=Path(" + repr(base + "/numerics/" + name + "/runtime") + ")\n"
            "for sig in (signal.SIGTERM,signal.SIGKILL):\n"
            " launcher=directory.parent/'launcher.json'\n"
            " if launcher.exists():\n"
            "  d=json.loads(launcher.read_text());q=Path('/proc')/str(d['pid'])\n"
            "  try:\n"
            "   ticks=q.joinpath('stat').read_text().split(') ',1)[1].split()[19]\n"
            "   argv=q.joinpath('cmdline').read_text()\n"
            "   if ticks==d['start_ticks'] and " + repr(base + "/numerics/" + name) + " in argv and os.getpgid(d['pid'])==d['pid']:os.killpg(d['pid'],sig)\n"
            "  except (ProcessLookupError,FileNotFoundError):pass\n"
            " for p in directory.glob('rank-*.json'):\n"
            "  d=json.loads(p.read_text());q=Path('/proc')/str(d['pid'])\n"
            "  if not q.exists():continue\n"
            "  try:\n"
            "   ticks=q.joinpath('stat').read_text().split(') ',1)[1].split()[19]\n"
            "   argv=q.joinpath('cmdline').read_text().split('\\0')\n"
            "   if ticks==d['process_start_ticks'] and " + repr(base + "/src/test/gpt2_train.py") + " in argv and "
            + repr(base + "/numerics/" + name) + " in argv:os.kill(d['pid'],sig)\n"
            "  except (ProcessLookupError,FileNotFoundError):pass\n"
            " time.sleep(5)\n")
        guard.docker(PYTHON, "-c", code)

    try:
        for folder in ("logs", "numerics", "captures"):
            (root / folder).mkdir()
        with socket.socket() as port:
            port.bind(("127.0.0.1", 29886))
        mapping = guard.docker("npu-smi", "info", "-m")
        (root / "logs/mapping.txt").write_text(mapping)
        validate_mapping(mapping)
        guard.prepare(7200)
        guard.activate()
        for block, order in enumerate(ORDERS):
            for mode in order:
                name = "overhead-{}-{}".format(block, mode)
                if shutil.disk_usage(root).free < 35 * 1024**3 or time.monotonic() > deadline - 900:
                    raise RuntimeError("bounded free-space or runtime limit reached")
                guard.idle()
                state.update(status="training", active=name)
                write(root / "state.json", state)
                case = dict(schema_version=1, case_id=name, topology=dict(nnodes=1, ranks_per_node=4),
                    workload=dict(WORKLOAD, iters=50), workload_seed=20261028, injection=dict(kind="normal"))
                write(root / "input" / (name + ".json"), case)
                out = root / "numerics" / name
                for folder in ("public", "private", "workload_results"):
                    (out / folder).mkdir(parents=True)
                dest = base + "/captures/" + name + "/nodes/node0"
                app = [PYTHON, "-m", "torch.distributed.run", "--nnodes=1", "--nproc-per-node=4",
                    "--max-restarts=0", "--master-addr=127.0.0.1", "--master-port=29886",
                    base + "/src/test/gpt2_train.py", "--case", base + "/input/" + name + ".json",
                    "--output", base + "/numerics/" + name, "--data", ASSETS + "/data",
                    "--devices", "1,3,5,7", "--sdk-observations", dest + "/calls"]
                flags = ("export HCCL_STEP_TRACE={0} HCCL_TASK_SEMANTIC_TRACE={0}\n".format(int(mode != "off"))
                    + "export HCCL_TRACE_RUN_ID=" + name + " HCCL_TRACE_NODE_ID=node0\n"
                    + "export ASCEND_PROCESS_LOG_PATH=" + dest + "/plog\n")
                launch = (["msprof", "--application=" + shlex.join(app), "--output=" + dest + "/msprof",
                    "--hccl=on", "--task-time=on", "--type=db"] if mode == "profile" else app)
                started = time.monotonic_ns()
                timed = ["timeout", "--signal=TERM", "--kill-after=30s", "900s", "bash", "-lc",
                         shell + flags + "exec " + shlex.join(launch)]
                entry = entry_code(base, name, timed)
                with (root / "logs" / (name + ".log")).open("x") as log:
                    process = subprocess.Popen(["docker", "exec", "zjy-new", PYTHON, "-c", entry],
                        stdout=log, stderr=subprocess.STDOUT)
                    state["active_launcher_pid"] = process.pid
                    write(root / "state.json", state)
                    try:
                        process.wait(timeout=950)
                        if process.returncode:
                            raise RuntimeError(name + " failed; retain this attempt without retry")
                    except BaseException:
                        cancel_owned(name)
                        process.wait(timeout=180)
                        raise
                samples = [json.loads((out / "workload_results" / ("rank-" + str(r) + ".json")).read_text()) for r in range(4)]
                measured = metrics(samples)
                if any(s["loaded_communication_libraries"].get(base + "/deploy/lib64/libhcomm.so") != guard.host_hash for s in samples):
                    raise ValueError("matched Host library was not actually loaded")
                state["completed"].append(dict(name=name, block=block, mode=mode,
                    wall_ns=time.monotonic_ns() - started, numerical_rank_count=4, **measured))
                state.update(active=None, active_launcher_pid=None)
                write(root / "state.json", state)
                time.sleep(3)
        state["summary"] = summarize(state["completed"])
        state["status"] = "restoring"
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        raise
    finally:
        try:
            if guard.snapshot.exists():
                guard.restore()
                snapshot = json.loads(guard.snapshot.read_text())
                actual = guard.verify_original(snapshot)
                if guard.registry.exists():
                    raise RuntimeError("device registry remains active")
                timer_status = guard.run(["systemctl", "is-active", snapshot["unit"] + ".timer"], check=False).strip()
                if timer_status not in {"inactive", "unknown"}:
                    raise RuntimeError("rollback timer remains active")
                state["restoration_verified"] = True
                write(root / "restoration-verified.json", dict(policies=actual,
                    official_sha256=guard.sha(PACKAGE), timer_status=timer_status, registry_absent=True,
                    container_id=guard.container(snapshot["container_id"]), unix_ns=time.time_ns()))
        except BaseException as error:
            state.update(status="restoration_requires_attention", restoration_error=repr(error))
            raise
        finally:
            state.update(active=None, finished_unix_ns=time.time_ns())
            write(root / "state.json", state)
    state.update(status="completed")
    write(root / "state.json", state)
    write(root / "summary.json", state["summary"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError("overhead test interrupted by signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    with (args.root / "overhead.lock").open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root.resolve())
