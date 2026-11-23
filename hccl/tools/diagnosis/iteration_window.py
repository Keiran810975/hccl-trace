"""A contiguous, rank-local slice with an exact target-iteration boundary."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .clock_alignment import raw_to_profiler


@dataclass(frozen=True)
class IterationWindow:
    target: int
    first: int
    bounds: dict
    scopes: frozenset
    target_scopes: frozenset

    @staticmethod
    def _overlaps(start, stop, begin, end):
        if start == stop:
            return begin <= start < end
        return max(start, begin) < min(stop, end)

    def keep_row(self, row):
        begin, _, end = self.bounds[row["node_id"], int(row["device_id"])]
        return self._overlaps(Decimal(row["task_start"])*1000, Decimal(row["task_stop"])*1000,
                              begin, end)

    def target_row(self, row):
        _, begin, end = self.bounds[row["_node_id"], row["_device_id"]]
        return self._overlaps(row["_start_ns"], row["_stop_ns"], begin, end)


def _coordinate(call):
    return tuple(call[k] for k in ("group_id", "stage", "iteration", "call_site", "occurrence"))


def from_observations(target, manifest, observations, inventory, coordinates, *, lookback=10, locations=None):
    windows = {}
    points = {}
    target_locations = set()
    for header, calls, markers in observations.values():
        rank = header["user_rank"]
        node, device = header["node_id"], header["device_id"]
        key = manifest["run_id"]+"/"+node, device
        facts = {m["iteration"]: (m["before"]["raw_ns"], m["after"]["raw_ns"])
                 for m in markers if m["stage"] == "measured"}
        if target not in facts or key in windows:
            raise ValueError("whole-iteration diagnosis requires a unique finished iteration marker on every Rank")
        data = inventory[node][device]
        if data["clock_stop"] is None:
            raise ValueError("whole-iteration diagnosis requires both local profiler clock endpoints")
        points[key] = data["clock_start"], data["clock_stop"]
        windows[key] = facts
        target_calls = [c for c in calls if c["stage"] == "measured" and c["iteration"] == target]
        if any(not facts[target][0] <= c["before"]["raw_ns"] <= c["completion_raw_ns"] <= facts[target][1]
               for c in target_calls):
            raise ValueError(f"Rank {rank} did not observe completion within the target iteration")
        target_locations.update(_coordinate(c) for c in target_calls)
    if len(windows) != len(manifest["ranks"]) or not target_locations:
        raise ValueError("target iteration is missing Rank coverage or collective calls")
    if locations is not None:
        if not locations or not locations <= target_locations:
            raise ValueError("requested collective is missing from the closed iteration")
        target_locations = locations
    common = set.intersection(*(set(markers) for markers in windows.values()))
    first = target
    while first - 1 in common and first > target - lookback:
        first -= 1
    bound = {_coordinate(c): c["operation_scope"] for c in coordinates}
    if target_locations - bound.keys():
        raise ValueError("not all target iteration collective calls are uniquely bound")
    scopes = frozenset(c["operation_scope"] for c in coordinates
                       if c["stage"] == "measured" and first <= c["iteration"] <= target)
    bounds = {key: tuple(raw_to_profiler(v, *points[key]) for v in
              (markers[first][0], markers[target][0], markers[target][1])) for key, markers in windows.items()}
    return IterationWindow(target, first, bounds, scopes, frozenset(bound[c] for c in target_locations))
