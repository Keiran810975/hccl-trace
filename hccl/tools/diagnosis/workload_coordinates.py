"""Public workload locations shared by legacy and SDK-based captures."""
from __future__ import annotations


def position(item):
    if item.get("group_id") is not None:
        return ("named", item["group_id"], item["call_site"], item["occurrence"])
    return ("legacy", item["block"], item["bucket"])


def location_fields(item):
    fields = {k: item.get(k) for k in ("stage", "iteration", "block", "bucket")}
    if item.get("group_id") is not None:
        fields.update({k: item[k] for k in ("group_id", "call_site", "occurrence")})
    return fields
