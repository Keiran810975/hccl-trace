#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/test/out/function"
PLOG=""
TASK_TIME=""
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
  --task-time FILE           msprof task_time.csv.
  --node-id ID               Node id used for task_time rows. Default: node0
  --min-match-rate PERCENT   validate_trace threshold. Default: 95
  --python BIN               Python executable. Default: $PYTHON_BIN or python3
  --no-visualize             Do not render timeline.svg and dependency.svg after merge
  -h, --help                 Show this help.

If command is provided after --, it is run once with HCCL_STEP_TRACE=1 before
merge/validate. If no command is provided, the script only validates the
provided --plog and --task-time files.
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
        --task-time)
            TASK_TIME="$2"
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

if [[ -z "${PLOG}" || -z "${TASK_TIME}" ]]; then
    echo "Both --plog and --task-time are required for merge/validate." >&2
    exit 2
fi

if [[ ! -f "${PLOG}" ]]; then
    echo "plog file not found: ${PLOG}" >&2
    exit 2
fi

if [[ ! -f "${TASK_TIME}" ]]; then
    echo "task_time.csv not found: ${TASK_TIME}" >&2
    exit 2
fi

MERGED_CSV="${OUT_DIR}/merged.csv"
SUMMARY_CSV="${OUT_DIR}/summary.csv"
MERGE_LOG="${OUT_DIR}/merge.log"
VALIDATE_LOG="${OUT_DIR}/validate.log"
TIMELINE_SVG="${OUT_DIR}/timeline.svg"
DEPENDENCY_SVG="${OUT_DIR}/dependency.svg"

echo "[step-trace] Merging semantic plog and task_time.csv"
PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.merge_timeline \
    --plog "${PLOG}" \
    --task-time "${TASK_TIME}" \
    --node-id "${NODE_ID}" \
    --output "${MERGED_CSV}" \
    --summary "${SUMMARY_CSV}" \
    2>&1 | tee "${MERGE_LOG}"

if [[ "${VISUALIZE}" == "1" ]]; then
    echo "[step-trace] Rendering timeline SVG"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_timeline \
        "${MERGED_CSV}" \
        --output "${TIMELINE_SVG}"

    echo "[step-trace] Rendering dependency SVG"
    PYTHONPATH="${ROOT_DIR}/hccl" "${PYTHON_BIN}" -m tools.diagnosis.visualize_dependency_graph \
        "${MERGED_CSV}" \
        --output "${DEPENDENCY_SVG}"
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
if [[ "${VISUALIZE}" == "1" ]]; then
    echo "  timeline:   ${TIMELINE_SVG}"
    echo "  dependency: ${DEPENDENCY_SVG}"
fi
