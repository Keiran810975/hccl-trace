"""Lossless local backup of one completed owned attempt, before deleting its raw copies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile


def ssh_arguments():
    command = ["ssh", "-i", str(Path.home() / ".ssh/id_rsa_k1"), "-o", "IdentitiesOnly=yes",
       "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
       "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=2"]
    control = os.environ.get("HCCL_DIAG_SSH_CONTROL_PATH")
    if control:
        if not Path(control).is_absolute():
            raise ValueError("SSH control path must be absolute")
        command += ["-o", "ControlMaster=auto", "-o", "ControlPersist=600", "-o", "ControlPath=" + control]
    return command + ["commTeam@heter.2.heroism.win"]


SSH = ssh_arguments()
REPORTS = {"report/" + name for name in ("execution.html", "root_causes.json", "propagation.html")}
MEMBERS = ("src", "input", "capture", "report.debug", "report", "gpt-output", "peer-preflight", "logs",
           "security", "network", "hold", "evaluation.json", "communication-impact.json", "authorized-state.json",
           "preflight-state.json", "network-port-evidence.json", "cleanup-receipt.json", "node3-preflight.tar",
           "retain-all-evidence.json", "diagnosis-seal.json", "build-receipt.json", "deployment.json",
           "source-snapshot.json", "retain-until-verified-archive.json")
MEMBERS += ('effect-evidence.json', 'authorization.json', 'restoration-verified.json')
MEMBERS += ('cpu-recovery.json', 'cpu-recovery-transport.json', 'network-observation-unavailable.json')
MEMBERS += ('failure-restoration-audit.json',)
MEMBERS += ('postdiagnosis-evaluator', 'effect-source-revision.json')
REMOVE = ("capture", "report.debug", "peer-preflight", "node3-preflight.tar", "report/execution.html")


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def case_name(name):
    calibration = bool(re.fullmatch(r"hccl-diagnose-node03-20261101-2\d\d", name)) and not name.endswith("-200")
    dual = bool(re.fullmatch(r"hccl-diagnose-node03-20261103-52[1-6]", name))
    repeated = name in ({'hccl-diagnose-node03-20261105-' + str(i) for i in range(901, 921)}
                       | {'hccl-diagnose-node03-20261106-' + str(i) for i in range(1002, 1021)})
    if not (calibration or dual or repeated):
        raise ValueError("only reviewed calibration attempts or new dual cases 521..526 are accepted")
    return name


def command(node, argv):
    if node not in (0, 3):
        raise ValueError("only Node0 and Node3 are allowed")
    rendered = shlex.join(argv)
    if node == 3:
        peer = ["ssh", "-i", "/home/commTeam/.ssh/KeyPair-f1dd.pem", "-o", "IdentitiesOnly=yes",
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
                "root@192.169.0.220", rendered]
        rendered = shlex.join(peer)
    return SSH + [rendered]


def remote_json(node, code, timeout=240):
    try:
        result = subprocess.run(command(node, ["docker", "exec", "zjy-new", "python3", "-c", code]),
                                capture_output=True, text=True, check=True, timeout=timeout)
    except subprocess.CalledProcessError as error:
        raise RuntimeError('bounded archive query failed (exit {}): {}'.format(
            error.returncode, (error.stderr or '')[-1500:])) from error
    return json.loads(result.stdout)


def manifest_code(base):
    return """import hashlib,json,pathlib
base=pathlib.Path(BASE)
assert base.is_dir() and not base.is_symlink()
assert json.loads((base/'security/restored.json').read_text())['restored']
assert json.loads((base/'hold/state.json').read_text())['status']=='released'
names=[n for n in NAMES if (base/n).exists()]
files={}
for name in names:
 p=base/name
 for q in ([p] if p.is_file() else sorted(p.rglob('*'))):
  if q.is_dir() and not q.is_symlink(): continue
  assert q.resolve().is_relative_to(base.resolve()),str(q)
  if q.is_symlink(): raise ValueError('unexpected symlink in completed capture: '+str(q))
  h=hashlib.sha256()
  with q.open('rb') as f:
   for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
  files[str(q.relative_to(base))]=dict(size=q.stat().st_size,sha256=h.hexdigest())
