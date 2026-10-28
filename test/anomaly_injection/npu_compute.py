"""Explicit test-workload GEMM backends; no precision/shape changes or silent fallback."""
from __future__ import annotations


def gemm(left, right, backend="matmul"):
    if backend not in {"matmul", "grouped"}:
        raise ValueError("unknown GEMM backend: " + backend)
    import torch
    if backend == "matmul":
        return torch.matmul(left, right)
    import torch_npu
    if (left.dim() != 2 or right.dim() != 2 or left.shape[1] != right.shape[0]
            or left.dtype != torch.bfloat16 or right.dtype != torch.bfloat16):
        raise ValueError("single-group GEMM requires compatible two-dimensional BF16 tensors")
    outputs = torch_npu.npu_grouped_matmul([left], [right], split_item=0, group_type=-1)
    if (len(outputs) != 1 or tuple(outputs[0].shape) != (left.shape[0], right.shape[1])
            or outputs[0].dtype != left.dtype):
        raise ValueError("single-group GEMM returned an unexpected shape or dtype")
    return outputs[0]
