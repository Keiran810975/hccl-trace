# Node0 + Node3 低日志十九组接续

## 当前检查点：2026-11-08

旧501 capture已按明确授权无损迁至Node0，599文件逐项SHA和独立复读通过；仅清Node3副本，
Node0原capture及preflight-report三报告、两端源码/环境保留。[迁移凭证](../../../artifacts/multinode19-lowlog-20261106-1000/node3-501-migration.md)。

1014训练和诊断流程完成，效应有效但封存候选0/4；两节点10095文件完整归档和真实ACK通过。
独立从封存报告重算累计12/19、96Rank数值通过，任一/首选4/12个已完成例；1012技术失败、
1015..1020六例未跑，旧INFO901仍单列。所有已完成原始和全图在本机逐项SHA压缩包，可无损恢复。

归档助手79101连续SSH关闭后退出，监督2390786因90分钟ACK超时停止，不是训练失败。
未重跑1014，只补原采集归档。两机原策略/官方包、Device/端口timer inactive、registry absent、
端口原200Gbps及旧监督退出已再次实读。随后按用户本次继续授权，仅控制根增加按停止检查点SHA
绑定的单次消费入口；旧状态/源码/launch/log备份到archive-checkpoints，旧标记不重提。
六例r4清单SHA和原计划、诊断、负载、阈值及注入均不变，35本地控制及5服务器检查点测试通过。

新唯一监督3238321/start ticks503369603，waiting_node0、active=null，完整计数仍12/19。
Node3磁盘36.39GiB，但两机全8卡两芯片目前均被非本队列python/VLLM任务占用；未起新训练，
不停止外部任务。继续原48小时有界等待，Node0整机及Node3目标NPU4..7需空闲并保留30秒复核；
仅将Node3忙时的提前退出改为同一有界等待，未降低准入。新控制SHA
`22ba5927264559e86334e5e49351e569ea4a873008189b32a82f22e3a1f7b26c`，父检查点SHA
`6537085f66ea05ef957f6d4b6504cefea7bc70197a5ec18b1119eaac1cebb309`。

本机唯一归档助手91412有限72小时，需要本机在线。只读监控走已核验Node0入口，不再内部自连接，
复用连接并保留主机密钥校验；只对无partial的连接中断最长10分钟有界重查。此前失败历史保留，
不因本机断连重提实验。当前累计表和三报告入口见[接续结果](../../../artifacts/multinode19-lowlog-20261106-1000/remaining8-progress.md)。

## 2026-11-07检查点（历史）

本节优先于下文历史启动/终态。1013已从原采集完成诊断、效应和两节点10127文件SHA归档；
Copy有效但候选0/3，累计11/19完整、88Rank数值通过。1012技术失败，1014..1020七例未运行，
旧INFO首例901仍单列。原八组控制因90分钟归档ACK超时停止，监督1841945退出，不冒充存活。
归档传输未开始前SSH255导致本机助手退出，后续只补原1013归档，不重训。两机原策略/官方包、
端口8/9、timer inactive/registry absent及监督退出已再次实读通过。

Node3目前35.017GiB余量，比35GiB仅多约17MiB；正在请求旧501 capture约1.48GiB完整迁至
Node0、逐项SHA后精确清源副本授权，未获答复前不删除。两机最新空闲实读及35GiB门禁通过，
原归档检查点已一次性接续1014..1020，新唯一监督2390786/start ticks501210992，1014准备中。
本机唯一归档助手79101有限72小时，旧助手SSH255及ACK超时历史完整保留；不改1013快照/
诊断/参数、不补跑1012，不降低空间门槛。Node0原生hccl-test27/27已先单独完成且恢复，
持原队列互斥锁，不与多机同时占卡。多机完整验收仍是11/19，准备中不计完成。

## 最新接续：2026-11-07

用户重新要求继续，并明确批准1012完整失败采集备份及仅清Node3已验证capture副本。
7862文件本机逐项SHA通过；只清Node3该例995文件，Node0原件及两端源码/环境保留。
失败事实不改、无诊断完成ACK。清理后两机35GiB门禁通过，两机各46项控制测试通过。

