#!/usr/bin/env python3
"""Compile real trace sources against minimal SDK stubs; no device claims.

Run on Linux: python test/test_aicpu_semantic.py --out-dir test/out/aicpu-unit
The real HCOMM device build separately checks SDK types and linking.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'aicpu').mkdir(exist_ok=True)
    trace = root / 'hcomm/src/common/debug/profiling'
    scope = root / 'hcomm/src/algorithm/base/alg_template/component'
    for src in (trace / 'task_semantic_trace.cc', trace / 'task_semantic_aicpu.cc',
                trace / 'inc/task_semantic_trace.h', trace / 'inc/task_semantic_aicpu.h',
                scope / 'task_semantic_scope.cc', scope / 'task_semantic_scope.h'):
        shutil.copy2(src, out / src.name)
    (out / 'hccl_common.h').write_text("""#pragma once
#include <cstdint>
#include <string>
#include <vector>
using u32=uint32_t; using s32=int32_t; using u64=unsigned long long;
constexpr u32 INVALID_UINT=0xffffffffU, INVALID_VALUE_RANKID=INVALID_UINT;
constexpr u64 INVALID_U64=0xffffffffffffffffULL;
using HcclResult=int; constexpr int HCCL_SUCCESS=0;
void TestLog(const char*, ...);
inline void TestDiscard(const char*, ...) {}
#define HCCL_INFO(...) TestLog(__VA_ARGS__)
#define HCCL_DEBUG(...) TestDiscard(__VA_ARGS__)
#define HCCL_WARNING(...) TestLog(__VA_ARGS__)
#define HCCL_RUN_INFO(...) TestLog(__VA_ARGS__)
""", encoding='utf-8')
    (out / 'profiler_base_pub.h').write_text("""#pragma once
namespace hccl { enum class TaskType { TASK_SDMA, TASK_RDMA, TASK_REDUCE_INLINE,
TASK_REDUCE_TBE, TASK_NOTIFY_RECORD, TASK_NOTIFY_WAIT, TASK_HOST,
TASK_GRAPH_LAUNCH, TASK_BATCH_REPORT, TASK_FLIP }; }
""", encoding='utf-8')
    # Extract the real SDK test header's layout, not a guessed task-ID offset.
    header = (root / 'hcomm/test/ut/depends/pkg_inc/runtime/runtime/rt_stars_define.h').read_text(encoding='utf-8')
    header = header[header.index('typedef struct tagStarsSqeHeader'):header.index('} rtStarsSqeHeader_t;') + len('} rtStarsSqeHeader_t;')]
    (out / 'aicpu/aicpu_hccl_sqcqv1.h').write_text('#pragma once\n#include <cstdint>\n' + header, encoding='utf-8')
    (out / 'main.cc').write_text(r"""
