#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/test/out/function"
PLOG=""
PLOG_DIR=""
MSPROF_DB=""
MSPROF_DB_DIR=""
NODE_ID="node0"
MIN_MATCH_RATE="95"
VISUALIZE="1"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
    cat <<'USAGE'
Usage:
  bash test/run_step_trace_function_test.sh [options] [-- command...]

Options:
  --out-dir DIR              Output directory. Default: test/out/function
  --plog FILE                HCCL plog containing [HcclTaskSemantic] rows.
  --plog-dir DIR            Directory containing plog*.log files.
  --msprof-db FILE           Consolidated msprof_*.db.
  --msprof-db-dir DIR        Directory containing PROF_*/msprof_*.db files.
  --node-id ID               Node id assigned to this capture. Default: node0
  --min-match-rate PERCENT   validate_trace threshold. Default: 95
  --python BIN               Python executable. Default: $PYTHON_BIN or python3
  --no-visualize             Do not render timeline/dependency reports after merge
  -h, --help                 Show this help.

If command is provided after --, it is run once with HCCL_STEP_TRACE=1 before
merge/validate. If no command is provided, the script only validates the
provided plog and msprof DB files.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out-dir)
            OUT_DIR="$2"
            shift 2
            ;;
        --plog)
            PLOG="$2"
            shift 2
            ;;
        --plog-dir)
            PLOG_DIR="$2"
            shift 2
            ;;
        --msprof-db)
            MSPROF_DB="$2"
            shift 2
            ;;
        --msprof-db-dir)
            MSPROF_DB_DIR="$2"
            shift 2
            ;;
        --node-id)
            NODE_ID="$2"
            shift 2
            ;;
        --min-match-rate)
            MIN_MATCH_RATE="$2"
            shift 2
            ;;
        --python)
            PYTHON_BIN="$2"
            shift 2
            ;;
        --no-visualize)
            VISUALIZE="0"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

mkdir -p "${OUT_DIR}"

