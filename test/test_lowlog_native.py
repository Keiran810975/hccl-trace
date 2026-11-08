"""Compile the changed logging branches with CPU stubs; not a device acceptance test."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from hccl.tools.diagnosis.aicpu_buffers import parse_buffers


class NativeLowLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('c++') or shutil.which('g++')
        if not compiler:
            raise unittest.SkipTest('C++14 compiler unavailable')
        root=Path(__file__).resolve().parents[1]
        profiling=(root/'hcomm/src/framework/device/debug/dfx/profiling/profiling_manager_device.cc').read_text()
        begin=profiling.index('HcclResult ProfilingManager::ReportMainStreamTask(')
        body=profiling[begin:profiling.index('HcclResult ProfilingManager::ReportFilpTask(',begin)]
        comm=(root/'hcomm/src/framework/device/framework/aicpu_communicator.cc').read_text()
        end=comm.index('    opUnfoldIdx_ += 1;',comm.index('HcclResult HcclCommAicpu::OrchestrateHcclOp('))
        begin=comm.rindex('    if (IsTaskSemanticTraceEnabled()) {',0,end)
        operation=comm[begin:end]
        stub=r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>
using u32=uint32_t;using u64=unsigned long long;using HcclResult=int;
constexpr int HCCL_SUCCESS=0,HCCL_E_PARA=1,MSPROF_REPORT_AICPU_HCCL_FLAG_TASK=1;
bool trace=false,debug=false,profile=true;int reports=0;
std::vector<std::string> lines;
void Log(const char*channel,const char*fmt,...){char b[2048];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);lines.push_back(std::string(channel)+"\t"+b);}
#define HCCL_RUN_INFO(...) Log("RUN",__VA_ARGS__)
#define HCCL_INFO(...) do{if(debug)Log("DEBUG",__VA_ARGS__);}while(0)
#define HCCL_ERROR(...) do{}while(0)
#define CHK_PTR_NULL(p) do{if(!(p))return 1;}while(0)
#define CHK_PRT_RET(c,m,v) do{if(c){m;return v;}}while(0)
#define CHK_PRT(v) do{assert((v)==0);}while(0)
namespace hccl { bool IsTaskSemanticTraceEnabled(){return trace;}struct Stream{u32 id(){return 11;}}; }
namespace aicpu {enum class status_t{AICPU_ERROR_NONE};status_t Identity(uint64_t&t,uint32_t&s){t=6001;s=901;return status_t::AICPU_ERROR_NONE;}auto GetTaskAndStreamId=&Identity;}
uint32_t StreamId(){return 901;}uint64_t TaskId(){return 6001;}
auto AicpuGetStreamId=&StreamId;auto AicpuGetTaskId=&TaskId;
uint64_t ProfGetCurCpuTimestamp(){return 0;}
struct MsprofAicpuHcclMainStreamTask{uint32_t streamId,taskId,type,aicpuStreamId;uint64_t aicpuTaskId;};
namespace dfx {struct ProfilingManager{
 static bool GetProfL0State(){return profile;}
 static int CallMsprofReportAdditionInfo(int,uint64_t,const void*,size_t){++reports;return 0;}
 static HcclResult ReportMainStreamTask(hccl::Stream&,uint16_t,uint16_t);
};
BODY
}
namespace hccl {
uint32_t GetRankSize(){return 2;}
void Operation(){struct{int opType;u64 inputPtr,inputSize,outputPtr,outputSize;}param{2,4096,4096,4096,4096};
struct{uint32_t userRank;}topoInfo_{3};u32 opUnfoldIdx_=999;
OPERATION
}
}
int main(int argc,char**argv){assert(argc==4);trace=std::atoi(argv[1]);debug=std::atoi(argv[2]);profile=std::atoi(argv[3]);
hccl::Stream stream;assert(dfx::ProfilingManager::ReportMainStreamTask(stream,65535,0)==0);
hccl::Operation();assert(reports==(profile?1:0));
for(const auto&line:lines)std::puts(line.c_str());}
'''.replace('BODY',body).replace('OPERATION',operation)
        cls.directory=tempfile.TemporaryDirectory(prefix='hccl-lowlog-native-')
        source=Path(cls.directory.name)/'branch.cc';cls.executable=source.with_suffix('')
        source.write_text(stub)
        result=subprocess.run([compiler,'-std=c++14',str(source),'-o',str(cls.executable)],capture_output=True,text=True,timeout=60)
        if result.returncode:
            cls.directory.cleanup()
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_branch(self,trace,debug,profile=True):
        result=subprocess.run([str(self.executable),str(int(trace)),str(int(debug)),str(int(profile))],
            capture_output=True,text=True,check=True,timeout=10)
        records=[line.split('\t',1) for line in result.stdout.splitlines()]
        prefix='[INFO] HCCL(100,aicpu_scheduler):2026-11-06 [lowlog.cc:1] [24]'
        facts=list(parse_buffers(prefix+message for _,message in records))
        return records,facts

    def test_trace_uses_runtime_channel_and_default_behavior_is_unchanged(self):
        for trace,debug in ((False,False),(False,True),(True,False),(True,True)):
            with self.subTest(trace=trace,debug=debug):
                records,facts=self.run_branch(trace,debug)
                self.assertEqual(len(records),4 if trace or debug else 0)
                if records:
                    self.assertEqual({channel for channel,_ in records},{'RUN' if trace else 'DEBUG'})
                    self.assertEqual(len(facts),1)
                    self.assertEqual(facts[0]['anchor_task_id'],65535)
                    self.assertEqual(facts[0]['input_buffer_ptr'],4096)

    def test_semantic_only_cannot_invent_a_profiler_anchor(self):
        records,facts=self.run_branch(True,False,False)
        self.assertEqual(len(records),2)
        self.assertEqual(facts,[])
