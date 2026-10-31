#!/usr/bin/env python3
"""Actual GPT-2 forward/backward/AdamW, with public DDP bucket observations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import threading
import time

if __package__:
    from .anomaly_injection.single_node_control import PublicCalls, SingleControl, clocks
else:
    from anomaly_injection.single_node_control import PublicCalls, SingleControl, clocks


def verify_replicated_initialization(directory, rank, fingerprint, timeout=120, *, world_size=4, store=None):
    directory = Path(directory)
    path = directory / ("initialization-rank-{}.json".format(rank))
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(rank=rank, **fingerprint)) + "\n")
    temporary.replace(path)
    if store is not None:
        prefix = "hccl-diagnose/model-initialization/"
        store.set(prefix + str(rank), json.dumps(dict(rank=rank, **fingerprint)))
        for other in range(world_size):
            if json.loads(store.get(prefix + str(other))) != dict(rank=other, **fingerprint):
                raise ValueError("initial GPT-2 parameters differ across the actual communication group")
        return
    expected = [directory / ("initialization-rank-{}.json".format(r)) for r in range(world_size)]
    deadline = time.monotonic() + timeout
    while not all(p.is_file() for p in expected):
        if time.monotonic() >= deadline:
            raise TimeoutError("complete CPU model initialization fingerprints required")
        time.sleep(.02)
    for r, item in enumerate(expected):
        value = json.loads(item.read_text())
        if value != dict(rank=r, **fingerprint):
            raise ValueError("initial GPT-2 parameter names/shapes/values differ across ranks")


def prepare_data(root, assets=None):
    import urllib.request
    from transformers import GPT2TokenizerFast
    root.mkdir(parents=True, exist_ok=False)
    url = "https://www.gutenberg.org/files/11/11-0.txt"
    text = (assets / "alice.txt").read_bytes() if assets else urllib.request.urlopen(url, timeout=60).read()
    (root / "alice.txt").write_bytes(text)
    if assets:
        tokenizer = (GPT2TokenizerFast(tokenizer_file=str(assets / "tokenizer.json")) if (assets / "tokenizer.json").is_file() else
                     GPT2TokenizerFast(vocab_file=str(assets / "vocab.json"), merges_file=str(assets / "merges.txt")))
    else:
        tokenizer = GPT2TokenizerFast.from_pretrained("openai-community/gpt2", cache_dir=str(root / "hf-cache"))
    tokenizer.save_pretrained(root / "tokenizer")
    ids = tokenizer.encode(text.decode("utf-8"), add_special_tokens=False)
    import array
    values = array.array("I", ids)
    (root / "tokens.bin").write_bytes(values.tobytes())
    (root / "dataset.json").write_text(json.dumps(dict(source="https://www.gutenberg.org/cache/epub/11/pg11.txt" if assets else url,
        text_sha256=hashlib.sha256(text).hexdigest(),
        token_count=len(ids), tokenizer="openai-community/gpt2", token_dtype="native_uint32", byteorder=__import__("sys").byteorder,
        purpose="Short reproducible full-model language-model training, not a convergence benchmark"), indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-data", type=Path)
    parser.add_argument("--data-assets", type=Path)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--devices", default="1,3,5,7")
    parser.add_argument("--communication-worker", type=Path)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--iters", type=int)
    parser.add_argument("--coordination-port", type=int)
    parser.add_argument("--sdk-observations", type=Path)
    args = parser.parse_args()
    if args.prepare_data:
        prepare_data(args.prepare_data, args.data_assets)
        return
    import ctypes
    ctypes.CDLL(None).prctl(15, b"hccl-diagnose", 0, 0, 0)
    import array
    import torch
    import torch_npu
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel as DDP
    from torch.distributed.algorithms.ddp_comm_hooks import default_hooks
    from transformers import GPT2Config, GPT2LMHeadModel

    case = json.loads(args.case.read_text())
    settings, inj = case["workload"], case["injection"]
    rank, local = int(os.environ["RANK"]), int(os.environ["LOCAL_RANK"])
    devices = list(map(int, args.devices.split(",")))
    device = devices[local]
    runtime_directory = args.output / "runtime"
    runtime_directory.mkdir(parents=True, exist_ok=True)
    (runtime_directory / ("rank-{}.json".format(rank))).write_text(json.dumps(dict(
        pid=os.getpid(), user_rank=rank, runtime_device_id=device, node_id=os.environ.get("HCCL_TRACE_NODE_ID"),
        role="foreground_training", process_start_ticks=Path("/proc/self/stat").read_text().split(") ", 1)[1].split()[19])) + "\n")
    torch_npu.npu.set_device(device)
    dist.init_process_group("hccl")
    world = dist.get_world_size()
    if world != case["topology"]["nnodes"] * case["topology"]["ranks_per_node"]:
        raise ValueError("actual communication group differs from the declared experiment")
    store = None
    if case["topology"]["nnodes"] > 1:
        if args.coordination_port is None or args.sdk_observations is None:
            raise ValueError("multi-node GPT-2 requires explicit CPU coordination and SDK observations")
        from datetime import timedelta
        store = dist.TCPStore(os.environ["MASTER_ADDR"], args.coordination_port, world, rank == 0,
                              timeout=timedelta(seconds=120))
    torch.manual_seed(case["workload_seed"])
    torch_npu.npu.manual_seed_all(case["workload_seed"])
    torch.set_num_threads(1)
    output = args.output
    if store is None:
        control = SingleControl(args.case, output / "private", rank, devices, args.communication_worker, "grouped")
    else:
        if __package__:
            from .node03_gpt2_control import MultiNodeControl
        else:
            from node03_gpt2_control import MultiNodeControl
        first = rank - local
        device_map = {first + index: device for index, device in enumerate(devices)}
        control = MultiNodeControl(args.case, output / "private", rank, device_map)
    recorder = PublicCalls(output / "public", rank, device)
    try:
        control.prepare()
        config = GPT2Config(n_layer=settings["n_layer"], n_head=settings["n_head"], n_embd=settings["n_embd"],
                            n_positions=settings["seq_length"], use_cache=False, attn_implementation="eager")
        model = GPT2LMHeadModel(config)
        digest = hashlib.sha256()
        for name, parameter in model.named_parameters():
            digest.update(json.dumps((name, list(parameter.shape), str(parameter.dtype))).encode())
            digest.update(parameter.detach().numpy().tobytes())
        fingerprint = dict(parameter_sha256=digest.hexdigest(),
                           parameter_count=sum(p.numel() for p in model.parameters()))
        verify_replicated_initialization(output / "public", rank, fingerprint, world_size=world, store=store)
        model = model.to("npu:{}".format(device))
        names = {id(p): name for name, p in model.named_parameters()}
        model = DDP(model, device_ids=[device], broadcast_buffers=False, bucket_cap_mb=settings["bucket_cap_mb"],
                    gradient_as_bucket_view=True, find_unused_parameters=False, init_sync=False)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=False)
        values = array.array("I")
        values.frombytes((args.data / "tokens.bin").read_bytes())
        data = torch.tensor(values, dtype=torch.long)
        rng = random.Random(case["workload_seed"] + rank)
        warmup, iters = args.warmup if args.warmup is not None else settings["warmup"], args.iters if args.iters is not None else settings["iters"]
        state = dict(step=None, prepare=None, buckets={}, warmup_buckets={}, target_bucket=None)

        hook_lock = threading.Lock()

        def submit_bucket(unused_state, bucket):
            step = state["step"]
            if step is None:
                raise ValueError("gradient communication outside a recorded iteration")
            signature = hashlib.sha256(json.dumps([names[id(p)] for p in bucket.parameters()]).encode()).hexdigest()
            index, count = bucket.index(), bucket.buffer().numel()
            if bucket.buffer().dtype != torch.float32:
                raise ValueError("this experiment requires actual FP32 gradient buckets")
            state["buckets"][index] = (signature, count)
            if (control.owner and step == inj.get("iteration") and index == state["target_bucket"]):
                control.record("selected_bucket", iteration=step, bucket=index, signature=signature, count=count)
                control.start(index)
            recorder.preparation = dict(location=(step, 0, index, count), clocks=state["prepare"])
            recorder.begin(step, 0, index, count)
            recorder.current["bucket_signature"] = signature
            recorder.current["input_buffer_ptr"] = bucket.buffer().data_ptr()
            future = default_hooks.allreduce_hook(dist.group.WORLD, bucket)
            recorder.end()
            state["prepare"] = clocks()
            return future

        def communicate(unused_state, bucket):
            # A public hook interval must not interleave another hook's mutable recorder state.
            with hook_lock:
                return submit_bucket(unused_state, bucket)

        model.register_comm_hook(None, communicate)
        times, losses = [], []
        first_parameter = next(model.parameters())
        initial = first_parameter.detach().flatten()[:32].float().cpu().tolist()
        for number in range(warmup + iters):
            step = number - warmup
            # Negative warmup IDs follow PublicCalls' explicit warmup convention.
            stage_step = -(number + 1) if step < 0 else step
            if step == 0:
                stable = state["warmup_buckets"]
                if not stable:
                    raise ValueError("no DDP buckets after warmup")
                state["stable"] = stable
                if inj["kind"] != "normal":
                    state["target_bucket"] = random.Random(inj["bucket_selector_seed"]).choice(sorted(stable))
            if control.owner and inj["kind"] not in {"normal", "progress_delay"} and step == inj["iteration"] + inj["duration_iters"]:
                control.stop()
            offsets = [rng.randrange(len(data) - settings["seq_length"]) for _ in range(settings["batch_per_rank"])]
            batch = torch.stack([data[i:i + settings["seq_length"]] for i in offsets]).to("npu:{}".format(device))
            optimizer.zero_grad(set_to_none=True)
            state.update(step=stage_step, prepare=clocks(), buckets={})
            started = time.perf_counter_ns()
            with torch.autocast(device_type="npu", dtype=torch.bfloat16):
                loss = model(input_ids=batch, labels=batch, use_cache=False).loss
            loss.backward()
            optimizer.step()
            torch_npu.npu.synchronize()
            recorder.iteration_done(stage_step)
            elapsed = time.perf_counter_ns() - started
            loss_value = float(loss.detach().float().cpu())
            if not __import__("math").isfinite(loss_value):
                raise ValueError("GPT-2 loss is not finite")
            if step < 0:
                state["warmup_buckets"] = dict(state["buckets"])
            else:
                if state["buckets"] != state["stable"]:
                    raise ValueError("formal DDP parameter buckets changed; no guessed cross-iteration binding")
                times.append(elapsed)
                losses.append(loss_value)
            print(json.dumps(dict(rank=rank, stage="warmup" if step < 0 else "measured", iteration=step,
                                  duration_ms=elapsed / 1e6, loss=loss_value, buckets=len(state["buckets"]))), flush=True)
        state["step"] = None
        control.finish()
        sampled = [p.detach().flatten()[:4].float().cpu().tolist() for p in model.parameters()]
        final = first_parameter.detach().flatten()[:32].float().cpu().tolist()
        if final == initial:
            raise ValueError("training did not update sampled model parameters")
        result = dict(rank=rank, pid=os.getpid(), world_size=world, runtime_device_id=device, status="passed", warmup=warmup, iters=iters,
                      losses=losses, iteration_ns=times, parameter_samples=sampled, parameter_update_observed=True,
                      parameters=sum(p.numel() for p in model.parameters()), bucket_structure=state["stable"],
                      selected_bucket=state["target_bucket"], full_model_training=True,
                      initialization=fingerprint, ddp_init_sync=False,
                      data_source=json.loads((args.data / "dataset.json").read_text()),
                      torch=torch.__version__, torch_npu=torch_npu.__version__)
        paths = {line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                 if any(name in line for name in ("libhcomm.so", "libhccl.so")) and line.split()[-1].startswith("/")}
        result["loaded_communication_libraries"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                                    for p in map(Path, sorted(paths)) if p.is_file()}
        operators = {line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                     if "libopapi" in line and line.split()[-1].startswith("/")}
        result["loaded_operator_libraries"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                               for p in map(Path, sorted(operators)) if p.is_file()}
        result["ascend_opp_path"] = os.environ.get("ASCEND_OPP_PATH")
        (output / "workload_results" / ("rank-{}.json".format(rank))).write_text(json.dumps(result, indent=2) + "\n")
        if args.sdk_observations is not None:
            if __package__:
                from .node03_gpt2_suite import adapt_ddp_public
            else:
                from node03_gpt2_suite import adapt_ddp_public
            adapt_ddp_public(output / "public", args.sdk_observations, run_id=case["case_id"],
                node_id=os.environ["HCCL_TRACE_NODE_ID"], rank=rank, device=device, pid=os.getpid(), participants=list(range(world)))
    finally:
        control.close()
        recorder.close()
        if dist.is_initialized():
            dist.destroy_process_group()


if __name__ == "__main__":
    main()