if [[ $# -gt 0 ]]; then
    echo "[step-trace] Running workload with HCCL_STEP_TRACE=1"
    (
        export HCCL_STEP_TRACE=1
        export HCCL_TASK_SEMANTIC_TRACE=1
        "$@"
    ) 2>&1 | tee "${OUT_DIR}/workload.log"
fi

if [[ ( -z "${PLOG}" && -z "${PLOG_DIR}" ) || \
      ( -z "${MSPROF_DB}" && -z "${MSPROF_DB_DIR}" ) ]]; then
    echo "plog input and msprof DB input are required for merge/validate." >&2
    exit 2
fi

if [[ -n "${PLOG}" && ! -f "${PLOG}" ]]; then
    echo "plog file not found: ${PLOG}" >&2
    exit 2
fi

if [[ -n "${PLOG_DIR}" && ! -d "${PLOG_DIR}" ]]; then
    echo "plog dir not found: ${PLOG_DIR}" >&2
    exit 2
fi

if [[ -n "${MSPROF_DB}" && ! -f "${MSPROF_DB}" ]]; then
    echo "msprof DB not found: ${MSPROF_DB}" >&2
    exit 2
fi
if [[ -n "${MSPROF_DB_DIR}" && ! -d "${MSPROF_DB_DIR}" ]]; then
    echo "msprof DB dir not found: ${MSPROF_DB_DIR}" >&2
    exit 2
fi

MERGED_CSV="${OUT_DIR}/merged.csv"
SUMMARY_CSV="${OUT_DIR}/summary.csv"
MERGE_LOG="${OUT_DIR}/merge.log"
VALIDATE_LOG="${OUT_DIR}/validate.log"
TIMELINE_SVG="${OUT_DIR}/timeline.svg"
DEPENDENCY_HTML="${OUT_DIR}/dependency.html"
DEPENDENCY_EXECUTION_HTML="${OUT_DIR}/dependency_execution.html"
DEPENDENCY_EXECUTION_SVG="${OUT_DIR}/dependency_execution.svg"
DEPENDENCY_RESOURCE_SVG="${OUT_DIR}/dependency_resource.svg"
DEPENDENCY_PREFIX="${OUT_DIR}/dep_graph"
DEPENDENCY_GATE_LOG="${OUT_DIR}/dependency_validate.log"
DEPENDENCY_GATE_SUMMARY="${OUT_DIR}/dep_graph_gate_summary.csv"
TIMELINE_HTML="${OUT_DIR}/timeline_time.html"

echo "[step-trace] Merging semantic plog and msprof profiler events"
MERGE_ARGS=(
    --node-id "${NODE_ID}"
    --output "${MERGED_CSV}"
    --summary "${SUMMARY_CSV}"
)
if [[ -n "${PLOG}" ]]; then
    MERGE_ARGS+=(--plog "${PLOG}")
fi
if [[ -n "${PLOG_DIR}" ]]; then
    MERGE_ARGS+=(--plog-dir "${PLOG_DIR}")
fi
if [[ -n "${MSPROF_DB}" ]]; then
    MERGE_ARGS+=(--msprof-db "${MSPROF_DB}")
fi
if [[ -n "${MSPROF_DB_DIR}" ]]; then
    MERGE_ARGS+=(--msprof-db-dir "${MSPROF_DB_DIR}")
fi
PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.merge_timeline \
    "${MERGE_ARGS[@]}" \
    2>&1 | tee "${MERGE_LOG}"

echo "[step-trace] Exporting execution and resource dependency artifacts"
PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_dependency_graph \
    "${MERGED_CSV}" \
    --output-prefix "${DEPENDENCY_PREFIX}"

echo "[step-trace] Validating dependency artifacts"
PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.validate_dependency_graph \
    "${DEPENDENCY_PREFIX}" \
    --summary-output "${DEPENDENCY_GATE_SUMMARY}" \
    2>&1 | tee "${DEPENDENCY_GATE_LOG}"

if [[ "${VISUALIZE}" == "1" ]]; then
    echo "[step-trace] Rendering timeline SVG"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_timeline \
        "${MERGED_CSV}" \
        --output "${TIMELINE_SVG}"

    echo "[step-trace] Rendering execution dependency HTML/SVG from artifacts"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_html \
        "${DEPENDENCY_PREFIX}_nodes.csv" \
        --edges-csv "${DEPENDENCY_PREFIX}_edges.csv" \
        --view execution \
        --output "${DEPENDENCY_EXECUTION_HTML}" \
        --svg-output "${DEPENDENCY_EXECUTION_SVG}"

    echo "[step-trace] Rendering resource dependency HTML/SVG from artifacts"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_html \
        "${DEPENDENCY_PREFIX}_resource_nodes.csv" \
        --edges-csv "${DEPENDENCY_PREFIX}_resource_edges.csv" \
        --view resource \
        --output "${DEPENDENCY_HTML}" \
        --svg-output "${DEPENDENCY_RESOURCE_SVG}"

    echo "[step-trace] Rendering fine-grained interactive time view"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_html \
        "${MERGED_CSV}" --view timeline --layout time --output "${TIMELINE_HTML}"
fi

echo "[step-trace] Validating merged trace"
PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.validate_trace \
    "${MERGED_CSV}" \
    --min-match-rate "${MIN_MATCH_RATE}" \
    2>&1 | tee "${VALIDATE_LOG}"

echo "[step-trace] PASS"
echo "  merged:   ${MERGED_CSV}"
echo "  summary:  ${SUMMARY_CSV}"
echo "  validate: ${VALIDATE_LOG}"
echo "  dependency gate: ${DEPENDENCY_GATE_LOG}"
echo "  dependency summary: ${DEPENDENCY_GATE_SUMMARY}"
if [[ "${VISUALIZE}" == "1" ]]; then
    echo "  timeline:   ${TIMELINE_SVG}"
    echo "  execution dependency: ${DEPENDENCY_EXECUTION_HTML}"
    echo "  resource dependency:  ${DEPENDENCY_HTML}"
    echo "  time HTML:  ${TIMELINE_HTML}"
fi