d=dict(schema_version=1,base=str(base),names=names,files=files)
(base/'offload-manifest.json').write_text(json.dumps(d,sort_keys=True)+'\\n')
print(json.dumps(d))
""".replace("BASE", repr(base)).replace("NAMES", repr(MEMBERS))


def verify_archive(archive, manifest, reports=None):
    found = set()
    regular = set()
    if reports is not None:
        reports.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.name in found:
                raise ValueError("unsafe or repeated archive member")
            if member.isdir():
                continue
            expected = manifest["files"].get(member.name)
            if member.islnk() and manifest.get('content_deduplicated') is True:
                target_path = PurePosixPath(member.linkname)
                target = manifest['files'].get(member.linkname)
                if (expected is None or target is None or member.size != 0 or member.linkname not in regular
                        or target_path.is_absolute() or '..' in target_path.parts
                        or target['size'] != expected['size'] or target['sha256'] != expected['sha256']
                        or member.name in REPORTS):
                    raise ValueError('unsafe or unverified content-deduplicated hardlink')
                found.add(member.name)
                continue
            if not member.isfile() or expected is None or member.size != expected["size"]:
                raise ValueError("archive member differs from frozen manifest: " + member.name)
            source = stream.extractfile(member)
            digest = hashlib.sha256()
            target = ((reports / path.name).open("xb") if reports is not None and member.name in REPORTS else None)
            try:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
                    if target:
                        target.write(chunk)
            finally:
                if target:
                    target.close()
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError("archive content hash differs: " + member.name)
            found.add(member.name)
            regular.add(member.name)
    if found != set(manifest["files"]):
        raise ValueError("archive is incomplete")
    return found


def backup(node, name, output):
    base = "/workspace/" + case_name(name)
    directory = output / ("node" + str(node))
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / "verified.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        archive = directory / "replay.tar.gz"
        if file_hash(archive) != receipt["archive_sha256"]:
            raise ValueError("local verified archive changed")
        return receipt
    manifest = remote_json(node, manifest_code(base))
    deduplicate = name in ({'hccl-diagnose-node03-20261105-' + str(i) for i in range(901, 921)}
                          | {'hccl-diagnose-node03-20261106-' + str(i) for i in range(1002, 1021)})
    if deduplicate:
        manifest['content_deduplicated'] = True
    if not manifest["files"]:
        raise ValueError("empty completed capture manifest")
    if shutil.disk_usage(output).free < 30 * 1024**3:
        raise RuntimeError("less than 30GiB free for local lossless backup")
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive = directory / "replay.tar.gz"
    partial = directory / "replay.tar.gz.partial"
    if partial.exists() or archive.exists():
        raise ValueError("unfinished backup exists; inspect it before retrying")
    cmd = command(node, ["docker", "exec", "zjy-new", "tar", "--hard-dereference", "-czf", "-", "-C", base] + manifest["names"])
    if deduplicate:
        # Keep native replay files lossless, but store duplicate DB copies only once.
        code = """import json,pathlib,sys,tarfile
base=pathlib.Path(BASE)
manifest=json.loads((base/'offload-manifest.json').read_text())
seen={}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
 for name,record in sorted(manifest['files'].items()):
  path=base/name
  assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(base.resolve())
  item=archive.gettarinfo(str(path),arcname=name)
  key=(record['size'],record['sha256'],item.mode,item.uid,item.gid)
  if key in seen and name not in REPORTS:
   item.type=tarfile.LNKTYPE;item.linkname=seen[key];item.size=0
   archive.addfile(item)
  else:
   with path.open('rb') as stream:archive.addfile(item,stream)
   seen[key]=name
