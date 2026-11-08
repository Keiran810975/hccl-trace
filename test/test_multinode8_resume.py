from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from test.multinode20_suite import continuation_plan
from test.run_multinode8_resume import (ORIGIN, validate_previous, receipt_verified,
                                       validate_archived_checkpoint, consume_archived_checkpoint, sha)


class ResumeEightTests(unittest.TestCase):
    def previous(self):
        plan = continuation_plan()
        return dict(status='stopped', completed=10, cases=deepcopy(plan['cases'][:10]),
            active_case=plan['cases'][10]['case_id'],
            active_directory=str(ORIGIN.parent / 'hccl-diagnose-node03-20261106-1012'))

    def test_only_eight_unused_positions_and_no_failed_case_retry(self):
        plan = continuation_plan()
        pending = validate_previous(self.previous(), plan)
        self.assertEqual([i for i, _ in pending], list(range(1013, 1021)))
        self.assertEqual([c for _, c in pending], plan['cases'][11:])

    def test_wrong_checkpoint_or_changed_case_identity_is_rejected(self):
        for key, value in (('completed', 9), ('status', 'running'), ('active_case', 'different')):
            state = self.previous(); state[key] = value
            with self.assertRaises(ValueError):
                validate_previous(state, continuation_plan())
        state = self.previous(); state['cases'][0]['case_id'] = 'changed'
        with self.assertRaises(ValueError):
            validate_previous(state, continuation_plan())

    def test_ack_requires_both_verified_archives_and_exact_case(self):
        current = Path('/tmp/1013')
        receipt = dict(status='verified', case_directory=str(current), local_archive_sha256=['a', 'b'],
                       file_hashes_verified=True, owned_raw_removed=True)
        self.assertTrue(receipt_verified(receipt, current))
        for key, value in (('local_archive_sha256', ['a']), ('file_hashes_verified', False),
                           ('owned_raw_removed', False), ('case_directory', '/tmp/1012')):
            self.assertFalse(receipt_verified(dict(receipt, **{key: value}), current))

    def test_archive_timeout_can_continue_only_seven_never_run_cases(self):
        plan=continuation_plan();current=ORIGIN.parent/'hccl-diagnose-node03-20261106-1013'
        case=dict(case_id=plan['cases'][11]['case_id'],effect_gate_passed=True)
        state=dict(status='stopped',requested=8,completed=1,cases=[case],active_directory=str(current),
                   aggregate_completed=11,
                   error='90-minute verified archive deadline; no next capture')
        receipt=dict(status='verified',case_directory=str(current),local_archive_sha256=['a','b'],
                     file_hashes_verified=True,owned_raw_removed=True)
        self.assertEqual(validate_archived_checkpoint(state,receipt,plan),[case])
        for change in (dict(completed=2),dict(error='different failure'),dict(status='running'),
                       dict(cases=[dict(case,effect_gate_passed=False)])):
            with self.assertRaises(ValueError):validate_archived_checkpoint(dict(state,**change),receipt,plan)
        with self.assertRaises(ValueError):validate_archived_checkpoint(state,dict(receipt,owned_raw_removed=False),plan)

    def test_second_archived_checkpoint_retains_prefix_and_cannot_be_consumed_twice(self):
        plan=continuation_plan();current=ORIGIN.parent/'hccl-diagnose-node03-20261106-1014'
        cases=[dict(case_id=c['case_id'],effect_gate_passed=True) for c in plan['cases'][11:13]]
        state=dict(status='stopped',requested=8,completed=2,cases=cases,active_directory=str(current),
                   aggregate_completed=12,error='90-minute verified archive deadline; no next capture')
        receipt=dict(status='verified',case_directory=str(current),local_archive_sha256=['a','b'],
                     file_hashes_verified=True,owned_raw_removed=True)
        self.assertEqual(validate_archived_checkpoint(state,receipt,plan),cases)
        for change in (dict(completed=8),dict(aggregate_completed=11),dict(cases=list(reversed(cases))),
                       dict(cases=[cases[0],dict(cases[1],effect_gate_passed=False)])):
            with self.assertRaises(ValueError):validate_archived_checkpoint(dict(state,**change),receipt,plan)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'state.json').write_text(json.dumps(state))
            digest=sha(root/'state.json');authorizations=root/'checkpoint-authorizations';authorizations.mkdir()
            path=authorizations/(digest+'.json')
            authorization=dict(user_confirmed=True,checkpoint_sha256=digest,
                               only_unused_cases=list(range(1015,1021)),no_training_repeated=True)
            path.write_text(json.dumps(dict(authorization,user_confirmed=False)))
            with self.assertRaises(ValueError):consume_archived_checkpoint(root,state,receipt,plan)
            path.write_text(json.dumps(authorization))
            backup=root/'archive-checkpoints'/digest;backup.mkdir(parents=True)
            (backup/'state.json').write_text(json.dumps(state))
            self.assertEqual(consume_archived_checkpoint(root,state,receipt,plan),(cases,digest))
            with self.assertRaises(FileExistsError):consume_archived_checkpoint(root,state,receipt,plan)


if __name__ == '__main__':
    unittest.main()
