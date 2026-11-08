"""Opt-in, one-collective RoCE window; CPU gates are not training observations."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import time

if __package__:
    from .anomaly_injection.single_node_control import clocks
else:
    from anomaly_injection.single_node_control import clocks


PROFILE = "roce-single-collective-v1"
ROOT_NAME = "hccl-diagnose-node03-20261108-1101"
RANKS = tuple(range(8))


def case():
    if __package__:
        from .multinode_dual_suite import plan
    else:
        from multinode_dual_suite import plan
    value = deepcopy(plan()["cases"][-1])
    value["case_id"] = "roce-single-collective-20261108-01"
    value["experiment_contract"].update(profile=PROFILE, controlled_call=True,
        activation='preverified_single_collective_gate',
        control_waits_are_not_host_preparation=True, training_overhead_not_comparable=True)
    value["injection"].update(iteration=25, duration_iters=1, window_mode="single_collective")
    return value


def validate_case(value):
    if value != case():
        raise ValueError("single-collective probe must match its independent frozen case")


def read(path):
    return json.loads(path.read_text())


def publish(path, value):
    if path.exists():
        raise ValueError("single-collective checkpoint must not be reused: " + path.name)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def identity(case_id, iteration, bucket_signature, element_count):
    signature, count = bucket_signature, element_count
    if (type(iteration) is not int or iteration < 5 or type(count) is not int or count <= 0
            or len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature)):
        raise ValueError("a real measured bucket identity is required")
    return dict(case_id=case_id, iteration=iteration, bucket_signature=signature, element_count=count)


def validate_participants(message, expected, phase):
    if message.get("identity") != expected or message.get("phase") != phase:
        raise ValueError("single-collective identity or phase mismatch")
    values = message.get("ranks", [])
    if len(values) != 8 or {r.get("rank") for r in values} != set(RANKS):
        raise ValueError("all eight distinct ranks must rendezvous")
    for item in values:
        if type(item.get('rank')) is not int or item.get("identity") != expected or item.get("phase") != phase:
            raise ValueError("ranks selected different collectives")
        if item.get("device_synchronized") is not True:
            raise ValueError("device completion, not API return, is required")
        if type(item.get("raw_ns")) is not int or item["raw_ns"] < 0:
            raise ValueError("missing local monotonic clock")
        if phase == "completed" and not (0 <= item.get("submit_before_raw_ns", -1)
                <= item.get("submit_after_raw_ns", -1) <= item["raw_ns"]):
            raise ValueError("invalid local submission/completion order")
    return {r["rank"]: r for r in values}


class SingleCollectiveControl:
    single_collective_window = True
    communication_scoped = False

    def __init__(self, value, directory, rank, store, synchronize, *, timeout=90):
        validate_case(value)
        if rank not in RANKS or store is None or not 0 < timeout <= 120:
            raise ValueError("eight-rank CPU coordination with a bounded timeout is required")
        self.case, self.inj, self.kind = value, value["injection"], "bandwidth_limit"
        self.directory, self.rank = Path(directory), rank
        self.directory.mkdir(parents=True, exist_ok=True)
        self.owner, self.started, self.stopped = rank == 0, False, False
        self.store, self.synchronize, self.timeout = store, synchronize, timeout
        self.prefix = value["case_id"] + "/single-collective/"
        self.current = None

    def record(self, event, **fields):
        path = self.directory.parent / "public" / ("roce-controls-rank-%d.jsonl" % self.rank)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as output:
            output.write(json.dumps(dict(event=event, rank=self.rank, clocks=clocks(), **fields)) + "\n")

    def put(self, name, value):
        self.store.set(self.prefix + name, json.dumps(value))

    def wait(self, predicate):
        deadline = time.monotonic() + self.timeout
        while True:
            if self.store.check([self.prefix + "abort"]):
                raise RuntimeError("single-collective gate aborted")
            result = predicate()
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded single-collective gate expired")
            time.sleep(.005)

    def get(self, name):
        key = self.prefix + name
        return self.wait(lambda: json.loads(self.store.get(key)) if self.store.check([key]) else None)

    def file(self, name):
        def ready():
            if (self.directory / "single-call-error.json").exists():
                raise RuntimeError("native single-collective guard failed")
            path = self.directory / name
            return read(path) if path.exists() else None
        return self.wait(ready)

    def prepare(self):
        if self.owner:
            self.wait(lambda: True if (self.directory / "single-call-guard-ready").exists() else None)
            self.put("guard_ready", dict(case_id=self.case["case_id"]))
        if self.get("guard_ready") != dict(case_id=self.case["case_id"]):
            raise ValueError("guard belongs to a different capture")

    def before_iteration(self, iteration, total):
        pass

    def after_iteration(self, iteration):
        pass

    def before_bucket(self, iteration, signature, count, *, previous_futures=()):
        if self.started:
            raise ValueError("only one collective may be limited")
        expected = identity(self.case["case_id"], iteration, signature, count)
        if iteration != self.inj["iteration"]:
            raise ValueError("wrong predeclared iteration")
        self.started, self.current = True, expected
        self.record("entry_control_begin", identity=expected)
        for future in previous_futures:
            future.wait()
        self.synchronize()
        self.put("ready/%d" % self.rank, dict(identity=expected, phase="ready", rank=self.rank,
            device_synchronized=True, raw_ns=clocks()["raw_ns"]))
        if self.owner:
            ready = dict(identity=expected, phase="ready", ranks=[self.get("ready/%d" % r) for r in RANKS])
            validate_participants(ready, expected, "ready")
            publish(self.directory / "single-call-ready.json", ready)
            active = self.file("single-call-active.json")
            if (active.get("identity") != expected or active.get("phase") != "limited"
                    or active.get("limit_mbps") != 20000 or active.get("applied_verified") is not True):
                raise ValueError("limited port acknowledgement does not match this collective")
            self.put("limited", active)
        active = self.get("limited")
        if active.get("identity") != expected or active.get("phase") != "limited":
            raise ValueError("ranks must use the same confirmed limit")
        self.record("entry_control_end", identity=expected)

    def after_bucket(self, future, public_call):
        # Waiting for the asynchronous Future is not enough: record a device sync too.
        future.wait()
        self.synchronize()
        done = dict(identity=self.current, phase="completed", rank=self.rank,
            device_synchronized=True, raw_ns=clocks()["raw_ns"],
            submit_before_raw_ns=public_call["before"]["raw_ns"],
            submit_after_raw_ns=public_call["after"]["raw_ns"])
        self.put("completed/%d" % self.rank, done)
        self.record("exit_control_begin", identity=self.current, completion=done)
        if self.owner:
            completed = dict(identity=self.current, phase="completed",
                ranks=[self.get("completed/%d" % r) for r in RANKS])
            validate_participants(completed, self.current, "completed")
            publish(self.directory / "single-call-completed.json", completed)
            restored = self.file("single-call-restored.json")
            if restored.get("identity") != self.current or restored.get("restored_verified") is not True:
                raise ValueError("restoration acknowledgement is incomplete")
            self.put("restored", restored)
        restored = self.get("restored")
        if restored.get("identity") != self.current or restored.get("restored_verified") is not True:
            raise ValueError("never release a following call before verified restoration")
        self.stopped = True
        self.record("exit_control_end", identity=self.current)

    def finish(self):
        if not self.started or not self.stopped:
            raise ValueError("the one requested collective did not complete its restored gate")

    def close(self):
        if not self.stopped:
            self.put("abort", dict(rank=self.rank))
            if self.owner:
                (self.directory / "abort").touch()


def watch(window):
    """Use the existing native setters/restorer, but never its five-iteration trigger."""
    if __package__:
        from . import node03_roce_window as native
        from .node03_device_guard import write
    else:
        import node03_roce_window as native
        from node03_device_guard import write
    value = read(window.root / "input/case.json")
    validate_case(value)
    if window.root.name != ROOT_NAME:
        raise ValueError("single-collective limiter is restricted to its new attempt")
    authorization = read(window.root / "authorization.json")
    if (authorization.get("nodes") != [0, 3] or authorization.get("physical_cards") != [4, 5, 6, 7]
            or authorization.get("restore_required") is not True
            or authorization.get("single_collective_user_confirmed") is not True
            or authorization.get("node3_target_process_stop_user_confirmed") is not False):
        raise ValueError("one-call shaping needs explicit scope and no external-task stop")
    native.baseline_active(read(window.root / "input/network-baseline.json"))
    window.directory.mkdir(mode=0o700)
    window.control.mkdir(parents=True, exist_ok=True)
    original = {str(d): window.shaping(d) for d in (native.DEVICE, native.SIBLING)}
    if any(v["limit_mbps"] != 200000 for v in original.values()):
        raise ValueError("both original port settings must be verified before arming")
    state = dict(device=native.DEVICE, sibling=native.SIBLING, original=original,
        limit_mbps=native.LIMIT, unit="hccl-roce-" + window.root.name.removeprefix("hccl-diagnose-"))
    write(window.snapshot, state)
    shutil.copy2(Path(native.__file__), window.directory / "guard.py")
    command = ["systemd-run", "--unit=" + state["unit"], "--on-active=3600s",
        "--timer-property=AccuracySec=1s", "--property=Type=oneshot", "/usr/bin/python3",
        str(window.directory / "guard.py"), "restore", "--root", str(window.root)]
    result = dict(window_mode="single_collective", applied_verified=False,
        restored_verified=False, foreground_path_verified=True)
    target = None
    try:
        window.run(command)
        if window.run(["systemctl", "is-active", state["unit"] + ".timer"]).strip() != "active":
            raise RuntimeError("independent network rollback timer is not active")
        probe = state["unit"] + "-probe"
        rehearsal = command.copy()
        rehearsal[1:3] = ["--unit=" + probe, "--on-active=2s"]
        window.run(rehearsal)
        wait_until(window, lambda: (window.directory / "restored.json").exists(), 30)
        if read(window.directory / "restored.json").get("restored_verified") is not True:
            raise RuntimeError("independent network recovery rehearsal failed")
        window.stop_timer(probe)
        (window.control / "single-call-guard-ready").touch()
        wait_until(window, lambda: (window.control / "single-call-ready.json").exists(), 1200)
        ready = read(window.control / "single-call-ready.json")
        target = ready["identity"]
        if target["case_id"] != value["case_id"] or target["iteration"] != value["injection"]["iteration"]:
            raise ValueError("unexpected requested collective")
        identity(**target)
        validate_participants(ready, target, "ready")
        window.own_processes()
        if {str(d): window.shaping(d) for d in (native.DEVICE, native.SIBLING)} != original:
            raise RuntimeError("port state changed while ranks were draining")
        result["before"] = window.query()
        check_abort(window)
        active_timer = command.copy()
        active_timer[1:3] = ['--unit=' + state['unit'] + '-active', '--on-active=120s']
        window.run(active_timer)
        if window.run(['systemctl', 'is-active', state['unit'] + '-active.timer']).strip() != 'active':
            raise RuntimeError('short active-window rollback timer is not armed')
        result['active_rollback_seconds'] = 120
        result["apply_started_raw_ns"] = native.raw_ns()
        window.set(native.DEVICE, native.LIMIT)
        result["apply_returned_raw_ns"] = native.raw_ns()
        if (window.shaping(native.DEVICE)["limit_mbps"] != native.LIMIT
                or window.shaping(native.SIBLING) != original[str(native.SIBLING)]):
            raise RuntimeError("single-call native readback or sibling verification failed")
        result.update(applied_verified=True, first_confirmed_limit_raw_ns=native.raw_ns())
        check_abort(window)
        publish(window.control / "single-call-active.json", dict(identity=target, phase="limited",
            limit_mbps=native.LIMIT, applied_verified=True,
            confirmed_raw_ns=result["first_confirmed_limit_raw_ns"]))
        wait_until(window, lambda: (window.control / "single-call-completed.json").exists(), 90)
        completed = read(window.control / "single-call-completed.json")
        participants = validate_participants(completed, target, "completed")
        rank0 = participants[0]
        if not result["first_confirmed_limit_raw_ns"] <= rank0["submit_before_raw_ns"]:
            raise ValueError("target communication began before confirmed native limitation")
        if (window.shaping(native.DEVICE)['limit_mbps'] != native.LIMIT
                or window.shaping(native.SIBLING) != original[str(native.SIBLING)]):
            raise RuntimeError('limit expired or port settings changed before target completion')
        result.update(started_raw_ns=rank0["submit_before_raw_ns"], finished_raw_ns=rank0["raw_ns"],
            measurement_window=completed)
    except BaseException as error:
        result["error"] = str(error)
        publish(window.control / "single-call-error.json", dict(error=str(error)))
        raise
    finally:
        # No rank may submit a following call until this path verifies restoration.
        result["restore_started_raw_ns"] = native.raw_ns()
        try:
            window.restore()
            result.update(restored_verified=True, restore_verified_raw_ns=native.raw_ns())
            window.stop_timer(state['unit'] + '-active')
            window.stop_timer(state['unit'] + '-probe')
            window.stop_timer(state["unit"])
            if "measurement_window" in result:
                result["after"] = window.query()
                if (result["after"]["mac_tx_total_oct_num"] <= result["before"]["mac_tx_total_oct_num"]
                        or result["after"]["roce_tx_all_pkt_num"] <= result["before"]["roce_tx_all_pkt_num"]):
                    raise ValueError("target gated call did not prove outgoing RoCE traffic")
                if "error" not in result:
                    publish(window.control / "single-call-restored.json",
                        dict(identity=target, restored_verified=True, phase="restored"))
        except BaseException as error:
            result["restoration_or_traffic_error"] = str(error)
            if not (window.control / "single-call-error.json").exists():
                publish(window.control / "single-call-error.json", dict(error=str(error)))
            raise
        finally:
            write(window.control / "network-result.json", result)


def check_abort(window):
    if (window.control / "abort").exists():
        raise RuntimeError("single-collective limiter was cancelled")


def wait_until(window, predicate, seconds):
    deadline = time.monotonic() + seconds
    while True:
        check_abort(window)
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("bounded native single-collective wait expired")
        time.sleep(.01)


def audit_public_window(root, value, activity):
    """Post-seal audit: one real public call in each participant's held interval."""
    validate_case(value)
    measurement = activity.get('measurement_window', {})
    expected = measurement.get('identity', {})
    identity(**expected)
    if expected['case_id'] != value['case_id'] or expected['iteration'] != value['injection']['iteration']:
        raise ValueError('wrong requested single-collective window')
    done = validate_participants(measurement, expected, 'completed')
    control = root / 'gpt-output/private'
    ready = validate_participants(read(control / 'single-call-ready.json'), expected, 'ready')
    restored = read(control / 'single-call-restored.json')
    if restored.get('identity') != expected or restored.get('restored_verified') is not True:
        raise ValueError('public audit requires the matching verified restoration')
    checked = []
    for rank in RANKS:
        data = root / ('gpt-output' if rank < 4 else 'peer-preflight/gpt-output')
        public = data / 'public'
        records = [json.loads(s) for s in (public / ('roce-controls-rank-%d.jsonl' % rank)).read_text().splitlines()]
        controls = [r for r in records if r['event'] in {
            'entry_control_begin', 'entry_control_end', 'exit_control_begin', 'exit_control_end'}]
        if ([r['event'] for r in controls] != ['entry_control_begin', 'entry_control_end',
                'exit_control_begin', 'exit_control_end']
                or any(r.get('rank') != rank or r.get('identity') != expected for r in controls)):
            raise ValueError('complete distinct public control boundaries are required')
        enter, released, completed, leave = [r['clocks']['raw_ns'] for r in controls]
        calls = [json.loads(s) for s in (public / ('rank-%d.jsonl' % rank)).read_text().splitlines()]
        held = [c for c in calls if enter <= c['before']['raw_ns'] <= leave]
        if len(held) != 1:
            raise ValueError('another collective was submitted inside the held single-call window')
        call, = held
        if (call.get('rank') != rank or call.get('stage') != 'measured'
                or call.get('iteration') != expected['iteration']
                or call.get('bucket_signature') != expected['bucket_signature']
                or call.get('count') != expected['element_count']
                or call['before']['raw_ns'] != done[rank]['submit_before_raw_ns']
                or call['after']['raw_ns'] != done[rank]['submit_after_raw_ns']
                or not enter <= ready[rank]['raw_ns'] <= released
                <= call['preparation_before']['raw_ns'] <= call['before']['raw_ns']
                <= call['after']['raw_ns'] <= done[rank]['raw_ns'] <= completed <= leave):
            raise ValueError('single-call identity, public preparation or device completion differs')
        checked.append(dict(rank=rank, call_sequence=call['sequence'], identity=expected,
            control_begin_raw_ns=enter, target_start_raw_ns=call['before']['raw_ns'],
            target_completed_raw_ns=done[rank]['raw_ns'], control_end_raw_ns=leave))
    if (activity.get('window_mode') != 'single_collective' or not all(activity.get(k) for k in (
            'applied_verified', 'restored_verified', 'foreground_path_verified'))
            or activity['started_raw_ns'] != done[0]['submit_before_raw_ns']
            or activity['finished_raw_ns'] != done[0]['raw_ns']
            or not activity['first_confirmed_limit_raw_ns'] <= activity['started_raw_ns']
            < activity['finished_raw_ns'] <= activity['restore_started_raw_ns'] <= activity['restore_verified_raw_ns']):
        raise ValueError('native limitation must bracket the real target and restore before release')
    return dict(window_mode='single_collective', identity=expected, checked_ranks=checked,
        physical_port_enforcement_is_not_task_exact=True, rdma_task_presence_requires_db_audit=True,
        control_waits_separately_observed=True, training_overhead_not_comparable=True)