""".replace('BASE', repr(base)).replace('REPORTS', repr(REPORTS))
        # The manifest digest must be identical on both ends before any cleanup.
        remote_json(node, "import json,pathlib;p=pathlib.Path(" + repr(base + '/offload-manifest.json') + ");d=json.loads(p.read_text());d['content_deduplicated']=True;p.write_text(json.dumps(d,sort_keys=True)+'\\n');print('{}')")
        cmd = command(node, ['docker', 'exec', 'zjy-new', 'python3', '-c', code])
    with partial.open("xb") as target:
        process = subprocess.Popen(cmd, stdout=target, stderr=subprocess.PIPE)
        try:
            _, stderr = process.communicate(timeout=1800)
        except BaseException:
            process.kill()
            process.communicate(timeout=30)
            raise
        if process.returncode:
            raise RuntimeError("backup transfer failed: " + stderr.decode(errors="replace")[-1500:])
    partial.rename(archive)
    reports = output / "report" if node == 0 else None
    verify_archive(archive, manifest, reports)
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    receipt = dict(node=node, base=base, archive=str(archive.resolve()), archive_sha256=digest.hexdigest(),
                   file_count=len(manifest["files"]), file_hashes_verified=True,
                   manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest())
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def cleanup(node, name, receipt):
    base = "/workspace/" + case_name(name)
    code = """import pathlib,json,hashlib,shutil
base=pathlib.Path(BASE)
assert not (base/'retain-all-evidence.json').exists(),'explicit retain-all-evidence lock forbids remote deletion'
d=json.loads((base/'offload-manifest.json').read_text())
assert hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()==DIGEST
assert json.loads((base/'security/restored.json').read_text())['restored']
assert json.loads((base/'hold/state.json').read_text())['status']=='released'
for name in REMOVE:
 p=base/name
 if not p.exists():continue
 assert p.resolve().is_relative_to(base.resolve()) and not p.is_symlink()
 if p.is_dir():
  items=[q for q in p.rglob('*') if q.is_file()]
 else: items=[p]
 for q in items:
  key=str(q.relative_to(base))
  assert key in d['files'],key
  h=hashlib.sha256()
  with q.open('rb') as f:
   for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
  assert h.hexdigest()==d['files'][key]['sha256'],key
for name in REMOVE:
 p=base/name
 if p.is_dir():shutil.rmtree(p)
 elif p.exists():p.unlink()
print(json.dumps(dict(raw_removed=True,only_this_attempt=True)))
""".replace("BASE", repr(base)).replace("DIGEST", repr(receipt["manifest_sha256"])).replace("REMOVE", repr(REMOVE))
    return remote_json(node, code, timeout=600)


def offload(name, destination, *, remove_remote):
    case_name(name)
    output = destination / name
    output.mkdir(parents=True, exist_ok=True)
    receipts = [backup(n, name, output) for n in (0, 3)]
    clean = [cleanup(n, name, receipt) for n, receipt in zip((0, 3), receipts)] if remove_remote else []
    result = dict(status="verified", case_directory="/home/commTeam/zjy/zjy-new-workspace/" + name,
                  local_archive_sha256=[r["archive_sha256"] for r in receipts],
                  file_hashes_verified=True, owned_raw_removed=bool(clean), receipts=receipts,
                  local_report_files=[str((output / path).resolve()) for path in REPORTS],
                  original_server_execution_archived_not_discarded=True)
    # The acknowledgment is written only after both backups and all per-file checks pass.
    if remove_remote:
        code = "import pathlib,json;p=pathlib.Path(" + repr("/workspace/" + name + "/offload-receipt.json") + ");p.write_text(" + repr(json.dumps(result)) + ");print('{}')"
        remote_json(0, code)
    (output / "offload-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remove-verified-remote-raw", action="store_true")
    args = parser.parse_args()
    print(json.dumps(offload(args.case, args.output, remove_remote=args.remove_verified_remote_raw)))


if __name__ == "__main__":
    main()
