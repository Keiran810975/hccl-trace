#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: run_multinode_hccl_case.sh OPTIONS

Required:
  --node-rank N          Zero-based node rank.
  --master-addr IP       Rendezvous address of node rank 0.
  --case-dir DIR         Per-node output directory.

Optional:
  --workload NAME       allreduce or commmix. Default: allreduce
  --nnodes N             Number of nodes. Default: 2
  --master-port PORT     Rendezvous port. Default: 29610
  --devices LIST         Comma-separated local NPU IDs. Default: 0
  --count N              Tensor element count. Default: 1048576
  --dtype TYPE           fp32, fp16, or bf16. Default: fp32
  --warmup N             Warmup iterations. Default: 2
  --iters N              Measured iterations. Default: 5
  --bucket-mib LIST      CommMix fp32 bucket sizes. Default: 1,8,32
  --compute-size N       CommMix square BF16 GEMM size. Default: 1024
  --blocks N             Transformer CommMix block count. Default: 1
  --tokens N             Transformer CommMix tokens per rank. Default: 0 (legacy mode)
  --hidden-size N        Transformer CommMix hidden size. Default: 0 (legacy mode)
  --ffn-size N           Transformer CommMix FFN size. Default: 0 (2 x hidden size)
  --seed N               CommMix random seed. Default: 20260924
  --arrival-delay-rank N Global rank delayed before one AllReduce.
  --arrival-delay-iter N Zero-based measured iteration. Default: 0
  --arrival-delay-block N Zero-based Transformer block. Default: -1
  --arrival-delay-bucket N Zero-based bucket inside a block. Default: -1
  --arrival-delay-ms N   Delay duration in milliseconds. Default: 0
  --python PATH          Python executable. Default: python3
  --runtime-lib-dir DIR  Prepend a rebuilt HCOMM/HCCL lib directory.
  --hccl-if-ip IP        Host IP advertised by HCCL.
  --hccl-socket-ifname N Host interface selected by HCCL.
  --trace                Enable HCCL semantic trace.
  --profile              Run the workload under msprof DB collection.
  --op-expansion-mode M  Explicit DEFAULT, HOST or AI_CPU execution mode. Default: DEFAULT
  --no-barrier           Keep profiler data limited to AllReduce tasks.
  --inject-delay-us N    Delay a matching HCCL task submission.
  --inject-rank N        Global user rank selected for injection.
  --inject-phase NAME    Exact semantic phase selected for injection.
  --inject-step N        Exact semantic step selected for injection.
  --inject-event NAME    Exact semantic event selected for injection.
  --inject-skip N        Ignore the first N matching tasks. Default: 0
  --inject-max-hits N    Maximum delayed tasks. Default: 1
EOF
}

