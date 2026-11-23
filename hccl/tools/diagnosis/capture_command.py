"""Small node-local msprof wrapper and verified local capture assembly."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading

from .capture_discovery import write_json, read_json
from .multi_node_trace import _name
from .parse_msprof_db import _device_ids, _readonly_connection, discover_db_files


def _complete_sdk_logs(directory):
    from .workload_binder import _read_calls
    paths = sorted(Path(directory).glob('rank-*.jsonl'))
    if not paths:
        raise ValueError('missing consolidated DB or Trace SDK logs; add training observations and keep the raw capture')
    logs = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError('SDK logs must be ordinary files: ' + str(path))
        runtime, calls = _read_calls(path)
        if not calls:
            raise ValueError('SDK rank needs explicit collective observations; iteration markers alone are not sufficient')
        logs.append((path, runtime))
    return logs


def _node_capture_logs(calls_dir, msprof_dir):
    logs = _complete_sdk_logs(calls_dir)
    ranks = {runtime['user_rank'] for _, runtime in logs}
    devices = {runtime['device_id'] for _, runtime in logs}
    if len(ranks) != len(logs) or len(devices) != len(logs):
        raise ValueError('node capture needs one SDK runtime per Rank and profiler device')
    profiled = set()
    for path in discover_db_files(msprof_dir):
        with closing(_readonly_connection(str(path))) as db:
            ids = _device_ids(db)
        if len(ids) != 1 or profiled.intersection(ids):
            raise ValueError('node capture needs one consolidated DB per profiler device')
        profiled.update(ids)
    if profiled != devices:
        raise ValueError('consolidated DB devices differ from complete SDK runtimes')
    return logs


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def _capture_files(node):
    files = set()
    for path in node.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('capture assembly accepts only ordinary files/directories, not symlinks')
        if path.is_file():
            files.add(path.relative_to(node))
    return files


def add_commands(sub):
    capture = sub.add_parser('capture', aliases=['cap'], help='capture your unchanged training launcher on this node')
    capture.add_argument('-o', '--output', type=Path, default=Path('capture'))
    capture.add_argument('--node', default=None, help='default: actual hostname')
    capture.add_argument('--run-id', default=None, help='shared across nodes; default: output directory name')
    capture.add_argument('application', nargs=argparse.REMAINDER, help='-- torchrun ... or your launcher')
    join = sub.add_parser('join', help='assemble already transferred node captures without changing inputs')
    join.add_argument('inputs', type=Path, nargs='+')
    join.add_argument('-o', '--output', type=Path, required=True)


def capture(output, application, *, node=None, run_id=None):
    application = list(application)
    if application[:1] == ['--']:
        application.pop(0)
    if not application:
        raise ValueError('capture needs -- followed by your training launcher')
    if sys.platform != 'linux':
        raise ValueError('online capture requires the Linux/CANN training host; offline analyze is portable')
    profiler = shutil.which('msprof')
    if profiler is None:
        raise ValueError('msprof was not found; load the CANN environment first')
    if threading.current_thread() is not threading.main_thread():
        raise ValueError('capture must run on the main thread for signal cleanup')
    output = Path(output).absolute()
    node = _name(node or os.environ.get('HCCL_TRACE_NODE_ID') or socket.gethostname())
    run_id = _name(run_id or os.environ.get('HCCL_TRACE_RUN_ID') or output.name)
    if output.is_symlink() or (output / 'nodes').is_symlink():
        raise ValueError('capture output cannot be a symlink')
    target = output / 'nodes' / node
    target.mkdir(parents=True, exist_ok=False)
    for name in ('plog', 'calls'):
        (target / name).mkdir()
    env = dict(os.environ, HCCL_STEP_TRACE='1', HCCL_TASK_SEMANTIC_TRACE='1',
        HCCL_TRACE_NODE_ID=node, HCCL_TRACE_RUN_ID=run_id,
        HCCL_TRACE_CALLS_DIR=str(target / 'calls'), ASCEND_PROCESS_LOG_PATH=str(target / 'plog'),
        ASCEND_GLOBAL_LOG_LEVEL='2', ASCEND_SLOG_PRINT_TO_STDOUT='0')
    env.pop('ASCEND_MODULE_LOG_LEVEL', None)
    command = [profiler, '--application=' + shlex.join(application), '--output=' + str(target / 'msprof'),
               '--hccl=on', '--task-time=l1', '--ascendcl=on', '--ai-core=off', '--type=db']
    state = dict(node_id=node, run_id=run_id, status='capturing', application=application,
        capture_profile='low_log_l1_no_pmu', compatible_modified_host_device_required=True,
        numerical_correctness_verified=False, device_settings_changed=False)
    write_json(target / 'collection.json', state)
    previous_handler = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        error = KeyboardInterrupt('capture interrupted by signal {}'.format(signum))
        error.signum = signum
        raise error
    try:
        signal.signal(signal.SIGTERM, interrupted)
        with (target / 'profiler.log').open('x') as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = child.wait()
            except BaseException:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=30)
                raise
        if code:
            raise ValueError('training/profiler exited with code %d; raw data retained' % code)
        logs = _node_capture_logs(target/'calls', target/'msprof')
        for _, runtime in logs:
            if runtime['run_id'] != run_id or runtime['node_id'] != node:
                raise ValueError('SDK runtime identity disagrees with this node capture')
        state['status'] = 'captured_not_yet_diagnosed'
        return state
    except BaseException as error:
        state.update(status='failed', error=str(error))
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        write_json(target / 'collection.json', state)


def join(inputs, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('join output must be a fresh directory')
    sources, ids, descriptions, ranks, operations, auxiliary = {}, set(), {}, {}, {}, set()
    world_sizes, clock_limits = set(), set()
    for source in inputs:
        source = Path(source)
        if source.is_symlink() or (source/'nodes').is_symlink():
            raise ValueError('capture assembly refuses symlinks')
        source = source.resolve()
        if output.resolve() == source or source in output.resolve().parents:
            raise ValueError('join output cannot be inside capture inputs')
        metadata_path = source/'capture.json'
        if metadata_path.is_symlink():
            raise ValueError('capture assembly refuses symlinks')
        metadata = read_json(metadata_path) if metadata_path.is_file() else {}
        if not isinstance(metadata, dict):
            raise ValueError('capture.json must contain an object')
        if 'clock_alignment_max_error_ns' in metadata:
            clock_limit = metadata['clock_alignment_max_error_ns']
            if type(clock_limit) is not int or clock_limit <= 0:
                raise ValueError('clock error tolerance must be a positive integer')
            clock_limits.add(clock_limit)
        nodes = metadata.get('nodes', [])
        if not isinstance(nodes, list) or any(not isinstance(n, dict) or not isinstance(n.get('node_id'), str) for n in nodes):
            raise ValueError('capture.json nodes must declare unique node identities')
        declarations = {n['node_id']:n for n in nodes}
        if len(declarations) != len(nodes):
            raise ValueError('capture.json contains duplicate node declarations')
        extras = metadata.get('sdk_auxiliary_operation_types', [])
        if not isinstance(extras, list) or any(not isinstance(kind, str) for kind in extras):
            raise ValueError('invalid auxiliary operation type declarations')
        auxiliary.update(extras)
        bindings = metadata.get('operations', [])
        if not isinstance(bindings, list) or any(not isinstance(op, dict) or not isinstance(op.get('operation_id'), str) for op in bindings):
            raise ValueError('invalid operation binding declarations')
        for operation in bindings:
            key = operation['operation_id']
            if key in operations and operations[key] != operation:
                raise ValueError('conflicting operation binding in joined captures')
            operations[key] = operation
        for node in sorted((source / 'nodes').iterdir()):
            if node.is_symlink():
                raise ValueError('symlink node capture is not accepted')
            if not node.is_dir():
                continue
            if node.name in sources:
                raise ValueError('duplicate or invalid node capture')
            _name(node.name)
            expected_files = _capture_files(node)
            description = dict(declarations.get(node.name, dict(node_id=node.name)))
            for key in ('plog_dir', 'msprof_db_dir', 'calls_dir'):
                if key in description:
                    if not isinstance(description[key], str) or not description[key]:
                        raise ValueError('declared node paths must be nonempty strings: ' + key)
                    original = Path(description[key])
                    original = original if original.is_absolute() else source/original
                    relative = original.resolve().relative_to(node.resolve())
                    description[key] = str(Path('nodes')/node.name/relative)
            state_path = node/'collection.json'
            state = read_json(state_path) if state_path.is_file() else None
            if state_path.exists() and (not isinstance(state, dict) or state.get('node_id') != node.name
                    or state.get('status') != 'captured_not_yet_diagnosed'):
                raise ValueError('join requires a successfully finished node capture: ' + node.name)
            calls_dir = source/description.get('calls_dir', str(Path('nodes')/node.name/'calls'))
            msprof_dir = source/description.get('msprof_db_dir', str(Path('nodes')/node.name/'msprof'))
            logs = _node_capture_logs(calls_dir, msprof_dir)
            for _, runtime in logs:
                if runtime['node_id'] != node.name:
                    raise ValueError('node directory differs from actual SDK node identity')
                ids.add(runtime['run_id'])
                if (metadata.get('run_id', runtime['run_id']) != runtime['run_id']
                        or (state is not None and state.get('run_id') != runtime['run_id'])):
                    raise ValueError('capture metadata conflicts with SDK run identity')
                if 'world_size' in runtime:
                    world_sizes.add(runtime['world_size'])
                rank = {k:runtime[k] for k in ('node_id','user_rank','device_id')}
                if runtime['user_rank'] in ranks:
                    raise ValueError('global rank occurs on more than one joined runtime')
                ranks[runtime['user_rank']] = rank
            sources[node.name] = node, expected_files
            for key in ('clock_probe_files', 'clock_validation_files'):
                if key not in description:
                    continue
                if (not isinstance(description[key], list)
                        or any(not isinstance(p, str) or not p for p in description[key])):
                    raise ValueError(key + ' must be a list of node-local paths')
                description[key] = [str(Path('nodes')/node.name/(source/p).resolve().relative_to(node.resolve()))
                                    for p in description[key]]
            descriptions[node.name] = description
    if len(ids) != 1 or not sources:
        raise ValueError('all node captures must belong to one shared run_id')
    world_size = next(iter(world_sizes), None)
    if len(world_sizes) > 1 or (world_size is not None and (len(ranks) != world_size or max(ranks) >= world_size)):
        raise ValueError('joined Rank coverage differs from SDK WORLD_SIZE')
    if len(clock_limits) > 1:
        raise ValueError('joined captures disagree on clock error tolerance')
    output.parent.mkdir(parents=True, exist_ok=True)
    verified = {}
    with TemporaryDirectory(prefix='.hccl-join-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'capture'
        for name, (source, expected) in sources.items():
            target = stage / 'nodes' / name
            shutil.copytree(source, target, symlinks=True)
            if _capture_files(source) != expected or _capture_files(target) != expected:
                raise ValueError('capture file inventory changed during assembly')
            for relative in sorted(expected):
                value = _digest(source / relative)
                if value != _digest(target / relative):
                    raise ValueError('capture copy hash mismatch')
                verified[str(Path('nodes') / name / relative)] = value
        run_id = ids.pop()
        metadata = dict(run_id=run_id, nodes=list(descriptions.values()), ranks=list(ranks.values()), operations=list(operations.values()))
        if auxiliary:
            metadata['sdk_auxiliary_operation_types'] = sorted(auxiliary)
        if clock_limits:
            metadata['clock_alignment_max_error_ns'] = clock_limits.pop()
        write_json(stage/'capture.json', metadata)
        result = dict(status='assembled', run_id=run_id, node_count=len(sources), sha256=verified)
        write_json(stage / 'assembly.json', result)
        if output.exists() or output.is_symlink():
            raise ValueError('join output must remain a fresh directory')
        stage.rename(output)
    return result


def dispatch(args):
    if args.command == 'join':
        result = join(args.inputs, args.output)
    else:
        result = capture(args.output, args.application, node=args.node, run_id=args.run_id)
    print('status={} output={}'.format(result['status'], args.output.absolute()))
    return 0
