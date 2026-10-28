from __future__ import annotations

import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test.anomaly_injection.acl_copy_load import AclCopies


class AclCopyTests(unittest.TestCase):
    def library(self):
        buffers, events = [], []
        def allocate(pointer, size, policy):
            memory = ctypes.create_string_buffer(size)
            buffers.append(memory)
            pointer._obj.value = ctypes.addressof(memory)
            return 0
        def memset(pointer, maximum, value, size):
            ctypes.memset(pointer, value, size)
            return 0
        def memcpy(destination, maximum, source, size, kind, *stream):
            events.append(kind)
            ctypes.memmove(destination, source, size)
            return 0
        def stream(pointer):
            pointer._obj.value = 1
            return 0
        library = SimpleNamespace(**{name:Mock(return_value=0) for name in ("aclInit","aclFinalize","aclrtSetDevice","aclrtMalloc","aclrtFree","aclrtMemset","aclrtCreateStream","aclrtDestroyStream","aclrtSynchronizeStream","aclrtMemcpyAsync","aclrtMemcpy")})
        library.aclrtMalloc.side_effect = allocate
        library.aclrtMemset.side_effect = memset
        library.aclrtCreateStream.side_effect = stream
        library.aclrtMemcpyAsync.side_effect = memcpy
        library.aclrtMemcpy.side_effect = memcpy
        return library, events, buffers

    def test_explicit_d2d_async_and_post_measurement_validation(self):
        library, events, buffers = self.library()
        copies = AclCopies(1, 1, library)
        copies.copy()
        self.assertEqual(events, [3,3])
        copies.validate()
        self.assertEqual(events, [3,3,2])
        copies.close()
        self.assertEqual(library.aclrtFree.call_count, 2)
        library.aclrtDestroyStream.assert_called_once()
        library.aclFinalize.assert_called_once()

    def test_initialization_failure_cleans_only_its_own_allocations(self):
        library, _, buffers = self.library()
        library.aclrtCreateStream.side_effect = None
        library.aclrtCreateStream.return_value = 123
        with self.assertRaises(RuntimeError):
            AclCopies(1, 1, library)
        self.assertEqual(library.aclrtFree.call_count, 2)
        library.aclFinalize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
