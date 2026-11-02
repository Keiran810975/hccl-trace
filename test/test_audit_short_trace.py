from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test.audit_short_trace import communication_fact


class ShortTraceAuditTests(unittest.TestCase):
    def test_original_db_identity_and_peer_are_read_without_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "capture").mkdir()
            path = root / "capture/msprof_fixture.db"
            with sqlite3.connect(path) as db:
                db.executescript("CREATE TABLE TASK(deviceId,streamId,taskId,startNs,endNs,globalTaskId);"
                    "CREATE TABLE COMMUNICATION_TASK_INFO(globalTaskId,srcRank,dstRank,size,transportType,taskType);"
                    "CREATE TABLE STRING_IDS(id,value);"
                    "INSERT INTO TASK VALUES(3,90,1539,1000,2000,8);"
                    "INSERT INTO COMMUNICATION_TASK_INFO VALUES(8,5,4,33554432,0,1);"
                    "INSERT INTO STRING_IDS VALUES(1,'Reduce_Inline');")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            row = dict(_device_id=3, _stream_id=90, _task_id=1539, _start_order=Decimal(1),
                       _start=1, profiler_task_index="8:1000", _peer_rank=4, _user_rank=5)
            fact = communication_fact(root, row)
            self.assertEqual(fact["executing_rank"], 5)
            self.assertEqual(fact["semantic_peer_rank"], 4)
            self.assertFalse(fact["physical_fault_owner_proven"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            row["profiler_task_index"] = "9:1000"
            with self.assertRaisesRegex(ValueError, "physical task index"):
                communication_fact(root, row)
            row["_task_id"] += 1
            self.assertIsNone(communication_fact(root, row))