原1000根仍stopped/10，原监督不重启；新单一控制在该根`remaining8-20261107/`，
首次启动监督PID1841945/start ticks499515401，只跑原未运行1013..1020八例。
截至首次身份实读已进入1013准备阶段，不冒充已完成采集/效应或诊断。
随后1013已实际进入八Rank采集并转CPU分析，尚不等于效应或定位通过。实际有进程的原生输出
为`Process id:... Process name:... Process memory(MB):...`，并非表格；据此只对尚未运行的
1014..1020增加严格逐行解析，未知行仍拒绝。当前1013的r3快照不改，原生输出已留证。
余7例r4清单SHA `b258692a5d2fba4ca41dd1c06d0dbe10bf41ea651e0a8b929de1836b201e8ded`，
两机各43项原控制测试及本地46项含接续驱动测试通过。旧清单/文件保存在before-native-format，
控制清单保留修正前版本及逐例版本映射；监督进程、原计划、诊断及阈值不改。
原plan SHA `d6ee44e49630dc2c13dcfa4691b3d60c10c0433a3ba140915038efa1570bae4a`不变，
未运行例r3清单SHA `07161ff01101ccb615bc0e7ebe6ad953c8359fed9f591bf4f1410154fb4d2dc0`。
只变两处RoCE进程安全查询及其测试：全机扫描改为授权NPU4两芯片并行原生查询；
保留未知PID拒绝、原20Gbps/位置/5完整轮与全部诊断规则，旧采集源码不动。
修改前两机每例文件和清单均备份。额外接续驱动SHA
`0d97de3ac8e7d2fd72da09ec63d0e669cedb1a045263fbc39137b948f280d2d0`。

本地控制证据`test/out/multinode8-resume-20261107/`；归档仍存原19组本地live目录，
一次只归档该监督当前awaiting_verified_archive例。只读入口为其中`monitor_once.py`，
仅当前例归档可加`--offload-ready`，禁止重复归档助手或监督。
原10完成+1012失败保持分母；即使余8全完成，也只可称18/19完整和1技术失败，不是19/19。
累计结果及三报告索引见[接续结果](../../../artifacts/multinode19-lowlog-20261106-1000/remaining8-progress.md)。

## 最新终态：2026-11-07

本节优先于下文历史进度。原队列于北京时间08:41:49停止，完整验收1002..1011共10/19；
1012（RoCE第3组）在Rank0收尾检查限速未覆盖5个完整轮次时失败，1013..1020未运行。
Rank0已输出正式轮49，其他7份Rank结果passed，两机各4份DB留存；不能称训练前失败，
也不能补造第8份数值、效应或诊断通过。未重跑、未修改活动快照或重提监督。

完整10组效应均有效：Copy执行候选3/5（任一/首选1/2个已完成例），通信0/12（0/3），
Host区间3/3（3/3），RoCE执行候选0/6（0/2）。合计任一和首选4/10，80份Rank数值通过。
余9个未完整验收中，1个技术失败、8个未启动，均保留计划分母；旧INFO首例901单列。

10组两节点完整原始和全图已本机逐项SHA归档。1012失败原件仍保留两台服务器，故障小证据
已读回；该失败例完整备份被自动权限检查要求用户另行确认，命令未执行，不声称已归档。
08:42终态核验监督退出、两机原策略/官方包、全部timer inactive、registry absent、自有容器
仅sleep，端口8/9恢复原200Gbps。本机归档助手正常退出，本次90分钟巡检随终态结束；
不再查资源或自动接续。后续完整备份及处置需用户确认，不自动重跑1012凑数。

见[终态汇总](../../../artifacts/multinode19-lowlog-20261106-1000/final-status.md)和
[1012失败说明](../../../artifacts/multinode19-lowlog-20261106-1000/incident-1012.md)。

用户2026-11-06明确选择：剩余19组改用刚验证的低日志版本，旧首例单列；允许将本项目
旧采集完整归档到Node0，逐文件校验后只清Node3对应原始副本，保留报告、源码和训练环境。
不停止任何外部任务，不重启已停止的900队列，不重跑901。

## 冻结范围

原批[20组计划](multinode20-20261105.md)实际完成1/20后由用户停止，901为有效Copy注入但
候选0/3、任一/首选0/1。新计划逐字保留原计划余下19个case、workload、注入位置和强度、
dual-v2、前5正式轮均值/1.5倍/3MAD、20%下游及1ms校时门禁，不读真值调整候选。
旧首例不进入新配置分母：新Copy4组，通信/Host调用前迟到/RoCE限速各5组。
不能称同配置20组，也不能把旧首例漏诊删掉。

