"""Remove retired critical-path annotations at the public report boundary."""
from __future__ import annotations


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
