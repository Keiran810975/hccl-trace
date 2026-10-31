from __future__ import annotations

from copy import deepcopy
import unittest

from .auxiliary_operations import bind_auxiliary


class AuxiliaryTests(unittest.TestCase):
    def fixture(self):
        bound, inventory = {}, {}
        for index in (0, 1):
            node = "node" + str(index)
            ops = [dict(kind=kind, dataType=4, count=count, group_name="local-group", op_name="opaque-" + str(n),
                        connectionId=n, api=dict(startNs=n * 100, endNs=n * 100 + 20))
                   for n, kind, count in ((0, "allreduce", 100), (1, "broadcast", 13), (2, "allreduce", 100))]
            inventory[node] = {7: dict(operations=ops)}
            for sequence, op in ((0, ops[0]), (1, ops[2])):
                key = ("dp", "warmup", sequence, "grad", 0)
                bound.setdefault(key, []).append(dict(user_rank=index, node_id=node, device_id=7,
                    call=dict(sequence=sequence), op=op))
        return bound, inventory

    def test_unique_complete_brackets_bind_without_any_cross_rank_name_assumption(self):
        bound, inventory = self.fixture()
        inventory["node1"][7]["operations"][1]["op_name"] = "a-different-local-name"
        operations, evidence = bind_auxiliary(bound, inventory, ["Broadcast"])
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["participants"], [0, 1])
        self.assertTrue(evidence[0]["auxiliary_control"])

    def test_missing_member_duplicate_shape_and_outside_bracket_are_not_guessed(self):
        bound, inventory = self.fixture()
        del inventory["node1"][7]["operations"][1]
        with self.assertRaisesRegex(ValueError, "participant"):
            bind_auxiliary(bound, inventory, ["Broadcast"])
        bound, inventory = self.fixture()
        duplicate = deepcopy(inventory["node0"][7]["operations"][1])
        duplicate["connectionId"] = 8
        inventory["node0"][7]["operations"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            bind_auxiliary(bound, inventory, ["Broadcast"])
        bound, inventory = self.fixture()
        for node in inventory:
            inventory[node][7]["operations"][1]["api"] = dict(startNs=300, endNs=320)
        self.assertEqual(bind_auxiliary(bound, inventory, ["Broadcast"]), ([], []))


if __name__ == "__main__":
    unittest.main()
