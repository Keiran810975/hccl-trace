#!/usr/bin/env python3
"""D2D interference via ACL runtime copies, not a TensorMove AI Core kernel."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import time


def raw_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


class AclCopies:
    def __init__(self, device, mib, library=None):
        self.acl = library if library is not None else ctypes.CDLL("libascendcl.so")
        ptr, size, integer = ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int
        signatures = {
            "aclInit": [ctypes.c_char_p], "aclFinalize": [], "aclrtSetDevice": [integer],
            "aclrtMalloc": [ctypes.POINTER(ptr), size, integer], "aclrtFree": [ptr],
            "aclrtMemset": [ptr, size, integer, size], "aclrtCreateStream": [ctypes.POINTER(ptr)],
            "aclrtDestroyStream": [ptr], "aclrtSynchronizeStream": [ptr],
            "aclrtMemcpyAsync": [ptr, size, ptr, size, integer, ptr],
            "aclrtMemcpy": [ptr, size, ptr, size, integer],
        }
        for name, args in signatures.items():
            function = getattr(self.acl, name)
            function.argtypes, function.restype = args, integer
        self.source, self.destination, self.stream = ptr(), ptr(), ptr()
        self.bytes = mib * 1024 * 1024
        self.initialized = False
        try:
            self.call("aclInit", None)
            self.initialized = True
            self.call("aclrtSetDevice", device)
            self.call("aclrtMalloc", ctypes.byref(self.source), self.bytes, 0)
            self.call("aclrtMalloc", ctypes.byref(self.destination), self.bytes, 0)
            self.call("aclrtCreateStream", ctypes.byref(self.stream))
            self.call("aclrtMemset", self.source, self.bytes, 0x3C, self.bytes)
            self.call("aclrtMemset", self.destination, self.bytes, 0, self.bytes)
            self.copy()
        except BaseException:
            self.close()
            raise

    def call(self, name, *args):
        result = getattr(self.acl, name)(*args)
        if result:
            raise RuntimeError("{} failed: {}".format(name, result))

    def copy(self):
        self.call("aclrtMemcpyAsync", self.destination, self.bytes, self.source, self.bytes, 3, self.stream)
        self.call("aclrtSynchronizeStream", self.stream)

    def validate(self):
        host = ctypes.create_string_buffer(self.bytes)
        self.call("aclrtMemcpy", host, self.bytes, self.destination, self.bytes, 2)
        if host.raw != b"\x3c" * self.bytes:
            raise RuntimeError("ACL background D2D full-buffer validation failed")

    def close(self):
        if self.stream:
            self.acl.aclrtDestroyStream(self.stream)
            self.stream = ctypes.c_void_p()
        for name in ("destination", "source"):
            value = getattr(self, name)
            if value:
                self.acl.aclrtFree(value)
                setattr(self, name, ctypes.c_void_p())
        if self.initialized:
            self.acl.aclFinalize()
            self.initialized = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("copy",), default="copy")
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--buffer-mib", type=int, default=512)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--defer-finalize", action="store_true")
    parser.add_argument("--probe-operations", type=int, default=0)
    args = parser.parse_args()
    if args.device < 0 or not 1 <= args.buffer_mib <= 2048 or args.timeout <= 0 or args.probe_operations < 0:
        parser.error("invalid bounded copy configuration")
    if args.probe_operations and args.defer_finalize:
        parser.error("standalone probe cannot await a foreground finalize")
    directory = args.control_dir
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "result.json").exists() or (directory / "ready").exists():
        raise ValueError("refusing reused worker directory")
    deadline = time.monotonic() + args.timeout
    copies = AclCopies(args.device, args.buffer_mib)
    try:
        (directory / "ready").touch()
        if not args.probe_operations:
            while not (directory / "start").exists():
                if (directory / "stop").exists():
                    raise RuntimeError("stopped before an active copy window")
                if time.monotonic() >= deadline:
                    raise TimeoutError("copy start timeout")
                time.sleep(.005)
        started, operations = raw_ns(), 0
        while True:
            if args.probe_operations and operations >= args.probe_operations:
                break
            if not args.probe_operations and (directory / "stop").exists():
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("copy active/finalize timeout")
            copies.copy()
            operations += 1
            if operations == 1:
                (directory / "active").touch()
        finished = raw_ns()
        if operations <= 0:
            raise RuntimeError("no active D2D copies")
        activity = dict(started_raw_ns=started, finished_raw_ns=finished, operations=operations, validation_status="pending")
        (directory / "activity-window.json").write_text(json.dumps(activity) + "\n")
        if args.defer_finalize:
            (directory / "paused").touch()
            while not (directory / "finalize").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("foreground did not authorize finalization")
                time.sleep(.01)
        authorized = raw_ns()
        copies.validate()
        result = dict(kind="copy", backend="aclrtMemcpyAsync", memcpy_kind="ACL_MEMCPY_DEVICE_TO_DEVICE",
                      pid=os.getpid(), runtime_device_index=args.device, buffer_mib=args.buffer_mib,
                      started_raw_ns=started, finished_raw_ns=finished, operations=operations,
                      finalize_deferred=args.defer_finalize, finalize_authorized_raw_ns=authorized,
                      max_error=0, status="completed_not_proof_of_contention")
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        copies.close()


if __name__ == "__main__":
    main()
