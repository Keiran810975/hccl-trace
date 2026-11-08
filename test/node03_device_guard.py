"""Explicit Node0/Node3 NPU4-7 development-package lease with independent rollback."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time


CARDS = (4, 5, 6, 7)
PARENTS = {"liteserver-560t-0": Path("/home/commTeam/zjy/zjy-new-workspace"),
           "liteserver-560t-3": Path("/home/zjy-new/workspace")}
PACKAGE = "/usr/local/Ascend/cann-8.5.1/opp/built-in/op_impl/aicpu/kernel/aicpu_hcomm.tar.gz"
DEVICE_HASH = "2b30fbe89be9eaa3c962f139aee162d356e97e1ce2b0788181d649d380f9974f"
HOST_HASH = "498c951114cff9a2d6cd5e02958a6bf1bc3a90cd661ac93d4b0ba4243430a64e"
NODE0_BUILD_PROBES = {"semantic-coverage-20261102", "gpt2-semantic-20261102-001",
    "gpt2-three-anomalies-20261102-101", "gpt2-three-anomalies-20261102-102",
    "gpt2-three-anomalies-20261102-103"}
SDMA10_ROOTS = frozenset("hccl-diagnose-single-20261104-" + str(i) for i in range(700, 711))
SDMA03_ROOTS = frozenset("hccl-diagnose-single-20261104-" + str(i) for i in range(800, 811))
MULTINODE20_ROOTS = frozenset("hccl-diagnose-node03-20261105-" + str(i) for i in range(900, 921))
MULTINODE19_ROOTS = frozenset("hccl-diagnose-node03-20261106-" + str(i) for i in (1000, *range(1002, 1021)))
OVERHEAD_ROOT = "gpt2-overhead-20261105-001"
OVERHEAD_TRIM_ROOT = "gpt2-overhead-trim-20261105-001"
OVERHEAD_BENCHMARK_ROOT = "gpt2-overhead-benchmark-20261106-001"
OVERHEAD_ATTRIBUTION_ROOT = "gpt2-overhead-attribution-20261106-001"
OVERHEAD_LOGFILTER_ROOT = "gpt2-overhead-logfilter-20261106-001"
LOWLOG_ROOT = "gpt2-lowlog-20261106-001"
HCCL_TEST_OVERHEAD_ROOT = "hccl-test-overhead-20261107-001"
ROCE_SINGLE_ROOT = "hccl-diagnose-node03-20261108-1101"


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def scope(root, hostname=None):
    parent = PARENTS.get((hostname or socket.gethostname()).split(".")[0])
    root = root.resolve()
    semantic_probe = root.name in NODE0_BUILD_PROBES | {OVERHEAD_ROOT, OVERHEAD_TRIM_ROOT, OVERHEAD_BENCHMARK_ROOT, OVERHEAD_ATTRIBUTION_ROOT, OVERHEAD_LOGFILTER_ROOT, LOWLOG_ROOT, HCCL_TEST_OVERHEAD_ROOT} and (hostname or socket.gethostname()).split(".")[0] == "liteserver-560t-0"
    single_suite = bool(re.fullmatch(r"hccl-diagnose-single-20261103-6[0-4][0-9]", root.name)) and (hostname or socket.gethostname()).split(".")[0] == "liteserver-560t-0"
    copy_suite = root.name in SDMA10_ROOTS | SDMA03_ROOTS and (hostname or socket.gethostname()).split(".")[0] == "liteserver-560t-0"
    if parent is None or root.parent != parent.resolve() or not (semantic_probe or single_suite or copy_suite or re.fullmatch(r"hccl-diagnose-node03-[0-9-]+", root.name)):
        raise ValueError("only the explicitly authorized Node0/Node3 workspace is allowed")
    return root


def policy(enable, mode):
    enables = re.findall(r"Custom-op-secverify-enable\s*:\s*(True|False)", enable)
    modes = re.findall(r"Custom-op-secverify-mode\s*:\s*(\d+)", mode)
    if len(enables) != 2 or len(modes) != 2 or len(set(enables)) != 1 or len(set(modes)) != 1:
        raise ValueError("each whole card must report two identical chip policies")
    return dict(enable=enables[0] == "True", mode=int(modes[0]))


def own_transition(current, original):
    return current in (original, dict(enable=True, mode=0), dict(enable=True, mode=original["mode"]))


class Guard:
    def __init__(self, root):
        self.root = scope(root)
        self.directory = self.root / "security"
        self.snapshot = self.directory / "snapshot.json"
        self.registry = self.root.parent / ".hccl-diagnose-device-active.json"
        self.base = "/workspace/" + self.root.name
        self.cards = CARDS
        self.device_hash, self.host_hash = DEVICE_HASH, HOST_HASH
        self.host_library = "/workspace/nf-20261022/deploy/lib64/libhcomm.so"
        self.host_libraries = {self.host_library: self.host_hash}
        multi19 = self.root.name in MULTINODE19_ROOTS
        single_roce = self.root.name == ROCE_SINGLE_ROOT
        multi20 = self.root.name in MULTINODE20_ROOTS or multi19
        multi_build = (self.root.name.startswith("hccl-diagnose-node03-20261103-") or multi20 or single_roce) and (self.root / "build-receipt.json").is_file()
        if single_roce and not multi_build:
            raise ValueError('single-collective RoCE requires an attested low-log build')
        single_build = bool(re.fullmatch(r"hccl-diagnose-single-20261103-6[0-4][0-9]", self.root.name))
        copy03_build = self.root.name in SDMA03_ROOTS
        copy_build = self.root.name in SDMA10_ROOTS or copy03_build
        overhead_build = self.root.name in {OVERHEAD_ROOT, OVERHEAD_TRIM_ROOT, OVERHEAD_BENCHMARK_ROOT, OVERHEAD_ATTRIBUTION_ROOT, OVERHEAD_LOGFILTER_ROOT, LOWLOG_ROOT, HCCL_TEST_OVERHEAD_ROOT}
        if copy_build:
            single_build = True
        if multi_build or single_build or overhead_build:
            deployment = json.loads((self.root / "deployment.json").read_text())
            expected_profile = ("hccl-test-overhead-v1" if self.root.name == HCCL_TEST_OVERHEAD_ROOT else "gpt-lowlog-v1" if self.root.name == LOWLOG_ROOT else "gpt-overhead-logfilter-v1" if self.root.name == OVERHEAD_LOGFILTER_ROOT else "gpt-overhead-attribution-v1" if self.root.name == OVERHEAD_ATTRIBUTION_ROOT else "gpt-overhead-benchmark-v1" if self.root.name == OVERHEAD_BENCHMARK_ROOT else "gpt-overhead-trim-v1" if self.root.name == OVERHEAD_TRIM_ROOT else "gpt-overhead-v1" if overhead_build else "single-gpt-sdma10-npu03-v1" if copy03_build else "single-gpt-sdma10-v1"
                if copy_build else "single-gpt40-v1" if single_build else "multinode19-lowlog-v1" if multi19 else "multinode20-v1" if multi20 else "multinode-dual-v1")
            if single_roce:
                expected_profile = 'roce-single-collective-v1'
            if deployment.get("profile") != expected_profile:
                raise ValueError("new multi-node producer requires the explicit reviewed deployment profile")
            if multi20 or single_roce:
                authorization = json.loads((self.root / "authorization.json").read_text())
                if (authorization.get('nodes') != [0, 3] or authorization.get('physical_cards') != [4, 5, 6, 7]
                        or authorization.get('restore_required') is not True):
                    raise ValueError('twenty-run batch requires the exact two-node authorization')
                if multi19 and (authorization.get('manual_continuation_user_confirmed') is not True
                        or authorization.get('temporary_signature_user_confirmed') is not True
                        or authorization.get('node3_target_process_stop_user_confirmed') is not False
                        or deployment.get('capture_policy') != dict(global_log_level=2, module_override=False,
                            task_time='l1', ai_core='off', hccl='on', ascendcl='on')):
                    raise ValueError('manual low-log continuation requires exact authorization and capture policy')
                if single_roce and (authorization.get('single_collective_user_confirmed') is not True
                        or authorization.get('temporary_signature_user_confirmed') is not True
                        or authorization.get('node3_target_process_stop_user_confirmed') is not False
                        or deployment.get('capture_policy') != dict(global_log_level=2, module_override=False,
                            task_time='l1', ai_core='off', hccl='on', ascendcl='on')):
                    raise ValueError('single-call RoCE requires exact authorization, low-log capture and no external stop')
            if single_build and deployment.get("cards") != ([0, 1, 2, 3] if copy03_build else [4, 5, 6, 7]):
                raise ValueError("single-node batch is limited to the already authorized whole cards")
            if copy03_build:
                authorization = json.loads((self.root / "authorization.json").read_text())
                if (authorization.get("physical_cards") != [0, 1, 2, 3]
                        or authorization.get("temporary_signature_user_confirmed") is not True
                        or authorization.get("restore_required") is not True):
                    raise ValueError("NPU0-3 requires its explicit user authorization and mandatory restoration")
            if overhead_build:
                authorization = json.loads((self.root / "authorization.json").read_text())
                if (deployment.get("cards") != [4, 5, 6, 7] or authorization.get("nodes") != [0]
                        or authorization.get("physical_cards") != [4, 5, 6, 7]
                        or authorization.get("temporary_signature_user_confirmed") is not True
                        or authorization.get("restore_required") is not True):
                    raise ValueError("overhead capture requires explicit Node0 NPU4-7 authorization and restoration")
        if self.root.name in NODE0_BUILD_PROBES or multi_build or single_build or overhead_build:
            build = json.loads((self.root / "build-receipt.json").read_text())
            if build["status"] != "built" or any(not re.fullmatch(r"[0-9a-f]{64}", build[k]) for k in ("device_sha256", "host_sha256")):
                raise ValueError("new producer requires a completed matching Host/Device build receipt")
            if (multi19 or single_roce) and build['device_sha256'] != 'b68ef612370ebb9c635e9fb9d94ddaf977be81a3d609d0e35936f20e41ceebd2':
                raise ValueError('continuation requires the tested low-log Device build')
            if self.root.name == HCCL_TEST_OVERHEAD_ROOT and build['device_sha256'] != 'b68ef612370ebb9c635e9fb9d94ddaf977be81a3d609d0e35936f20e41ceebd2':
                raise ValueError('HCCL Test overhead requires the tested low-log Device build')
            if (overhead_build or multi19 or single_roce) and not build.get("verified_current_producer_files"):
                raise ValueError("overhead capture requires the attested current producer files")
            if (multi_build or single_build or overhead_build) and any(hashlib.sha256((self.root / "src" / name).read_bytes()).hexdigest() != value
                    for name, value in build["verified_current_producer_files"].items()):
                raise ValueError("multi-node source differs from the attested new semantic producer")
            self.cards = ((0, 1, 2, 3) if copy03_build else (5, 6, 7)
                if self.root.name == "semantic-coverage-20261102" else (4, 5, 6, 7))
            self.device_hash, self.host_hash = build["device_sha256"], build["host_sha256"]
            self.host_library = self.base + "/deploy/lib64/libhcomm.so"
            libraries = build.get("host_libraries", {})
            if (set(libraries) != {"libhcomm.so", "libhccl_alg.so", "libhccl_plf.so"}
                    or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in libraries.values())
                    or libraries["libhcomm.so"] != self.host_hash):
                raise ValueError("all three newly built Host libraries must be attested")
            self.host_libraries = {self.base + "/deploy/lib64/" + name: value for name, value in libraries.items()}

    @contextmanager
    def lock(self):
        with (self.root.parent / ".hccl-diagnose-device.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def run(self, command, *, input_text=None, check=True):
        completed = subprocess.run(command, input=input_text, text=True, capture_output=True, timeout=30)
        if self.directory.is_dir():
            with (self.directory / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(command=command, returncode=completed.returncode,
                    stdout=completed.stdout, stderr=completed.stderr, unix_ns=time.time_ns())) + "\n")
        if check and completed.returncode:
            raise RuntimeError("guard command failed: {}: {}".format(command, completed.stderr[-1200:] + completed.stdout[-1200:]))
        return completed.stdout

    def stop_timer(self, unit):
        # Successful one-shot timers can already have been garbage-collected by systemd.
        self.run(["systemctl", "stop", unit + ".timer"], check=False)
        if self.run(["systemctl", "is-active", unit + ".timer"], check=False).strip() not in {"inactive", "unknown"}:
            raise RuntimeError("rollback timer did not become inactive")

    def query(self, card):
        if card not in self.cards:
            raise ValueError("card outside authorization")
        return policy(self.run(["npu-smi", "info", "-t", "custom-op-secverify-enable", "-i", str(card)]),
                      self.run(["npu-smi", "info", "-t", "custom-op-secverify-mode", "-i", str(card)]))

    def set(self, card, kind, value):
        if card not in self.cards or kind not in {"custom-op-secverify-enable", "custom-op-secverify-mode"}:
            raise ValueError("setting outside authorization")
        self.run(["npu-smi", "set", "-t", kind, "-i", str(card), "-d", str(value)], input_text="Y\n")

    def container(self, expected=None):
        info = json.loads(self.run(["docker", "inspect", "zjy-new"]))[0]
        if (not info["State"]["Running"] or info["HostConfig"]["Privileged"] or expected and info["Id"] != expected):
            raise ValueError("owned nonprivileged container identity changed")
        if any(Path(PACKAGE).is_relative_to(Path(m["Destination"])) for m in info["Mounts"]):
            raise ValueError("refusing to replace a host-mounted/shared CANN package")
        if not any(m["Source"] == str(self.root.parent) and m["Destination"] == "/workspace" for m in info["Mounts"]):
            raise ValueError("owned workspace mount changed")
        if not {"/dev/davinci" + str(d) for c in self.cards for d in (2*c, 2*c+1)} <= {d["PathOnHost"] for d in info["HostConfig"]["Devices"]}:
            raise ValueError("complete authorized cards are not mapped")
        return info["Id"]

    def docker(self, *command):
        return self.run(["docker", "exec", "zjy-new", *command])

    def sha(self, path):
        return self.docker("sha256sum", path).split()[0]

    def idle(self):
        from run_tool_smoke import available
        if not available(self.run(["npu-smi", "info"]), list(self.cards)):
            raise ValueError("both chips of every authorized card must be idle")

    def timer(self, unit, seconds, rehearsal=False):
        command = ["systemd-run", "--unit=" + unit, "--on-active=" + str(seconds) + "s",
                   "--timer-property=AccuracySec=1s", "--property=Type=oneshot", "/usr/bin/python3",
                   str(self.directory / "guard.py"), "rehearse" if rehearsal else "restore", "--root", str(self.root)]
        self.run(command)
        if self.run(["systemctl", "is-active", unit + ".timer"]).strip() != "active":
            raise RuntimeError("independent rollback timer was not armed")

    def verify_original(self, state):
        self.container(state["container_id"])
        if self.sha(PACKAGE) != state["official_sha256"]:
            raise RuntimeError("official package hash differs from saved original")
        actual = {str(c): self.query(c) for c in self.cards}
        if actual != state["original"]:
            raise RuntimeError("card policies differ from saved originals")
        return actual

    def prepare(self, seconds):
        if not 900 <= seconds <= 7200:
            raise ValueError("independent restore deadline must be bounded to 15-120 minutes")
        with self.lock():
            if self.registry.exists():
                raise ValueError("another owned device lease is active; do not duplicate or overwrite it")
            self.directory.mkdir(mode=0o700)
            identity = self.container()
            self.idle()
            time.sleep(30)
            self.idle()
            custom = self.base + "/input/aicpu_hcomm.tar.gz"
            if self.sha(custom) != self.device_hash or any(self.sha(path) != value for path, value in self.host_libraries.items()):
                raise ValueError("the previously validated Host/Device pair is required")
            resolved = self.docker("readlink", "-f", PACKAGE).strip()
            if resolved != PACKAGE:
                raise ValueError("unexpected package symlink")
            original = {str(c): self.query(c) for c in self.cards}
            official = self.sha(PACKAGE)
            if official == self.device_hash:
                raise ValueError("custom package is already installed without this lease")
            backup = self.base + "/security/official-device.tar.gz"
            self.docker("cp", "-p", PACKAGE, backup)
            if self.sha(backup) != official:
                raise RuntimeError("official backup did not match")
            shutil.copy2(Path(__file__), self.directory / "guard.py")
            # Keep the independent restorer self-contained, including its idle-check import at prepare only.
            state = dict(schema_version=1, phase="prepared", root=str(self.root), container_id=identity,
                         cards=list(self.cards), original=original, official_sha256=official,
                         custom_sha256=self.device_hash, custom_container=custom, backup_container=backup,
                         unit="hccl-device-" + self.root.name.removeprefix("hccl-diagnose-"),
                         restore_after_seconds=seconds, created_unix_ns=time.time_ns(), explicit_user_authorization=True)
            write(self.snapshot, state)
            write(self.registry, dict(snapshot=str(self.snapshot)))
        try:
            self.timer(state["unit"] + "-probe", 2, rehearsal=True)
            for _ in range(25):
                if (self.directory / "rehearsal.json").exists():
                    break
                time.sleep(1)
            if not json.loads((self.directory / "rehearsal.json").read_text())["original_verified"]:
                raise RuntimeError("independent restoration rehearsal failed")
            self.stop_timer(state["unit"] + "-probe")
            self.timer(state["unit"], seconds)
            state["phase"] = "armed"
            write(self.snapshot, state)
        except BaseException:
            self.restore()
            raise

    def activate(self):
        with self.lock():
            state = json.loads(self.snapshot.read_text())
            if state["phase"] != "armed" or self.run(["systemctl", "is-active", state["unit"] + ".timer"]).strip() != "active":
                raise ValueError("an independently protected, unused snapshot is required")
            self.verify_original(state)
            self.idle()
            state["phase"] = "applying"
            write(self.snapshot, state)
            for card in self.cards:
                self.set(card, "custom-op-secverify-enable", 1)
                self.set(card, "custom-op-secverify-mode", 0)
                if self.query(card) != dict(enable=True, mode=0):
                    raise RuntimeError("temporary policy did not read back")
            self.docker("cp", "-p", state["custom_container"], PACKAGE)
            if self.sha(PACKAGE) != self.device_hash:
                raise RuntimeError("custom package did not read back")
            state.update(phase="active", activated_unix_ns=time.time_ns())
            write(self.snapshot, state)

    def rehearse(self):
        with self.lock():
            state = json.loads(self.snapshot.read_text())
            if state["phase"] != "prepared":
                raise ValueError("restoration rehearsal must precede any change")
            actual = self.verify_original(state)
            write(self.directory / "rehearsal.json", dict(original_verified=True, policies=actual, unix_ns=time.time_ns()))

    def restore(self):
        with self.lock():
            state = json.loads(self.snapshot.read_text())
            if state["cards"] != list(self.cards) or state["root"] != str(self.root) or state["custom_sha256"] != self.device_hash:
                raise ValueError("snapshot scope mismatch")
            errors = []
            try:
                self.container(state["container_id"])
                if self.sha(PACKAGE) not in {state["official_sha256"], self.device_hash}:
                    raise RuntimeError("unexpected concurrent package change")
                self.docker("cp", "-p", state["backup_container"], PACKAGE)
                if self.sha(PACKAGE) != state["official_sha256"]:
                    raise RuntimeError("official package restoration failed")
            except Exception as error:
                errors.append(str(error))
            for card in self.cards:
                try:
                    original, current = state["original"][str(card)], self.query(card)
                    if not own_transition(current, original):
                        raise RuntimeError("unexpected concurrent policy change on card " + str(card))
                    if current != original:
                        self.set(card, "custom-op-secverify-enable", 1)
                        self.set(card, "custom-op-secverify-mode", original["mode"])
                        self.set(card, "custom-op-secverify-enable", int(original["enable"]))
                    if self.query(card) != original:
                        raise RuntimeError("card policy did not restore: " + str(card))
                except Exception as error:
                    errors.append(str(error))
            receipt = dict(restored=not errors, errors=errors, finished_unix_ns=time.time_ns())
            write(self.directory / "restored.json", receipt)
            if errors:
                raise RuntimeError("restoration requires attention: " + "; ".join(errors))
            state["phase"] = "restored"
            write(self.snapshot, state)
            if self.registry.exists():
                if json.loads(self.registry.read_text())["snapshot"] != str(self.snapshot):
                    raise RuntimeError("another lease owns the registry")
                self.registry.unlink()
        # Cancel only after the independent on-disk verification succeeded.
        self.stop_timer(state["unit"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "activate", "restore", "rehearse"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise PermissionError("use the explicitly authorized host root SSH entry")
    guard = Guard(args.root)
    try:
        if args.action == "prepare":
            guard.prepare(args.seconds)
        else:
            getattr(guard, args.action)()
    except BaseException:
        if args.action == "activate":
            guard.restore()
        raise


if __name__ == "__main__":
    main()
