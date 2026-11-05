from __future__ import annotations

import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test.run_node03_authorized import root_command
from test.recover_multinode20_capture import verify_numeric, verify_peer_files


class RecoveryTests(unittest.TestCase):
    def test_only_authorized_root_on_node0_avoids_self_ssh(self):
        command = ['python3', '/owned/query.py', 'query']
        with patch('test.run_node03_authorized.os.geteuid', return_value=0), patch('test.run_node03_authorized.socket.gethostname', return_value='liteserver-560t-0.novalocal'):
            self.assertEqual(root_command(0, command), command)
            remote = root_command(3, command)
            self.assertEqual(remote[0], 'ssh')
            self.assertIn('StrictHostKeyChecking=yes', remote)
        with patch('test.run_node03_authorized.os.geteuid', return_value=1000):
            self.assertEqual(root_command(0, command)[0], 'ssh')
        with self.assertRaises(ValueError):root_command(2, command)

    def test_numeric_recovery_rejects_incomplete_or_mismatched_original_ranks(self):
        results = [dict(rank=r,status='passed',world_size=8,warmup=10,iters=50,
                        parameter_update_observed=True,losses=[1]*50,
                        initialization=dict(hash='a'),parameter_samples=[2]) for r in range(8)]
        verify_numeric(results)
        with self.assertRaises(ValueError):verify_numeric(results[:-1])
        results[-1]['parameter_samples']=[3]
        with self.assertRaises(ValueError):verify_numeric(results)

    def test_large_peer_manifest_uses_stdin_not_an_oversized_command_argument(self):
        files={'capture/nodes/node3/file-%d'%i:'a'*64 for i in range(10000)}
        with patch('test.recover_multinode20_capture.subprocess.run',return_value=SimpleNamespace(stdout='verified\n')) as run:
            verify_peer_files(Path('/owned/hccl-diagnose-node03-20261105-901'),files)
        args,kwargs=run.call_args
        self.assertLess(len(' '.join(args[0])),4096)
        self.assertGreater(len(kwargs['input']),128*1024)
        self.assertEqual(json.loads(kwargs['input']),files)


if __name__ == '__main__':unittest.main()