首个待跑例是原902通信竞争：正式轮12、Node0 Rank0与Node3 Rank4，独立后台两Rank
1GiB AllReduce。其后仍按原交错顺序，不添加计算竞争、正常重跑或无效补采。
每次八Rank GPT-2 Small DDP，Node0/Node3各4Rank，10预热+50正式，原workload seed20261103。

只用两机既有非特权zjy-new及NPU4..7，runtime1/3/5/7对应物理芯片9/11/13/15。
Node0整机空闲，目标整卡两芯片HBM/进程/磁盘/映射/端口门禁不变。Node3本次不再执行
停止任务操作；若新占用出现则门禁停止或有界等待，不追杀进程。

## 低日志变化

使用已构建配套Host/Device，Device包SHA
`b68ef612370ebb9c635e9fb9d94ddaf977be81a3d609d0e35936f20e41ceebd2`，Host libhcomm SHA
`498c951114cff9a2d6cd5e02958a6bf1bc3a90cd661ac93d4b0ba4243430a64e`。
全局WARNING、解除模块日志覆盖，HCCL/TASK L1/ASCENDCL开启、计算PMU关闭。
既有四种Device地址/anchor事实在语义trace开启时单独保留，消费者精确绑定规则不放宽。
这不是非通信TASK过滤，也不是已完成多机开销或准确率验收。
单机验证见[低日志试验](../../../artifacts/tool-lowlog-20261106/README.md)。

每例有独立7200秒Device恢复及演练；限速另有3600秒端口恢复。采集后先恢复实读再CPU诊断，
外层finally再次核验原策略/官方包、timer inactive和registry absent。
每例两机35GiB启动余量、8GiB运行应急余量。诊断先封存，再独立评测真实效应与命中；
无效则保留和归档后停止，漏诊但效应有效仍继续，不换参数补跑。
每例归档须两节点全部原始/debug/三报告逐文件SHA通过，才清本例已备份大副本并ACK。

## 来源与进度

新Node0唯一根：`/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-20261106-1000`。
Node3根：`/home/zjy-new/workspace/hccl-diagnose-node03-20261106-1000`。新例1002..1020
分别对应原902..920；case_id仍是原预冻结身份，不跨采集混用时间或任务ID。
新队列只有fresh启动入口，不能使用旧prestart/recover标记或再次执行部署。

本地状态`test/out/multinode20-continue-20261106/`，只读监控：

```bash
python3 test/monitor_multinode20.py --continuation --output test/out/multinode20-continue-20261106
```

仅当当前状态为awaiting_verified_archive，允许同命令加`--offload-ready`完成该当前例无损归档。
不得另启重复归档助手；未完成partial保留检查，不伪造ACK。当前进度以实际state/latest为准。

源码2860文件清单SHA `48838276dae759647ac88512c22dab7dfea8d2c97877a6a6a1f4b24b6975191d`，
plan SHA `d6ee44e49630dc2c13dcfa4691b3d60c10c0433a3ba140915038efa1570bae4a`。
修改前3355文件完整源码备份SHA `5995cf0eb9ef270401fc16824f58a7157fbd5472aa21493633d1b9f813d7fece`。
441诊断回归及65接续/恢复/归档/CLI专项本地通过，两机同源专项也通过。

初次上传校验发现SSH子查询提前读取stdin，停在解包之前；不完整包和错误原样留证。
只修同一根的上传，完整SHA核验后首次prepare/launch，没有重复训练或设备修改。
唯一监督PID3532382/start ticks491538946已实读匹配。首个通信竞争例已实际完成八Rank
10+50训练，数值/初始化/副本一致性独立核验通过，两机原始DB各4份，汇集后Node0为8份。
采集期间两机安装的新包及独立timer active已实读，之后两机恢复、现正CPU诊断，完整计数0/19。
这不等于注入或定位通过；完成条件为19份数值/效应/诊断/
独立评测/封存/恢复和两节点归档齐全，首例历史结果另列。
本地`follow_once.py`只跟踪这个已启动队列，并串行执行原校验归档ACK；不重提训练。
没有新增app定时监控。监督状态、归档锁和所有partial均须如实保留。

### 首组后处理接续