#include "task_semantic_aicpu.h"
#include "task_semantic_scope.h"
#include "aicpu/aicpu_hccl_sqcqv1.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
using namespace hccl;
std::vector<std::string> logs;
void TestLog(const char *fmt, ...) {
 char buf[4096]; va_list ap; va_start(ap,fmt); vsnprintf(buf,sizeof(buf),fmt,ap); va_end(ap);
 logs.emplace_back(buf);
}
int main() {
 unsetenv("ASCEND_RT_VISIBLE_DEVICES");
 assert(ResolveTaskSemanticDeviceId(2)==2);
 setenv("ASCEND_RT_VISIBLE_DEVICES","8,10,12,14",1);
 assert(ResolveTaskSemanticDeviceId(1)==10 && ResolveTaskSemanticDeviceId(4)==INVALID_UINT);
 setenv("ASCEND_RT_VISIBLE_DEVICES","0,2",1);
 assert(ResolveTaskSemanticDeviceId(1)==2);
 for (const char *invalid : {"0,0", "0,", "-1", "0, 2", "4294967295", "18446744073709551616"}) {
  setenv("ASCEND_RT_VISIBLE_DEVICES",invalid,1); assert(ResolveTaskSemanticDeviceId(0)==INVALID_UINT);
 }
 unsetenv("ASCEND_RT_VISIBLE_DEVICES");
 {
  TaskSemanticDeviceScope enabled(true,7,14);
  TaskSemanticTraceInfo direct{}; direct.source="host";
  setenv("ASCEND_RT_VISIBLE_DEVICES","0,2",1);
  ReportTaskSemanticTrace(1,45,3,TaskType::TASK_SDMA,&direct);
  assert(logs.back().find("device_id[2]")!=std::string::npos);
  direct.source="aicpu";
  ReportTaskSemanticTrace(1,45,3,TaskType::TASK_SDMA,&direct);
  assert(logs.back().find("device_id[1]")!=std::string::npos);
  direct.source="host";
  ReportTaskSemanticTrace(1,45,4,TaskType::TASK_SDMA,&direct,0);
  ReportTaskSemanticGraphCorrelation(1,47,9);
  assert(logs.back().find("[HcclTaskGraphCorrelation]")!=std::string::npos);
  assert(logs.back().find("device_id[2]")!=std::string::npos);
  logs.clear(); unsetenv("ASCEND_RT_VISIBLE_DEVICES");
 }
 alignas(8) uint8_t sqes[128]{}, cache[128]{};
 auto *h=reinterpret_cast<rtStarsSqeHeader_t *>(sqes); h->rtStreamId=7; h->taskId=65535;
 assert(!IsTaskSemanticTraceEnabled());
 {
  TaskSemanticDeviceScope enable(true, 7, 14);
  assert(IsTaskSemanticTraceEnabled());
  bool other=true; std::thread t([&]{other=IsTaskSemanticTraceEnabled();}); t.join(); assert(!other);
  {
   TaskSemanticScope parent(MakeTaskSemanticTraceInfo("RS",3,4,8,2));
   TaskSemanticTraceInfo rankInfo{}; assert(GetTaskSemanticTraceInfo(rankInfo));
   assert(rankInfo.userRank==7 && rankInfo.commRank==4);
   { TaskSemanticDeviceScope nested(true, 9, 15); assert(GetTaskSemanticTraceInfo(rankInfo)); assert(rankInfo.userRank==9);
     assert(GetTaskSemanticPhysicalDeviceId()==15); }
   assert(GetTaskSemanticTraceInfo(rankInfo) && rankInfo.userRank==7);
   assert(GetTaskSemanticPhysicalDeviceId()==14);
   TaskSemanticEventScope event("rx_wait_start","link_rx_wait");
   CaptureAicpuTaskSemantic(sqes,TaskType::TASK_NOTIFY_WAIT,123456789012345ULL,0);
   CaptureAicpuTaskSemantic(sqes+64,TaskType::TASK_NOTIFY_WAIT,2,0);
   TaskSemanticTraceInfo info{}; assert(!GetTaskSemanticTraceInfo(info));
  }
  // Scope has ended before reporting; cached copies must preserve the snapshot.
  std::memcpy(cache,sqes,sizeof(sqes)); CopyAicpuTaskSemantic(cache,sqes,2);
  ReportAicpuTaskSemantic(sqes,2,true);
  assert(logs.size()==1 && logs.back().find("step[3]")!=std::string::npos);
  assert(logs.back().find("device_id[14]")!=std::string::npos);
  assert(logs.back().find("notify_id[123456789012345]")!=std::string::npos);
  assert(logs.back().find("source[aicpu]")!=std::string::npos);
  assert(logs.back().find("user_rank[7]")!=std::string::npos);
  assert(logs.back().find("comm_rank[4]")!=std::string::npos);
  assert(logs.back().find("hccl_task_id[65535]")!=std::string::npos);
  ReportAicpuTaskSemantic(sqes,2,true); assert(logs.size()==1);
  auto *c=reinterpret_cast<rtStarsSqeHeader_t *>(cache); c->taskId=1; c->rtStreamId=9;
  { TaskSemanticDeviceScope changedScope(true, 9, 15); ReportAicpuTaskSemantic(cache,2,false); }
  assert(logs.size()==2 && logs.back().find("hccl_task_id[1]")!=std::string::npos);
  assert(logs.back().find("device_id[14]")!=std::string::npos);
  assert(logs.back().find("stream_id[9]")!=std::string::npos);
  { TaskSemanticDeviceScope off(false); ReportAicpuTaskSemantic(cache,2,false); assert(logs.size()==2); }
  ReportAicpuTaskSemantic(cache,2,false); assert(logs.size()==3);
  // Uninstrumented copy and erased/reused slots may never inherit old semantics.
  CopyAicpuTaskSemantic(cache,sqes,2); ReportAicpuTaskSemantic(cache,2,false); assert(logs.size()==3);
  { TaskSemanticScope event(MakeTaskSemanticTraceInfo("AG",9,4,8,0,"copy","local_copy"));
    CaptureAicpuTaskSemantic(sqes,TaskType::TASK_SDMA,0,-1); }
  EraseAicpuTaskSemantic(sqes,2); ReportAicpuTaskSemantic(sqes,2,true); assert(logs.size()==3);
 }
 assert(!IsTaskSemanticTraceEnabled());
 assert(GetTaskSemanticPhysicalDeviceId()==INVALID_UINT);
 { TaskSemanticDeviceScope missingDevice(true, 7);
   TaskSemanticScope event(MakeTaskSemanticTraceInfo("RS",0,0,2,0,"copy","local_copy"));
   CaptureAicpuTaskSemantic(sqes,TaskType::TASK_SDMA,0,-1);
   ReportAicpuTaskSemantic(sqes,2,true); assert(logs.size()==3); }
 {
  TaskSemanticDeviceScope enable(true, 7, 14);
  TaskControlAnchor anchor; anchor.deviceId=14; anchor.streamId=12; anchor.taskId=42;
  { TaskControlScope control(anchor);
    CaptureAicpuTaskSemantic(sqes,TaskType::TASK_NOTIFY_RECORD,99,-1);
    TaskControlAnchor read; assert(GetTaskControlAnchor(read) && read.taskId==42);
    { TaskControlScope nested(TaskControlAnchor{}); assert(!GetTaskControlAnchor(read)); }
    assert(GetTaskControlAnchor(read) && read.taskId==42);
  }
  TaskControlAnchor read; assert(!GetTaskControlAnchor(read));
  h->taskId=7; h->rtStreamId=91;
  ReportAicpuTaskSemantic(sqes,1,true);
  assert(logs.size()==4 && logs.back().find("[HcclTaskControl]")!=std::string::npos);
  assert(logs.back().find("anchor_task_id[42]")!=std::string::npos);
  assert(logs.back().find("notify_id[99]")!=std::string::npos);
  assert(logs.back().find("stream_id[91]")!=std::string::npos);
 }
 {
  TaskSemanticDeviceScope enable(true, 7, 14);
  TaskControlAnchor anchor; anchor.deviceId=14; anchor.streamId=12; anchor.taskId=42;
  { TaskBuildContext build(anchor); TaskControlAnchor read; assert(GetTaskBuildAnchor(read));
    assert(!GetTaskControlAnchor(read));
    auto info=MakeTaskSemanticTraceInfo("reduce_scatter",0,7,2,0,nullptr,nullptr,0,"nhr");
    ReportTaskBuildSpan(anchor,info,999999); assert(logs.size()==4);
    ReportTaskBuildSpan(anchor,info,2000000); assert(logs.size()==5);
    assert(logs.back().find("timing_domain[aicpu_build_cpu]")!=std::string::npos);
    assert(logs.back().find("kernel_task_id[42]")!=std::string::npos);
  }
  TaskControlAnchor read; assert(!GetTaskBuildAnchor(read));
 }
 puts("PASS: one-shot, delayed report, cache replay identity, thread/off isolation, wide notify, slot reuse");
}
""", encoding='utf-8')
    binary = out / 'aicpu-semantic-test'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-DCCL_KERNEL',
                    '-pthread', '-I', str(out), *(str(out / n) for n in
                    ('main.cc', 'task_semantic_trace.cc', 'task_semantic_aicpu.cc', 'task_semantic_scope.cc')),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
