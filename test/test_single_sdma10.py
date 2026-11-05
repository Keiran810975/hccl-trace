from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from .run_single_sdma10 import plan, positive_overlap, effect_evidence
from .node03_device_guard import scope
from .gpt_three_anomaly_control import GptThreeAnomalyControl
from .anomaly_injection.acl_copy_load import copy_window
from .remap_owned_npu_container import clone_spec, restore, ORIGINAL, ALLOCATION, ALLOCATION_NAME, BACKUP, ensure_idle_container


class SingleSdmaTenTests(unittest.TestCase):
    def test_ten_fixed_success_position_repetitions_without_computational_injection(self):
        p = plan()
        self.assertEqual(p, plan())
        self.assertEqual(p["requested"], len(p["cases"]))
        self.assertEqual(len({e["root"] for e in p["cases"]}), 10)
        for e in p["cases"]:
            c = e["case"]; i = c["injection"]
            self.assertEqual((c["workload"]["warmup"], c["workload"]["iters"]), (10,50))
            self.assertEqual((i["kind"], i["target_rank"], i["iteration"], i["bucket_selector_seed"]),
                             ("copy_contention",0,25,20261102))
            self.assertEqual(i["buffer_mib"],2048)
            self.assertNotIn("operations", i)
            self.assertEqual(i["active_timeout_seconds"],5)
        self.assertFalse(p["stop_on_diagnosis_miss"])
        self.assertTrue(p["never_replace_failed_cases"])
        self.assertEqual(p["cards"], [0,1,2,3])
        self.assertEqual(p["runtime_devices"], [1,3,5,7])

    def test_new_scope_is_node0_and_only_the_exact_eleven_directories(self):
        parent = Path("/home/commTeam/zjy/zjy-new-workspace")
        for n in [800,801,810]:
            root = parent / ("hccl-diagnose-single-20261104-"+str(n))
            self.assertEqual(scope(root,"liteserver-560t-0"),root.resolve())
            with self.assertRaises(ValueError): scope(root,"liteserver-560t-3")
        for n in [799,811,899]:
            with self.assertRaises(ValueError):scope(parent/("hccl-diagnose-single-20261104-"+str(n)),"liteserver-560t-0")

    def test_copy_profile_uses_no_ack_wait_in_the_selected_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Path(temporary)/"case.json";f.write_text(json.dumps(plan()["cases"][0]["case"]))
            control=GptThreeAnomalyControl(f,Path(temporary)/"private",0,[1,3,5,7])
            control.wait=Mock(side_effect=AssertionError("no readiness wait in a training hook"))
            control.after_collective(dict(stage="measured",iteration=25,sequence=10,bucket=3,bucket_signature="sig"))
            self.assertTrue((control.directory/"start").exists())
            control.wait.assert_not_called()
            control.wait=Mock();control.after_iteration(25)
            control.wait.assert_called_once_with("paused")

    def test_worker_repeats_until_iteration_stop_and_records_each_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            d=Path(temporary);copies=Mock()
            def copy():
                if copies.copy.call_count==7:(d/"stop").touch()
            copies.copy.side_effect=copy
            out=copy_window(copies,d,time.monotonic()+10,active_timeout=5)
            self.assertEqual(out["operations"],7)
            self.assertEqual(len(out["copy_host_envelopes_raw_ns"]),7)
            self.assertEqual(out["active_stop_reason"],"foreground_iteration_completed")
            self.assertFalse(out["hardware_duration_claimed"])
            copies.validate.assert_not_called()

    def test_active_worker_stops_on_its_own_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch("test.anomaly_injection.acl_copy_load.time.monotonic",side_effect=[0,0,0,1]):
                out=copy_window(Mock(),Path(temporary),100,active_timeout=.5)
            self.assertEqual(out["operations"],1)
            self.assertEqual(out["active_stop_reason"],"active_timeout")

    def test_copy_span_overlap_does_not_fill_the_gaps_between_copies(self):
        self.assertEqual(positive_overlap(dict(observed_start_ns=15,observed_stop_ns=20),[[0,10],[20,30]]),0)
        self.assertEqual(positive_overlap(dict(observed_start_ns=5,observed_stop_ns=25),[[0,10],[20,30]]),10)

    def test_clone_remaps_only_devices_without_privilege_or_namespace_changes(self):
        info=dict(Config=dict(Env=['EXAMPLE=unchanged'],Labels=dict(owner='zjy',project='hccl-trace')),
            HostConfig=dict(Privileged=False,Runtime='ascend',PidMode='host',DeviceCgroupRules=None,DeviceRequests=None,
                Devices=[dict(PathOnHost='/dev/davinci'+str(i),PathInContainer='/dev/davinci'+str(i),CgroupPermissions='rwm')
                         for i in range(8,16)]),Mounts=[dict(Destination='/workspace')])
        spec=clone_spec(info,'private-image')
        self.assertEqual([d['PathOnHost'] for d in spec['HostConfig']['Devices']],['/dev/davinci'+str(i) for i in range(8)])
        self.assertEqual(spec['HostConfig']['PidMode'],'host')
        self.assertFalse(spec['HostConfig']['Privileged'])
        self.assertEqual(info['HostConfig']['Devices'][0]['PathOnHost'],'/dev/davinci8')
        info['HostConfig']['Privileged']=True
        with self.assertRaises(ValueError):clone_spec(info,'private-image')

    def test_container_rollback_handles_rename_before_create(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'state.json').write_text(json.dumps(dict(phase='original_renamed',original_id=ORIGINAL,
                new_id=None,official_sha256='official')))
            before=dict(Id=ORIGINAL,Name='/backup',State=dict(Running=False))
            after=dict(Id=ORIGINAL,Name='/zjy-new',State=dict(Running=True))
            with patch('test.remap_owned_npu_container.no_active_lease'), patch('test.remap_owned_npu_container.inspect',side_effect=[before,after]), \
                    patch('test.remap_owned_npu_container.subprocess.run',return_value=Mock(returncode=1)), \
                    patch('test.remap_owned_npu_container.command',return_value='official package') as run:
                self.assertEqual(restore(root)['phase'],'original_restored')
                self.assertIn(('docker','rename',ORIGINAL,'zjy-new'),[c.args for c in run.call_args_list])

    def test_container_rollback_never_preempts_an_active_device_lease(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'state.json').write_text(json.dumps(dict(phase='ready',original_id=ORIGINAL)))
            with patch('test.remap_owned_npu_container.no_active_lease',side_effect=ValueError('active device lease')), \
                    patch('test.remap_owned_npu_container.inspect') as inspect:
                with self.assertRaises(ValueError):restore(root)
                inspect.assert_not_called()

    def test_container_idle_check_keeps_the_pid_column_required_by_docker_top(self):
        with patch('test.remap_owned_npu_container.command',return_value='PID PPID COMMAND COMMAND\n10 1 sleep sleep infinity') as run:
            ensure_idle_container('zjy-new')
            run.assert_called_once_with('docker','top','zjy-new','-eo','pid,ppid,comm,args')
        with patch('test.remap_owned_npu_container.command',return_value='PID PPID COMMAND COMMAND\n10 1 python user-workload.py'):
            with self.assertRaises(ValueError):ensure_idle_container('zjy-new')

    def test_reused_allocation_restores_both_names_without_restart_or_namespace_change(self):
        for phase in ['allocation_prepared', 'original_renamed', 'ready']:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                (root/'state.json').write_text(json.dumps(dict(mode='reuse_existing_allocation', phase=phase,
                    original_id=ORIGINAL, new_id=ALLOCATION, official_sha256='official')))
                names={ORIGINAL:'zjy-new' if phase=='allocation_prepared' else BACKUP,
                       ALLOCATION:'zjy-new' if phase=='ready' else ALLOCATION_NAME}
                def lookup(identity):
                    identity=identity if identity in names else next(k for k,v in names.items() if v==identity)
                    return dict(Id=identity, Name='/'+names[identity], State=dict(Running=True))
                def command(*args):
                    if args[:2]==('docker','rename'):
                        names[args[2]]=args[3]
                    else:
                        self.assertEqual(args[:2],('docker','exec'))
                    return 'official package'
                with patch('test.remap_owned_npu_container.no_active_lease'), \
                        patch('test.remap_owned_npu_container.ensure_idle_container'), \
                        patch('test.remap_owned_npu_container.inspect',side_effect=lookup), \
                        patch('test.remap_owned_npu_container.command',side_effect=command) as commands:
                    self.assertEqual(restore(root)['phase'],'original_restored')
                    self.assertEqual(names,{ORIGINAL:'zjy-new',ALLOCATION:ALLOCATION_NAME})
                    self.assertFalse(any(c.args[:2] in [('docker','stop'),('docker','start')]
                                         for c in commands.call_args_list))

    def test_reused_allocation_does_not_restore_alias_before_device_package(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'state.json').write_text(json.dumps(dict(mode='reuse_existing_allocation',phase='ready',
                original_id=ORIGINAL,new_id=ALLOCATION,official_sha256='official')))
            with patch('test.remap_owned_npu_container.no_active_lease'), \
                    patch('test.remap_owned_npu_container.ensure_idle_container'), \
                    patch('test.remap_owned_npu_container.inspect',return_value=dict(Name='/zjy-new')), \
                    patch('test.remap_owned_npu_container.command',return_value='custom package') as commands:
                with self.assertRaisesRegex(ValueError,'package has not been restored'):restore(root)
                self.assertFalse(any(c.args[:2]==('docker','rename') for c in commands.call_args_list))

    def effect_fixture(self, root, *, strong=2, truth_accessed=False):
        for n in ["diagnosis", "capture/private"]:(root/n).mkdir(parents=True,exist_ok=True)
        (root/"diagnosis/sealed.json").write_text(json.dumps(dict(truth_accessed=truth_accessed,files={})))
        (root/"capture/private/result.json").write_text(json.dumps(dict(backend="aclrtMemcpyAsync",max_error=0,
            buffer_mib=2048,operations=1,copy_host_envelopes_raw_ns=[[100,200]],started_raw_ns=100,finished_raw_ns=200,
            active_stop_reason="foreground_iteration_completed")))
        (root/"capture/binding-evidence.json").write_text(json.dumps(dict(ranks=[dict(rank=0,
            api_containment_verified=True,raw_to_profiler_offset_ns=1000)])))
        row=dict(node_id=plan()["cases"][0]["case"]["case_id"]+"/node0",user_rank="0",iteration="25",task_kind="sdma",
                 observed_start_ns=1110,observed_stop_ns=1150,duration_slow="True",slowdown_factor="2.5")
        with (root/"diagnosis/resource-comparisons.csv").open("w",newline="") as f:
            writer=csv.DictWriter(f,list(row));writer.writeheader()
            for _ in range(strong):writer.writerow(row)

    def test_effect_gate_is_independent_of_diagnostic_hit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.effect_fixture(root)
            out=effect_evidence(root,plan()["cases"][0]["case"],dict(any_candidate_hit=False))
            self.assertTrue(out["effect_gate_passed"])
            self.assertEqual(out["overlapping_sdma_at_least_2x_count"],2)
            self.assertFalse(out["physical_causation_proven"])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.effect_fixture(root,strong=1)
            self.assertFalse(effect_evidence(root,plan()["cases"][0]["case"],dict(any_candidate_hit=True))["effect_gate_passed"])

    def test_truth_inspection_requires_prior_sealed_diagnosis(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.effect_fixture(root,truth_accessed=True)
            with self.assertRaises(ValueError):effect_evidence(root,plan()["cases"][0]["case"],dict(any_candidate_hit=False))


if __name__ == "__main__":
    unittest.main()