NODE_RANK=""
MASTER_ADDR=""
CASE_DIR=""
WORKLOAD_KIND=allreduce
NNODES=2
MASTER_PORT=29610
DEVICES=0
COUNT=1048576
DTYPE=fp32
WARMUP=2
ITERS=5
BUCKET_MIB=1,8,32
COMPUTE_SIZE=1024
BLOCKS=1
TOKENS=0
HIDDEN_SIZE=0
FFN_SIZE=0
SEED=20260924
ARRIVAL_DELAY_RANK=-1
ARRIVAL_DELAY_ITER=0
ARRIVAL_DELAY_BLOCK=-1
ARRIVAL_DELAY_BUCKET=-1
ARRIVAL_DELAY_MS=0
PYTHON_BIN=python3
RUNTIME_LIB_DIR=""
HCCL_IF_IP_ARG=""
HCCL_SOCKET_IFNAME_ARG=""
TRACE=0
PROFILE=0
OP_EXPANSION_MODE=DEFAULT
NO_BARRIER=0
INJECT_DELAY_US=""
INJECT_RANK=""
INJECT_PHASE=""
INJECT_STEP=""
INJECT_EVENT=""
INJECT_SKIP=0
INJECT_MAX_HITS=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --node-rank) NODE_RANK="$2"; shift 2 ;;
        --master-addr) MASTER_ADDR="$2"; shift 2 ;;
        --case-dir) CASE_DIR="$2"; shift 2 ;;
        --workload) WORKLOAD_KIND="$2"; shift 2 ;;
        --nnodes) NNODES="$2"; shift 2 ;;
        --master-port) MASTER_PORT="$2"; shift 2 ;;
        --devices) DEVICES="$2"; shift 2 ;;
        --count) COUNT="$2"; shift 2 ;;
        --dtype) DTYPE="$2"; shift 2 ;;
        --warmup) WARMUP="$2"; shift 2 ;;
        --iters) ITERS="$2"; shift 2 ;;
        --bucket-mib) BUCKET_MIB="$2"; shift 2 ;;
        --compute-size) COMPUTE_SIZE="$2"; shift 2 ;;
        --blocks) BLOCKS="$2"; shift 2 ;;
        --tokens) TOKENS="$2"; shift 2 ;;
        --hidden-size) HIDDEN_SIZE="$2"; shift 2 ;;
        --ffn-size) FFN_SIZE="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        --arrival-delay-rank) ARRIVAL_DELAY_RANK="$2"; shift 2 ;;
        --arrival-delay-iter) ARRIVAL_DELAY_ITER="$2"; shift 2 ;;
        --arrival-delay-block) ARRIVAL_DELAY_BLOCK="$2"; shift 2 ;;
        --arrival-delay-bucket) ARRIVAL_DELAY_BUCKET="$2"; shift 2 ;;
        --arrival-delay-ms) ARRIVAL_DELAY_MS="$2"; shift 2 ;;
        --python) PYTHON_BIN="$2"; shift 2 ;;
        --runtime-lib-dir) RUNTIME_LIB_DIR="$2"; shift 2 ;;
        --hccl-if-ip) HCCL_IF_IP_ARG="$2"; shift 2 ;;
        --hccl-socket-ifname) HCCL_SOCKET_IFNAME_ARG="$2"; shift 2 ;;
        --trace) TRACE=1; shift ;;
        --profile) PROFILE=1; shift ;;
        --op-expansion-mode) OP_EXPANSION_MODE="$2"; shift 2 ;;
        --no-barrier) NO_BARRIER=1; shift ;;
        --inject-delay-us) INJECT_DELAY_US="$2"; shift 2 ;;
        --inject-rank) INJECT_RANK="$2"; shift 2 ;;
        --inject-phase) INJECT_PHASE="$2"; shift 2 ;;
        --inject-step) INJECT_STEP="$2"; shift 2 ;;
        --inject-event) INJECT_EVENT="$2"; shift 2 ;;
        --inject-skip) INJECT_SKIP="$2"; shift 2 ;;
        --inject-max-hits) INJECT_MAX_HITS="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -z "$NODE_RANK" || -z "$MASTER_ADDR" || -z "$CASE_DIR" ]]; then
    usage >&2
    exit 2
fi

if [[ "$WORKLOAD_KIND" != "allreduce" && "$WORKLOAD_KIND" != "commmix" ]]; then
    echo "--workload must be allreduce or commmix" >&2
    exit 2
fi

if [[ -n "$INJECT_DELAY_US" ]]; then
    if [[ -z "$INJECT_RANK" || -z "$INJECT_PHASE" || -z "$INJECT_STEP" || -z "$INJECT_EVENT" ]]; then
        echo "All injection selectors are required when --inject-delay-us is set." >&2
        exit 2
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "$OP_EXPANSION_MODE" in
    DEFAULT) ;;
    HOST|AI_CPU) export HCCL_OP_EXPANSION_MODE="$OP_EXPANSION_MODE" ;;
    *) echo "--op-expansion-mode must be DEFAULT, HOST or AI_CPU" >&2; exit 2 ;;
esac
mkdir -p "$CASE_DIR/ascend_log" "$CASE_DIR/msprof"

if [[ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]]; then
    # shellcheck disable=SC1091
    source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi
if [[ -n "$RUNTIME_LIB_DIR" ]]; then
    export LD_LIBRARY_PATH="$RUNTIME_LIB_DIR:${LD_LIBRARY_PATH:-}"
fi

