from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test.anomaly_injection.npu_compute import gemm
from test.run_single_node_suite import validate_mixed_preflight
from test.single_node_random_suite import generate_cases


def tensor(shape, dtype="bf16"):
    return SimpleNamespace(shape=shape, dtype=dtype, dim=lambda: len(shape))


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.left, self.right = tensor((2048, 4096)), tensor((4096, 12288))
        self.output = tensor((2048, 12288))
        self.torch = SimpleNamespace(bfloat16="bf16", matmul=Mock(return_value=self.output))
        self.npu = SimpleNamespace(npu_grouped_matmul=Mock(return_value=[self.output]))
        self.modules = patch.dict("sys.modules", torch=self.torch, torch_npu=self.npu)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_default_keeps_existing_matmul(self):
        self.assertIs(gemm(self.left, self.right), self.output)
        self.torch.matmul.assert_called_once_with(self.left, self.right)
        self.npu.npu_grouped_matmul.assert_not_called()

    def test_single_group_preserves_tensors_and_shape(self):
        self.assertIs(gemm(self.left, self.right, "grouped"), self.output)
        self.npu.npu_grouped_matmul.assert_called_once_with(
            [self.left], [self.right], split_item=0, group_type=-1)
        self.torch.matmul.assert_not_called()

    def test_rejects_precision_shape_and_backend_changes(self):
        for left, right, backend in [(tensor((2, 3), "fp32"), tensor((3, 4)), "grouped"),
                                     (tensor((2, 3)), tensor((4, 5)), "grouped"),
                                     (self.left, self.right, "automatic")]:
            with self.assertRaises(ValueError):
                gemm(left, right, backend)

    def test_rejects_unexpected_output_and_never_silently_falls_back(self):
        self.npu.npu_grouped_matmul.return_value = [tensor((1, 2))]
        with self.assertRaises(ValueError):
            gemm(self.left, self.right, "grouped")
        self.npu.npu_grouped_matmul.side_effect = RuntimeError("kernel failure")
        with self.assertRaisesRegex(RuntimeError, "kernel failure"):
            gemm(self.left, self.right, "grouped")
        self.torch.matmul.assert_not_called()

    def test_full_shape_gate_rejects_communication_only_and_small_probe(self):
        workload = generate_cases()[0]["workload"]
        result = dict(execution_success=True, strict_diagnosis_success=True,
                      purpose="full_shape_mixed_preflight", gemm_backend="grouped")
        launch = dict(workload=dict(workload, warmup=1, iters=7),
                      gemm_backend="grouped", devices=[1, 3, 5, 7])
        validate_mixed_preflight(result, launch, workload)
        for change in [dict(purpose="communication_reference_preflight"), dict(gemm_backend="matmul")]:
            with self.assertRaises(ValueError):
                validate_mixed_preflight(dict(result, **change), launch, workload)
        with self.assertRaises(ValueError):
            validate_mixed_preflight(result, dict(launch, workload=dict(launch["workload"], hidden_size=256)), workload)


if __name__ == "__main__":
    unittest.main()
