"""Display-only clock mapping from independent before/after network probes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from .parse_msprof_db import _readonly_connection, _device_ids, discover_db_files


@dataclass(frozen=True)
class DeviceClock:
    node_id: str
    device_id: int
    profiler_to_raw_offset_ns: int
    local_anchor_ns: int
    reference_anchor_ns: int
    rate_numerator: int
    rate_denominator: int
    valid_start_ns: int
    valid_stop_ns: int
    estimated_error_ns: int

    def map_ns(self, timestamp_ns):
        raw = timestamp_ns - self.profiler_to_raw_offset_ns
        if not self.valid_start_ns <= raw <= self.valid_stop_ns:
            raise ValueError("timestamp outside clock probe coverage")
        return self.reference_anchor_ns + round(Fraction(
            (raw - self.local_anchor_ns) * self.rate_numerator, self.rate_denominator))


def _integer(data, key):
    value = data[key]
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError("invalid integer clock field: " + key)
    return int(value)


def _anchor(samples):
    if not 4 <= len(samples) <= 256:
        raise ValueError("clock alignment requires 4..256 independent samples per batch")
    candidates = []
    for sample in samples:
        a, b, c, d = (_integer(sample, key) for key in
                       ("local_send_ns", "reference_recv_ns", "reference_send_ns", "local_recv_ns"))
        width = (d - a) - (c - b)
        if d < a or c < b or width < 0:
            raise ValueError("incompatible four-timestamp clock sample")
        candidates.append((width, (a + d) // 2, (b + c) // 2, a, d))
    width, local, reference, _, _ = min(candidates)
    return local, reference, (width + 1) // 2


def _validation_samples(manifest, node):
    """Check public identities/coverage; realtime pairs do not calibrate DB time."""
    samples, evidence = defaultdict(list), []
    files = node.get("clock_validation_files")
    if files is None:
        folder = Path(node.get("calls_dir", str(Path(node["plog_dir"]).parent / "calls")))
        files = sorted(folder.glob("rank-*.jsonl"))
    declared = {(r["user_rank"], r["device_id"]) for r in manifest.get("ranks", []) if r["node_id"] == node["node_id"]}
    for filename in files:
        path = Path(filename)
        records = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if not records:
            raise ValueError("empty public clock validation file")
        header = records[0]
        if (header.get("event") != "runtime" or header.get("schema_version") != 1
                or header.get("run_id") != manifest["run_id"] or header.get("node_id") != node["node_id"]
                or (header.get("user_rank"), header.get("device_id")) not in declared):
            raise ValueError("public clock validation identity mismatch")
        for record in records:
            for name in ("before", "after", "clocks"):
                value = record.get(name)
                if isinstance(value, dict) and "unix_ns" in value and "raw_ns" in value:
                    samples[header["device_id"]].append((_integer(value, "unix_ns"), _integer(value, "raw_ns")))
        evidence.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return samples, evidence


def profiler_conversion(start, stop, samples):
    """CANN encodes raw event time using the start offset, not realtime drift."""
    p0, p1 = _integer(start, "collectionTimeBegin") * 1000, _integer(stop, "collectionTimeEnd") * 1000
    r0, r1 = _integer(start, "clockMonotonicRaw"), _integer(stop, "clockMonotonicRaw")
    if p1 <= p0 or r1 <= r0:
        raise ValueError("profiler clock anchors are reversed")
    offset = p0 - r0
    if any(not r0 <= r <= r1 for _, r in samples):
        raise ValueError("public clock samples fall outside profiler session")
    audit = dict(model="cann_start_offset", time_domain="monotonic_raw_plus_start_offset",
        offset_ns=offset, public_sample_count=len(samples), metadata_quantization_ns=1000,
        realtime_offset_change_ns=(p1 - r1) - offset,
        max_public_realtime_offset_change_ns=max((abs(p - r - offset) for p, r in samples), default=0))
    return offset, 1000, audit


def raw_to_profiler(raw, start, stop=None):
    p0, r0 = _integer(start, "collectionTimeBegin") * 1000, _integer(start, "clockMonotonicRaw")
    if type(raw) is not int or raw < 0:
        raise ValueError("invalid raw timestamp")
    if stop is not None and not r0 <= raw <= _integer(stop, "clockMonotonicRaw"):
        raise ValueError("raw timestamp outside profiler calibration coverage")
    return raw + p0 - r0


def build(manifest, *, max_error_ns=1000000):
    if type(max_error_ns) is not int or max_error_ns <= 0:
        raise ValueError("clock error tolerance must be positive")
    nodes = manifest["nodes"]
    if not any(node.get("clock_probe_files") for node in nodes):
        return None
    if not all(node.get("clock_probe_files") for node in nodes):
        raise ValueError("clock evidence must cover every manifest node")
    probes, sources, capture_ids, references = {}, [], set(), set()
    for node in nodes:
        combined = {}
        for filename in node["clock_probe_files"]:
            path = Path(filename)
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if (data.get("schema_version") != 1 or data.get("clock") != "CLOCK_MONOTONIC_RAW"
                    or data.get("node_id") != node["node_id"]):
                raise ValueError("clock evidence identity/schema mismatch")
            capture_ids.add(data["capture_id"])
            references.add(data["reference_node"])
            for key in ("before", "after", "before_raw_ns", "after_raw_ns"):
                if key in data:
                    if key in combined:
                        raise ValueError("duplicate clock probe phase")
                    combined[key] = data[key]
            sources.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        probes[node["node_id"]] = combined
    if len(capture_ids) != 1 or len(references) != 1 or not next(iter(capture_ids)):
        raise ValueError("clock evidence mixes capture sessions/reference nodes")
    reference_node, = references
    if reference_node not in probes:
        raise ValueError("reference clock node absent")
    models, calibrations = [], []
    for node in nodes:
        validation, validation_sources = _validation_samples(manifest, node)
        sources.extend(validation_sources)
        evidence = probes[node["node_id"]]
        is_reference = node["node_id"] == reference_node
        if is_reference:
            first, last = (_integer(evidence, key) for key in ("before_raw_ns", "after_raw_ns"))
            x0, y0, rate, network_error = first, first, Fraction(1), 0
        else:
            x0, y0, e0 = _anchor(evidence["before"])
            x1, y1, e1 = _anchor(evidence["after"])
            if x1 <= x0 or y1 <= y0:
                raise ValueError("before/after clock anchors are reversed")
            if max(_integer(s, "local_recv_ns") for s in evidence["before"]) >= min(
                    _integer(s, "local_send_ns") for s in evidence["after"]):
                raise ValueError("clock probe phases overlap")
            first, last = x0, x1
            rate = Fraction(y1 - y0, x1 - x0)
            if abs(rate - 1) > Fraction(1, 1000):
                raise ValueError("clock rate differs by more than 1000ppm; unsupported clock model")
            network_error = max(e0, e1)
        if first >= last:
            raise ValueError("empty clock calibration window")
        for db_path in discover_db_files(node["msprof_db_dir"]):
            connection = _readonly_connection(str(db_path))
            try:
                devices = _device_ids(connection)
                session = connection.execute("SELECT startTimeNs,endTimeNs FROM SESSION_TIME_INFO").fetchall()
            finally:
                connection.close()
            if len(devices) != 1 or len(session) != 1:
                raise ValueError("clock conversion needs one device/session per DB")
            start_path, stop_path = db_path.parent / "host/start_info", db_path.parent / "host/end_info"
            start = json.loads(start_path.read_text())
            stop = json.loads(stop_path.read_text())
            epoch_start = _integer(start, "collectionTimeBegin") * 1000
            epoch_stop = _integer(stop, "collectionTimeEnd") * 1000
            raw_start, raw_stop = _integer(start, "clockMonotonicRaw"), _integer(stop, "clockMonotonicRaw")
            if tuple(session[0]) != (epoch_start, epoch_stop) or not first <= raw_start < raw_stop <= last:
                raise ValueError("clock probes do not bracket this actual profiler session")
            offset = epoch_start - raw_start
            offset, conversion_error, audit = profiler_conversion(start, stop, validation.get(devices[0], []))
            calibrations.append(dict(node_id=node["node_id"], device_id=devices[0], **audit))
            error = network_error + conversion_error
            if error > max_error_ns:
                raise ValueError("estimated clock alignment error exceeds configured tolerance")
            models.append(DeviceClock(manifest["run_id"] + "/" + node["node_id"], devices[0], offset,
                x0, y0, rate.numerator, rate.denominator, first, last, error))
            for path in (start_path, stop_path):
                sources.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return dict(schema_version=3, status="network_probe_estimate", capture_id=next(iter(capture_ids)),
                reference_node=manifest["run_id"] + "/" + reference_node,
                estimated_error_ns=max(model.estimated_error_ns for model in models),
                models=[asdict(model) for model in models], evidence=sources, profiler_calibrations=calibrations,
                limits=["Affine interpolation between before/after raw-clock probes; not hardware PTP synchronization.",
                        "CANN DB event time is monotonic raw plus the fixed start_info offset. Realtime end_info/SDK drift is audited, not applied to DB timestamps.",
                        "Error estimates combine network-delay bounds and start metadata quantization; unsampled network nonlinearity and device/Host synchronization error may remain. This is not a hardware-verified error bound.",
                        "Mapping supports display and estimated cross-node Host/Wait overlap checks; raw timestamps, task durations, graph edges and local critical paths are unchanged."])


def models_from_report(report):
    if report is None:
        return {}
    if report.get("schema_version") not in {1, 2, 3} or report.get("status") != "network_probe_estimate":
        raise ValueError("unsupported clock alignment artifact")
    models = []
    for source in report["models"]:
        row = dict(source)
        legacy = tuple(row.pop(name, default) for name, default in (
            ("profiler_anchor_ns", None), ("profiler_stop_ns", None),
            ("profiler_rate_numerator", 1), ("profiler_rate_denominator", 1)))
        if legacy != (None, None, 1, 1):
            raise ValueError("retired realtime-affine DB clock model; replay the retained capture")
        models.append(DeviceClock(**row))
    for model in models:
        if (model.rate_numerator <= 0 or model.rate_denominator <= 0 or model.device_id < 0
                or model.estimated_error_ns < 0 or model.valid_start_ns >= model.valid_stop_ns
                or abs(Fraction(model.rate_numerator, model.rate_denominator) - 1) > Fraction(1, 1000)):
            raise ValueError("invalid device clock model")
    result = {(model.node_id, model.device_id): model for model in models}
    if len(result) != len(models):
        raise ValueError("duplicate device clock model")
    return result
