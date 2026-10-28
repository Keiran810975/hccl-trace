from __future__ import annotations

import hashlib
import ast
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from test.bind_multinode_capture import bind
from test import test_single_node_capture as single_fixtures


def fixture(root):
    source = root / "source"
    source.mkdir()
    single_fixtures.PublicBindingTests().fixture(source)
    attempt = root / "attempt"
    cluster = dict(nodes=[dict(node_rank=0, node_id="node0", devices=[1, 3]),
                          dict(node_rank=1, node_id="node2", devices=[1, 3])])
    for rank in range(4):
        folder = attempt / ("node" + str(rank // 2))
        (folder / "public").mkdir(parents=True, exist_ok=True)
        (folder / "ascend_log").mkdir(exist_ok=True)
        db_dir = folder / "msprof" / ("rank-" + str(rank))
        shutil.copytree(source / "msprof" / str(rank), db_dir)
        device = (1, 3)[rank % 2]
        calls = [json.loads(line) for line in (source / "public" / ("rank-{}.jsonl".format(rank))).read_text().splitlines()]
        for call in calls:
            call["runtime_device_id"] = device
        (folder / "public" / ("rank-{}.jsonl".format(rank))).write_text("".join(json.dumps(c) + "\n" for c in calls))
        shutil.copy2(source / "public" / ("boundaries-rank-{}.jsonl".format(rank)), folder / "public")
        controls = [dict(label="configuration_sum", rank=rank, runtime_device_id=device, count=32,
                         dtype="int32", reduction="sum", before=dict(raw_ns=100), after=dict(raw_ns=300)),
                    dict(label="configuration_max", rank=rank, runtime_device_id=device, count=1,
                         dtype="int32", reduction="max", before=dict(raw_ns=400), after=dict(raw_ns=700)),
                    dict(label="configuration_device_synchronized", rank=rank, clocks=dict(raw_ns=900))]
        (folder / "public" / ("controls-rank-{}.jsonl".format(rank))).write_text("".join(json.dumps(c) + "\n" for c in controls))
        (folder / "execution.json").write_text(json.dumps(dict(status="completed", returncode=0)))
        with sqlite3.connect(db_dir / "msprof_fixture.db") as db:
            for i in range(8):
                db.execute("UPDATE STRING_IDS SET value=? WHERE id=?", ("hcom_allReduce__612_{}_1".format(i + 2), 10 + i))
            db.execute("UPDATE COMMUNICATION_OP SET deviceId=?", (device,))
            db.executemany("INSERT INTO STRING_IDS VALUES(?,?)", [(100, "hcom_allReduce__612_0_1"), (101, "hcom_allReduce__612_1_1")])
            db.executemany("INSERT INTO COMMUNICATION_OP VALUES(?,?,?,?,?)", [(device, 1, 100, 32, 2), (device, 1, 101, 1, 2)])
            db.executemany("INSERT INTO CANN_API VALUES(?,?,?)", [(1000000200, 1000000250, 2), (1000000500, 1000000600, 2)])
    cluster_path = root / "cluster.json"
    cluster_path.write_text(json.dumps(cluster))
    return attempt, cluster_path


class MultinodeCaptureTests(unittest.TestCase):
    def test_no_barrier_option_guards_every_extra_collective(self):
        tree = ast.parse((Path(__file__).parent / "multinode_commmix_train.py").read_text())
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "barrier"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "dist"):
                cursor, guarded = node, False
                while cursor in parents:
                    cursor = parents[cursor]
                    if isinstance(cursor, ast.If) and ast.unparse(cursor.test) == "not args.no_barrier":
                        guarded = True
                self.assertTrue(guarded, "unrecorded barrier would invalidate the public call binding")

    def test_binds_all_nodes_controls_business_and_real_device_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt, cluster = fixture(root)
            source = attempt / "node0/msprof/rank-0/msprof_fixture.db"
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "bound"
            manifest = bind(attempt, cluster, output, "capture")
            self.assertEqual([n["node_id"] for n in manifest["nodes"]], ["node0", "node2"])
            self.assertEqual([(r["user_rank"], r["device_id"]) for r in manifest["ranks"]], [(0, 1), (1, 3), (2, 1), (3, 3)])
            self.assertEqual(len(manifest["operations"]), 10)
            mapping = json.loads((output / "iteration-map.json").read_text())
            self.assertEqual(len(mapping["operations"]), 8)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            self.assertEqual(len(list((output / "foreground").rglob("msprof_*.db"))), 4)
            self.assertNotIn("injection", json.dumps(mapping))
            with self.assertRaises(FileExistsError):
                bind(attempt, cluster, output, "capture")

    def test_rejects_missing_control_api_and_mismatched_capture(self):
        for failure in ("control", "api", "dtype", "execution"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                attempt, cluster = fixture(root)
                if failure == "control":
                    (attempt / "node0/public/controls-rank-0.jsonl").write_text("")
                elif failure == "execution":
                    (attempt / "node0/execution.json").write_text(json.dumps(dict(status="failed", returncode=1)))
                else:
                    with sqlite3.connect(attempt / "node0/msprof/rank-0/msprof_fixture.db") as db:
                        db.execute("UPDATE CANN_API SET startNs=0" if failure == "api" else
                                   "UPDATE COMMUNICATION_OP SET dataType=0")
                with self.assertRaises(ValueError):
                    bind(attempt, cluster, root / "bound", "capture")

    def test_background_db_is_not_used_or_renumbered_as_foreground(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt, cluster = fixture(root)
            with sqlite3.connect(attempt / "node0/msprof/msprof_background.db") as db:
                db.execute("CREATE TABLE BACKGROUND(value INTEGER)")
            manifest = bind(attempt, cluster, root / "bound", "capture")
            self.assertEqual(len(list(Path(manifest["nodes"][0]["msprof_db_dir"]).rglob("*.db"))), 2)

    def test_different_node_local_names_use_public_binding_not_string_equality(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt, cluster = fixture(root)
            for path in (attempt / "node1/msprof").rglob("msprof_*.db"):
                with sqlite3.connect(path) as db:
                    db.execute("UPDATE STRING_IDS SET value='remote_group' WHERE id=1")
                    db.execute("UPDATE STRING_IDS SET value=REPLACE(value,'__612_','__999_')")
            manifest = bind(attempt, cluster, root / "bound", "capture")
            members = manifest["operations"][0]["members"]
            self.assertNotEqual(members[0]["group_name"], members[1]["group_name"])
            self.assertNotEqual(members[0]["op_name"], members[1]["op_name"])


if __name__ == "__main__":
    unittest.main()
