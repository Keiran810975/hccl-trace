# 910C BF16 GEMM 兼容修复与设备验收

## 结论

2026-10-25，Node0自有非特权`zjy-new`的单机4 Rank混合负载及完整诊断预检通过。
修复是测试程序显式使用官方单组GEMM接口，不是重装CANN或修复所有`torch.matmul`路径。
没有修改驱动、验签、Device包或其他容器，也没有缩小矩阵、通信量或降低精度。

## 原因与对照

在同一容器、同一设备、相同Host库和官方Device包下：

| 测试 | 结果 |
| --- | --- |
| 旧负载BF16 `(2048,8192) @ (8192,24576)` | 原`torch.matmul`通过；日志走MatMulV3Nd/MatMulV3Common |
| 新负载BF16 `(2048,4096) @ (4096,12288)` | 原`torch.matmul`失败；日志查找MatMulV2配置失败，报561103 |
| 新尺寸前补两次INT32初始化AllReduce，4 Rank HOST | 仍失败，不能归因于遗漏通信初始化 |
| 新尺寸，单组`npu_grouped_matmul` | 通过；已知输入的GEMM最大误差0，GELU正常 |

因此此前双机能跑通与当前报错不矛盾：计算尺寸不同，触发了不同算子路径。
证据支持形状相关的算子选路/配置问题，不能笼统断言整套计算包不可用。

接口依据：[torch_npu.npu_grouped_matmul官方说明](https://www.hiascend.com/document/detail/zh/Pytorch/700/apiref/apilist/ptaoplist_000155.html)。
这里使用一组输入、`split_item=0, group_type=-1`，计算一次独立BF16矩阵乘法。
其物理内核与原普通matmul可能不同，因此新21例必须全部采用同一显式后端，不能把旧/新
计算内核的性能差别误认为注入效果。原`torch.matmul`缺配置的路径未修复。

## 代码范围

- `test/anomaly_injection/npu_compute.py`统一显式GEMM入口，校验二维BF16输入和输出尺寸；不静默回退。
- `test/multinode_commmix_train.py --gemm-backend grouped`覆盖QKV、Output、FFN两次GEMM；默认仍为matmul。
- 同一选项传入单进程后台计算竞争，随机矩阵N不是2次幂时使用可精确验证的全1输入。
- `run_single_node_case --preflight`保留正式矩阵、4 Block及64/128/256MiB桶，仅缩短为1预热+7测量。
- 队列同时检查完整尺寸混合预检、单进程通信预检及2304/6144阶后台计算预检，不用纯通信替代。

## 实测验收

4 Rank在物理芯片9/11/13/15，即容器runtime1/3/5/7运行，HOST模式。
tokens2048、hidden4096、FFN16384、4 Block；每轮12次FP32 SUM AllReduce，每Rank输入1.75GiB。

| 项目 | 本次真实结果 |
| --- | --- |
| 4 Rank混合负载 | 全部完成1预热+7测量，AllReduce最大误差0，激活校验和有限且一致 |
| 语义与真实DB精确匹配 | 18,944 / 18,944，100% |
| Notify Wait配对 | 17,408 / 17,408 |
| execution graph | 47,064节点、63,928边，无环；8,192跨Rank Notify边、9,216本地Notify边 |
| 最近5轮对比 | 3,200任务可比，726个标慢；正常预检false_alarm=true，不是准确率验收 |
| 后台计算N=2304 / 6144 | 分别5,390 / 518次操作，误差均0；独立预检不证明竞争效果 |
| 本地测试 | 189项诊断测试、60项测试脚本测试通过 |

18,944/18,944仅表示已产生语义的任务均匹配，不代表47,064个profiler任务全有语义。
正常预检只有1轮预热，其波动不能代表10轮预热后的正式误报率；未改动判慢阈值。

## 证据与剩余工作

容器实验根目录：`/workspace/single-910c-random-20261024`。
本次运行源码快照：`src-gemm-fixed-20261025`，哈希在`gemm-fixed-provenance.json`。
最终修复源码另存`src-gemm-fixed-final-20261025`，不覆盖前一快照。
基线提交`24559bc35ca87d472c913e1cb0efecd50bfbad3f`加未提交修改；未提交、未推送。

真实产物在`preflight-mixed-grouped-v1/diagnosis/preflight-single-910c-4r-normal/`：
`execution.html`、`waits.html`、`resource.html`、`rolling/index.html`和JSON/CSV结果。
本地同名证据位于`test/out/single-node-910c-random-20261024/evidence/`。

**正式21例仍为0次启动、0次完成**。本次解决了负载执行与完整采集诊断的阻塞，未验证异常定位准确率。
短预检保留全部原始和派生产物约1.05GB；按迭代数线性外推，21例约166GB（仅粗估，非实测）。
共享数据盘当时可用约128GB，需先安排逐例无损归档/迁回本地或可用存储，再启动完整队列，
不能删他人数据或把磁盘写满。未挂新的后台队列或自动监控。
