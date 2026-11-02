"""Frozen single-node interventions; no background-ready wait in a DDP hook."""
from __future__ import annotations

from pathlib import Path

from .anomaly_injection.single_node_control import SingleControl
from .node03_gpt2_control import worker_environment


class GptThreeAnomalyControl(SingleControl):
    bounded_interference = True

    def __init__(self, config, directory, rank, devices, communication_worker=None):
        super().__init__(config, directory, rank, devices, communication_worker, "grouped")
        self.kind = self.inj['kind']
        if (self.case.get('experiment_contract', {}).get('profile') != 'gpt-three-anomalies-v1'
                or self.kind not in {'progress_delay', 'communication_contention', 'compute_contention'}
                or self.inj.get('duration_iters') != 1):
            raise ValueError('only the frozen one-iteration three-anomaly profile is supported')
        self.communication_scoped = self.kind != 'progress_delay'

    def prepare(self):
        import os
        super().prepare(environment=worker_environment(os.environ))
        if self.process is not None:
            ticks = (Path('/proc')/str(self.process.pid)/'stat').read_text().split(') ', 1)[1].split()[19]
            self.record('owned_worker_identity', pid=self.process.pid, process_start_ticks=ticks)

    def start(self, call):
        if self.kind == 'progress_delay':
            return super().start(call)
        if not self.owner:
            return
        if self.started:
            raise ValueError('one background activation per case')
        self.started = True
        self.record('injection_start', call=call, api_return_is_not_device_completion=True)
        (self.directory/'start').touch()
        self.record('start_requested_without_foreground_ack_wait')

    def after_collective(self, call):
        if (self.owner and not self.started and call['stage'] == 'measured'
                and call['iteration'] == self.inj['iteration']):
            self.record('post_submit_activation', sequence=call['sequence'], bucket=call['bucket'],
                        bucket_signature=call['bucket_signature'])
            self.start(call['sequence'])

    def after_iteration(self, iteration):
        if not self.owner or iteration != self.inj['iteration']:
            return
        if not self.started:
            raise ValueError('selected gradient bucket never activated the intervention')
        if self.kind != 'progress_delay':
            self.stop()
            self.wait('paused')
            self.record('background_paused_before_next_iteration')
