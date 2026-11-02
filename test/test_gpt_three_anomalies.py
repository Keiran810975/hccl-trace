from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from .gpt_three_anomaly_control import GptThreeAnomalyControl
from .run_gpt_three_anomalies import cases, bind_capture
from .stop_owned_capture import owned_processes
from .resume_gpt_compute import validate_state


class ThreeAnomalyTests(unittest.TestCase):
    def test_third_case_continuation_cannot_repeat_a_started_capture(self):
        state=dict(status='failed',phase='capturing',active='compute-contention',
            error='both chips of every authorized card must be idle',
            completed=[dict(case_id='progress-delay'),dict(case_id='communication-contention')])
        validate_state(state)
        with self.assertRaises(ValueError):
            validate_state(dict(state,phase='diagnosing'))
        with self.assertRaises(ValueError):
            validate_state(dict(state,completed=[]))

    def test_ai_cpu_uses_physical_identity_without_legacy_host_batch_export(self):
        with patch('test.run_gpt_three_anomalies.execute') as adapter:
            bind_capture(Path('/owned/attempt'), cases()[0][1])
        args=adapter.call_args.args
        self.assertEqual(args[0:2],(Path('/owned/attempt'),'bind'))
        self.assertIn('/workspace/attempt/capture',args[2])
        self.assertIn('--ddp-capture',args[2])
        self.assertNotIn('--preserve-task-batches',args[2])
        self.assertNotIn('/owned/',args[2])

    def test_frozen_three_cases_and_workload(self):
        values = cases()
        self.assertEqual([i for i,_ in values], [101,102,103])
        self.assertEqual([c['injection']['kind'] for _,c in values],
            ['progress_delay','communication_contention','compute_contention'])
        self.assertTrue(all(c['workload']['warmup']==10 and c['workload']['iters']==50
            and c['injection']['iteration']==25 and c['injection']['duration_iters']==1 for _,c in values))
        self.assertEqual(values[0][1]['injection']['delay_ms'],500)
        self.assertEqual(values[1][1]['injection']['buffer_mib'],1024)
        self.assertEqual(values[2][1]['injection']['matrix_size'],8192)

    def test_post_submit_activation_does_not_wait_for_background_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'case.json'
            path.write_text(json.dumps(cases()[1][1]))
            control=GptThreeAnomalyControl(path,Path(directory)/'private',0,[1,3,5,7])
            control.wait=Mock(side_effect=AssertionError('no wait in the foreground hook'))
            call=dict(stage='measured',iteration=25,sequence=123,bucket=9,bucket_signature='public-signature')
            control.after_collective(call)
            self.assertTrue((control.directory/'start').exists())
            self.assertTrue(control.started)
            control.wait.assert_not_called()

    def test_stop_and_pause_happen_after_selected_iteration_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'case.json'
            path.write_text(json.dumps(cases()[2][1]))
            control=GptThreeAnomalyControl(path,Path(directory)/'private',0,[1,3,5,7])
            control.started=True
            control.wait=Mock()
            control.after_iteration(24)
            self.assertFalse((control.directory/'stop').exists())
            control.after_iteration(25)
            self.assertTrue((control.directory/'stop').exists())
            control.wait.assert_called_once_with('paused')

    def test_native_orphan_cleanup_remains_exactly_scoped(self):
        base='/workspace/gpt2-three-anomalies-20261102-102'
        values={1:dict(parent=0,ticks='1',argv=[base+'/bin/single_process_comm_load']),
                2:dict(parent=0,ticks='2',argv=['/workspace/other/bin/single_process_comm_load'])}
        self.assertEqual(set(owned_processes(values,base)),{1})


if __name__=='__main__':
    unittest.main()
