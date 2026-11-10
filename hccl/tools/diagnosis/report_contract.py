"""Remove retired critical-path annotations at the public report boundary."""
from __future__ import annotations


CLEAN_TASK_REFERENCE = "previous_non_slow_task_mean"


def rolling_reference(reference_mode):
    reference = dict(kind="previous_five_measured", statistic="mean", window=5)
    if reference_mode == CLEAN_TASK_REFERENCE:
        reference.update(kind=CLEAN_TASK_REFERENCE, minimum_samples=1,
                         exclude_flagged=["duration_slow", "gap_slow"], host_preparation_kind="previous_five_measured")
    return reference


def without_critical_path(value):
    def retired(key):
        name = str(key).lower().replace('_', '')
        return ('criticalpath' in name or name in {'modeledexecutiongainns', 'modelgain',
                'localmodelexecutiongainns', 'localmodelimpactstatus'})
    if isinstance(value, dict):
        return {k: without_critical_path(v) for k, v in value.items() if not retired(k)}
    if isinstance(value, list):
        return [without_critical_path(v) for v in value if not (
            isinstance(v, str) and ('critical-path' in v.lower() or 'critical path' in v.lower() or '关键路径' in v))]
    return value