1002训练和原生诊断均passed后，效应评测因一条Notify Record的前5均值为0、慢化倍数为空而
抛出Decimal转换异常。该控制记录本就不属于强执行任务，错误发生在无用的提前数值解析，
不是训练、语义、SDK绑定或图门禁失败。保留首次监督及其stopped/0完整计数事实。

仅修后置效应评测：先按原任务类型准入，再解析SDMA/Inline Reduce的有效倍数；缺失执行
倍数不补成无穷或计为通过。阈值、候选、图、原始时间均不改。新增真实失败fixture及一次性
CPU接续门禁，67相关专项及441诊断回归通过，两机同源CPU专项也通过。
1002原采集/原源码/原三报告不动，3068项输入及报告SHA前后相同；新后处理源码另存
`postdiagnosis-evaluator/`并纳入完整归档。只对1000控制根及从未运行的1003..1020部署r2，
差异仅编排/后置效应评测及测试五文件；生产端、负载、注入和全部诊断消费者不变。

r2源码清单SHA `edf7d9f0d75abcd32d57d096793bbbd5dee9d93f049a52427aca79fec087eb26`，
plan SHA仍`d6ee44e49630dc2c13dcfa4691b3d60c10c0433a3ba140915038efa1570bae4a`。
当前唯一监督PID3671270/start ticks491857339；1002只从原报告完成效应评测，不重训或重诊。
`evaluation-continuation.json`已存在，禁止再次调用`--recover-evaluated`或接续辅助脚本。
原控制日志/状态/launch留在1000/postdiagnosis-v1，不冒充首次监督一直存活。

首组独立结果：预声明Rank0/4、第12轮通信竞争，两端后台各3次真实AllReduce；56个内部
执行任务满足1.5倍/3MAD并与实际窗口重叠，222慢Wait，effect gate通过。最终两个候选均
Node3 Rank6、第25轮，故严格候选0/2、任一/首选0/1，属于有效注入但漏诊。517538语义
100% exact，271082 Wait全部paired，36966跨机同步边，校时估计83.275us，八Rank数值通过。
结果已通知，不按已知注入改源头规则，保留漏诊分母；完整归档ACK后才接续下一组。

1002两节点10048文件已本机逐项SHA验证并写真实ACK，监督已自行进入waiting_node0，
completed=1/requested=19、active_case=null、next为1003调用前迟到。新出现的16个python
占满Node0全8卡两芯片，全部位于另一个容器18d3465f...，不是当前自有zjy-new；仅核对
PID/start ticks/cgroup容器身份，不读请求或环境，不停止外部任务，按原48小时门禁等待。
本地只读监控修正等待时优先使用最新last-node0-resources，而不是旧admission空闲快照；
此显示修正未部署到活动快照。两机原策略/官方包、全部timer inactive/registry absent、
holder released和自有容器仅sleep已重新实读，Node0端口8/9均原200Gbps。
一次本机DNS解析失败使前台跟踪退出，随后有界只读重查确认原监督存活，未重提训练；
本机连接错误增加三次有界重查，partial传输不自动覆盖或重试。当前唯一归档助手已交接为
本机后台PID50705，身份/源码哈希见background-follow-launch.json；原监督未重启。
只服务本次固定19组，上限112小时，等待资源时5分钟读取状态，原监督仍30分钟检查资源。
每次归档后独立重算，终态额外实读监督退出和恢复事实，才写completion或final-status。
本机电脑/网络需保持在线；错误写follow-status/follow-background/follow-exit，不新增app定时任务。
结果及报告索引见[进度](../../../artifacts/multinode19-lowlog-20261106-1000/progress.md)。

## 磁盘迁移

Node3初始可用约29GiB，未降低35GiB门槛。将旧092/104/009的capture目录归档到Node0：
`/home/commTeam/zjy/zjy-new-workspace/node3-capture-archive-20261106/`。
三份共2831文件、8649356617字节，逐文件SHA及迁移前后输入一致后，才移除Node3对应capture。
各原目录新增`capture-archived-node0.json`标明真实位置，报告、源码、环境均未删。
压缩包SHA及逐项清单留Node0各归档目录；本地凭证
`test/out/multinode20-continue-20261106/node3-archive-receipt.json`。
原始数据仍可由Node0归档无损恢复，不能再把旧Node3路径当作原始文件仍在。
