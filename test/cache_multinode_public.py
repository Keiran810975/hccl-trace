"""Extract verified public diagnosis facts, never private controls or evaluations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


PUBLIC_FACTS = ("source_selection.json", "clock_alignment.json", "cross_node/segments.csv",
                "node0/communication_tasks.csv", "node3/communication_tasks.csv")
GRAPH_FACTS = ("rolling/task_comparison.csv", "dep_graph_nodes.csv", "dep_graph_edges.csv")


def extract(source, output, *, graph=False):
    manifest = json.loads((source / "manifest.json").read_text())
    verified = json.loads((source / "verified.json").read_text())
    if (not verified.get("file_hashes_verified") or hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()).hexdigest() != verified["manifest_sha256"]):
        raise ValueError("verified archive manifest required")
    choices = [name for name in manifest["files"] if name.endswith("/source_selection.json")]
    if len(choices) != 1 or not choices[0].startswith("report.debug/analysis/"):
        raise ValueError("unique public source-selection artifact required")
    prefix = choices[0].removesuffix("source_selection.json")
    wanted = {prefix + name: name for name in PUBLIC_FACTS + (GRAPH_FACTS if graph else ())}
    if not set(wanted) <= manifest["files"].keys():
        raise ValueError("archive lacks required public facts")
    output.mkdir(parents=True, exist_ok=False)
    facts = {}
    with tarfile.open(source / "replay.tar.gz", "r|gz") as archive:
        for member in archive:
            if member.name not in wanted:
                continue
            name = wanted[member.name]
            expected = manifest["files"][member.name]
            if not member.isfile() or member.size != expected["size"] or name in facts:
                raise ValueError("public member differs from verified manifest")
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.extractfile(member) as data, target.open("xb") as stream:
                for chunk in iter(lambda: data.read(8 * 1024 * 1024), b""):
                    stream.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError("public member content changed")
            facts[name] = expected
            if len(facts) == len(wanted):
                break
    if len(facts) != len(wanted):
        raise ValueError("archive is incomplete")
    receipt = dict(schema_version=1, source_archive=str((source / "replay.tar.gz").resolve()),
                   original_archive_sha256=verified["archive_sha256"], files=facts,
                   truth_accessed=False, extraction_scope="public_analysis_artifacts_only")
    (output / "public-inputs.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--graph", action="store_true")
    args = parser.parse_args()
    result = extract(args.source, args.output, graph=args.graph)
    print(json.dumps(dict(files=len(result["files"]), truth_accessed=False)))
