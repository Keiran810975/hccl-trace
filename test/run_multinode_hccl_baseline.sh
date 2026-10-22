#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_multinode_hccl_baseline.sh OPTIONS

Required:
  --node-rank N        Zero-based node rank.
  --master-addr IP     Host IP of node rank 0.

Optional:
  --nnodes N           Number of nodes. Default: 2
  --master-port PORT   torchrun rendezvous port. Default: 29610
  --devices LIST       Comma-separated local NPU IDs. Default: 0
  --count N            Tensor element count. Default: 16777216
  --dtype TYPE         fp32, fp16, or bf16. Default: fp32
  --warmup N           Warmup iterations. Default: 5
  --iters N            Measured iterations. Default: 20
  --python PATH        Python executable used by torchrun. Default: python3
EOF
}

NODE_RANK=""
MASTER_ADDR=""
NNODES=2
MASTER_PORT=29610
DEVICES=0
COUNT=16777216
DTYPE=fp32
WARMUP=5
ITERS=20
PYTHON_BIN=python3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node-rank) NODE_RANK="$2"; shift 2 ;;
    --master-addr) MASTER_ADDR="$2"; shift 2 ;;
    --nnodes) NNODES="$2"; shift 2 ;;
    --master-port) MASTER_PORT="$2"; shift 2 ;;
    --devices) DEVICES="$2"; shift 2 ;;
    --count) COUNT="$2"; shift 2 ;;
    --dtype) DTYPE="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;;
    --iters) ITERS="$2"; shift 2 ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$NODE_RANK" || -z "$MASTER_ADDR" ]]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IFS=',' read -r -a DEVICE_IDS <<< "$DEVICES"
NPROC_PER_NODE=${#DEVICE_IDS[@]}

if [[ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi

export ASCEND_RT_VISIBLE_DEVICES="$DEVICES"
export HCCL_CONNECT_TIMEOUT="${HCCL_CONNECT_TIMEOUT:-120}"

echo "node_rank=$NODE_RANK nnodes=$NNODES devices=$DEVICES master=$MASTER_ADDR:$MASTER_PORT"
"$PYTHON_BIN" -m torch.distributed.run \
  --nnodes="$NNODES" \
  --nproc-per-node="$NPROC_PER_NODE" \
  --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" \
  --master-port="$MASTER_PORT" \
  "$SCRIPT_DIR/multinode_hccl_allreduce.py" \
  --count "$COUNT" \
  --dtype "$DTYPE" \
  --warmup "$WARMUP" \
  --iters "$ITERS"
