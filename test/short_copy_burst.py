"""One finite D2D copy on an independent stream in an already initialized rank."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from .anomaly_injection.acl_copy_load import AclCopies, raw_ns


class ShortCopyBurst:
    def __init__(self, device, mib, output, *, delay_us=0, operations=1, factory=AclCopies):
        if type(operations) is not int or not 1 <= operations <= 8:
            raise ValueError("one finite worker supports one to eight copy operations")
        self.device, self.mib, self.output = device, mib, Path(output)
        self.operations = operations
        self.factory = factory
        self.delay_us = delay_us
        self.ready, self.trigger, self.finalize = threading.Event(), threading.Event(), threading.Event()
        self.requested = False
        self.cancelled = False
        self.error = None
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        if not self.ready.wait(30):
            self.cancelled = True
            self.trigger.set()
            raise TimeoutError("D2D worker preparation timed out")
        self.check()

    def check(self):
        if self.error is not None:
            raise RuntimeError("short D2D worker failed") from self.error

    def start(self):
        self.check()
        if self.requested:
            raise ValueError("only one D2D copy burst is allowed")
        self.requested = True
        self.trigger.set()

    def _worker(self):
        copies = None
        try:
            copies = self.factory(self.device, self.mib, initialize_runtime=False)
            self.ready.set()
            if not self.trigger.wait(300):
                raise TimeoutError("D2D trigger did not arrive")
            if self.cancelled:
                return
            if self.delay_us:
                time.sleep(self.delay_us / 1000000)
            begin = raw_ns()
            spans = []
            for _ in range(self.operations):
                start = raw_ns()
                copies.copy()
                spans.append([start, raw_ns()])
            end = raw_ns()
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text(json.dumps(dict(schema_version=1, operations=self.operations, buffer_mib=self.mib,
                runtime_device_id=self.device, started_raw_ns=begin, finished_raw_ns=end,
                copy_host_envelopes_raw_ns=spans,
                requested_delay_us=self.delay_us,
                window_kind="host_envelope_contains_async_copy_and_stream_completion",
                backend="aclrtMemcpyAsync", hardware_duration_claimed=False)) + "\n")
            self.finished.set()
            if not self.finalize.wait(300):
                raise TimeoutError("post-measurement finalization did not arrive")
            copies.validate()
            data = json.loads(self.output.read_text())
            data.update(validation_passed=True, cleanup_deferred_until_measurement_end=True)
            self.output.write_text(json.dumps(data) + "\n")
        except BaseException as error:
            self.error = error
        finally:
            self.ready.set()
            self.finished.set()
            if copies is not None:
                copies.close()

    def wait_finished(self, seconds=60):
        if not self.finished.wait(seconds):
            raise TimeoutError("finite D2D copies did not complete")
        self.check()

    def close(self):
        self.cancelled = not self.requested
        self.trigger.set()
        self.finalize.set()
        self.thread.join(timeout=120)
        if self.thread.is_alive():
            raise TimeoutError("bounded D2D worker did not exit")
        self.check()


class GptCopyBurstControl:
    """One post-submit intervention; never block a DDP hook for worker readiness."""
    communication_scoped = True
    finite_copy_burst = True

    def __init__(self, case, directory, rank, devices, *, factory=ShortCopyBurst):
        self.inj = case['injection']
        if (self.inj.get('kind') != 'copy_contention' or self.inj.get('finite_copy_burst') is not True
                or self.inj.get('buffer_mib') != 2048 or self.inj.get('operations') != 4
                or self.inj.get('duration_iters') != 1):
            raise ValueError('only the reviewed finite four-copy GPT intervention is allowed')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.rank, self.device = rank, devices[rank]
        self.owner = rank == self.inj['target_rank']
        self.factory, self.burst = factory, None
        self.started = False

    def record(self, event, **fields):
        with (self.directory / ('rank-' + str(self.rank) + '.jsonl')).open('a') as stream:
            stream.write(json.dumps(dict(event=event, rank=self.rank, **fields)) + '\n')

    def prepare(self):
        if self.owner:
            self.burst = self.factory(self.device, self.inj['buffer_mib'],
                self.directory / 'injection.json', operations=self.inj['operations'])

    def after_collective(self, call):
        if (self.owner and not self.started and call['stage'] == 'measured'
                and call['iteration'] == self.inj['iteration']):
            self.record('post_submit_activation', sequence=call['sequence'], bucket=call['bucket'],
                        bucket_signature=call['bucket_signature'], api_return_is_not_device_completion=True)
            self.burst.start()
            self.started = True

    def after_iteration(self, iteration):
        if self.owner and iteration == self.inj['iteration']:
            if not self.started:
                raise ValueError('selected gradient collective did not trigger the intervention')
            # Outside the training timer; no later iteration inherits a live worker.
            self.burst.wait_finished()

    def stop(self):
        pass

    def finish(self):
        if self.owner and not self.started:
            raise ValueError('finite intervention never ran')
        self.close()

    def close(self):
        if self.burst is not None:
            self.burst.close()
            self.burst = None