IFS=',' read -r -a DEVICE_IDS <<< "$DEVICES"
NPROC_PER_NODE=${#DEVICE_IDS[@]}
export HCCL_WORKLOAD_RESULT_DIR="$CASE_DIR/workload_results"
mkdir "$HCCL_WORKLOAD_RESULT_DIR"
# Keep runtime IDs identical to profiler DB IDs; select devices in the worker.
unset ASCEND_RT_VISIBLE_DEVICES
export HCCL_WORKLOAD_DEVICES="$DEVICES"
export HCCL_CONNECT_TIMEOUT="${HCCL_CONNECT_TIMEOUT:-180}"
if [[ -n "$HCCL_IF_IP_ARG" ]]; then
    export HCCL_IF_IP="$HCCL_IF_IP_ARG"
fi
if [[ -n "$HCCL_SOCKET_IFNAME_ARG" ]]; then
    export HCCL_SOCKET_IFNAME="$HCCL_SOCKET_IFNAME_ARG"
fi
export HCCL_STEP_TRACE="$TRACE"
export HCCL_TASK_SEMANTIC_TRACE="$TRACE"
export ASCEND_PROCESS_LOG_PATH="$CASE_DIR/ascend_log"

unset HCCL_DIAG_INJECT_DELAY_US HCCL_DIAG_INJECT_RANK HCCL_DIAG_INJECT_PHASE
unset HCCL_DIAG_INJECT_STEP HCCL_DIAG_INJECT_EVENT HCCL_DIAG_INJECT_SKIP_MATCHES
unset HCCL_DIAG_INJECT_MAX_HITS
if [[ -n "$INJECT_DELAY_US" ]]; then
    export HCCL_DIAG_INJECT_DELAY_US="$INJECT_DELAY_US"
    export HCCL_DIAG_INJECT_RANK="$INJECT_RANK"
    export HCCL_DIAG_INJECT_PHASE="$INJECT_PHASE"
    export HCCL_DIAG_INJECT_STEP="$INJECT_STEP"
    export HCCL_DIAG_INJECT_EVENT="$INJECT_EVENT"
    export HCCL_DIAG_INJECT_SKIP_MATCHES="$INJECT_SKIP"
    export HCCL_DIAG_INJECT_MAX_HITS="$INJECT_MAX_HITS"
fi

WORKLOAD_SCRIPT="$SCRIPT_DIR/multinode_hccl_allreduce.py"
WORKLOAD_ARGS=(
    --warmup "$WARMUP"
    --iters "$ITERS"
    --delay-rank "$ARRIVAL_DELAY_RANK"
    --delay-iteration "$ARRIVAL_DELAY_ITER"
    --delay-ms "$ARRIVAL_DELAY_MS"
)
if [[ "$WORKLOAD_KIND" == "commmix" ]]; then
    WORKLOAD_SCRIPT="$SCRIPT_DIR/multinode_commmix_train.py"
    WORKLOAD_ARGS+=(
        --bucket-mib "$BUCKET_MIB"
        --compute-size "$COMPUTE_SIZE"
        --blocks "$BLOCKS"
        --tokens "$TOKENS"
        --hidden-size "$HIDDEN_SIZE"
        --ffn-size "$FFN_SIZE"
        --delay-block "$ARRIVAL_DELAY_BLOCK"
        --delay-bucket "$ARRIVAL_DELAY_BUCKET"
        --seed "$SEED"
    )
else
    WORKLOAD_ARGS+=(--count "$COUNT" --dtype "$DTYPE")
fi

WORKLOAD=(
    "$PYTHON_BIN" -m torch.distributed.run
    --nnodes="$NNODES"
    --nproc-per-node="$NPROC_PER_NODE"
    --node-rank="$NODE_RANK"
    --master-addr="$MASTER_ADDR"
    --master-port="$MASTER_PORT"
    "$WORKLOAD_SCRIPT"
    "${WORKLOAD_ARGS[@]}"
)
if [[ "$NO_BARRIER" == "1" ]]; then
    WORKLOAD+=(--no-barrier)
fi

{
    printf 'workload=%s node_rank=%s nnodes=%s devices=%s master=%s:%s trace=%s profile=%s expansion=%s\n' \
        "$WORKLOAD_KIND" "$NODE_RANK" "$NNODES" "$DEVICES" "$MASTER_ADDR" "$MASTER_PORT" "$TRACE" "$PROFILE" "${HCCL_OP_EXPANSION_MODE:-DEFAULT}"
    printf 'command:'
    printf ' %q' "${WORKLOAD[@]}"
    printf '\n'
} | tee "$CASE_DIR/command.log"

if [[ "$PROFILE" == "1" ]]; then
    for argument in "${WORKLOAD[@]}"; do
        if [[ "$argument" =~ [[:space:]] ]]; then
            echo "msprof application arguments must not contain whitespace: $argument" >&2
            exit 2
        fi
    done
    # msprof tokenizes --application itself; shell-style backslash escapes such as
    # 1\,8\,32 are forwarded literally to the Python program.
    APPLICATION="$(printf '%s ' "${WORKLOAD[@]}")"
    msprof \
        --application="$APPLICATION" \
        --output="$CASE_DIR/msprof" \
        --hccl=on \
        --task-time=on \
        --type=db \
        2>&1 | tee "$CASE_DIR/capture.log"
else
    "${WORKLOAD[@]}" 2>&1 | tee "$CASE_DIR/workload.log"
fi

# msprof can return zero even when its application failed.
"$PYTHON_BIN" "$SCRIPT_DIR/validate_workload_results.py" "$HCCL_WORKLOAD_RESULT_DIR" \
    --node-rank "$NODE_RANK" --nnodes "$NNODES" --nproc-per-node "$NPROC_PER_NODE"
