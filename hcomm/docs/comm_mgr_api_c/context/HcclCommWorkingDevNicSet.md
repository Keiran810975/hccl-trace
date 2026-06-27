# HcclCommWorkingDevNicSet<a name="ZH-CN_TOPIC_0000002486848098"></a>

## 产品支持情况<a name="zh-cn_topic_0000002305748108_section10594071513"></a>

<a name="zh-cn_topic_0000002305748108_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002305748108_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002305748108_p1883113061818"><a name="zh-cn_topic_0000002305748108_p1883113061818"></a><a name="zh-cn_topic_0000002305748108_p1883113061818"></a><span id="zh-cn_topic_0000002305748108_ph20833205312295"><a name="zh-cn_topic_0000002305748108_ph20833205312295"></a><a name="zh-cn_topic_0000002305748108_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002305748108_p783113012187"><a name="zh-cn_topic_0000002305748108_p783113012187"></a><a name="zh-cn_topic_0000002305748108_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002305748108_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002305748108_p48327011813"><a name="zh-cn_topic_0000002305748108_p48327011813"></a><a name="zh-cn_topic_0000002305748108_p48327011813"></a><span id="zh-cn_topic_0000002305748108_ph583230201815"><a name="zh-cn_topic_0000002305748108_ph583230201815"></a><a name="zh-cn_topic_0000002305748108_ph583230201815"></a><term id="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002305748108_p7948163910184"><a name="zh-cn_topic_0000002305748108_p7948163910184"></a><a name="zh-cn_topic_0000002305748108_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002305748108_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002305748108_p14832120181815"><a name="zh-cn_topic_0000002305748108_p14832120181815"></a><a name="zh-cn_topic_0000002305748108_p14832120181815"></a><span id="zh-cn_topic_0000002305748108_ph1292674871116"><a name="zh-cn_topic_0000002305748108_ph1292674871116"></a><a name="zh-cn_topic_0000002305748108_ph1292674871116"></a><term id="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002305748108_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002305748108_p19948143911820"><a name="zh-cn_topic_0000002305748108_p19948143911820"></a><a name="zh-cn_topic_0000002305748108_p19948143911820"></a>☓</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002305748108_section31291646"></a>

在集群场景下，配置通信域内的通信网卡。支持在同一NPU下，在某一Device网卡和备用网卡之间切换通信，备用网卡为同一NPU中的另一个Die网卡。

单次通信网卡配置时，同一通信域内的所有卡都需要调用该接口，且所有卡下发的ranks、useBackup和nRanks参数配置需保持一致。

> [!NOTE]说明
>配置通信网卡过程中，请注意以下操作的影响：
>-   同时下发切换到备网卡和切换到主网卡的命令时，如果在链路两端，一端切换到主网卡，一端切换到备用网卡，则命令执行失败。
>-   如果存在一条卡1和卡2的链路，第一次下发命令使卡1切到备用网卡，第二次下发命令使卡2换到默认网卡，此时卡1和卡2之间的链路会使用默认网卡通信，卡1和其他卡的链路会使用备用网卡通信。
>-   如果卡1和卡2的网卡互为备用网卡，并且两张卡同时下发切换到备用网卡的命令，那么卡1和卡2使用的通信网卡将会互换。

## 函数原型<a name="zh-cn_topic_0000002305748108_section18389930"></a>

```
HcclResult HcclCommWorkingDevNicSet(HcclComm comm, uint32_t *ranks, bool *useBackup, uint32_t nRanks)
```

## 参数说明<a name="zh-cn_topic_0000002305748108_section13189358"></a>

<a name="zh-cn_topic_0000002305748108_table24749807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002305748108_row60665573"><th class="cellrowborder" valign="top" width="17.61%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002305748108_p14964341"><a name="zh-cn_topic_0000002305748108_p14964341"></a><a name="zh-cn_topic_0000002305748108_p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="12.870000000000001%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002305748108_p4152081"><a name="zh-cn_topic_0000002305748108_p4152081"></a><a name="zh-cn_topic_0000002305748108_p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="69.52000000000001%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002305748108_p774306"><a name="zh-cn_topic_0000002305748108_p774306"></a><a name="zh-cn_topic_0000002305748108_p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002305748108_row13564174312568"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002305748108_p14564134316565"><a name="zh-cn_topic_0000002305748108_p14564134316565"></a><a name="zh-cn_topic_0000002305748108_p14564134316565"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002305748108_p95641043195610"><a name="zh-cn_topic_0000002305748108_p95641043195610"></a><a name="zh-cn_topic_0000002305748108_p95641043195610"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002305748108_p16564154315618"><a name="zh-cn_topic_0000002305748108_p16564154315618"></a><a name="zh-cn_topic_0000002305748108_p16564154315618"></a>指定通信网卡的通信域。</p>
<p id="zh-cn_topic_0000002305748108_p429419337019"><a name="zh-cn_topic_0000002305748108_p429419337019"></a><a name="zh-cn_topic_0000002305748108_p429419337019"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002305748108_row43502734719"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002305748108_p1935132714473"><a name="zh-cn_topic_0000002305748108_p1935132714473"></a><a name="zh-cn_topic_0000002305748108_p1935132714473"></a>ranks</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002305748108_p535112718471"><a name="zh-cn_topic_0000002305748108_p535112718471"></a><a name="zh-cn_topic_0000002305748108_p535112718471"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002305748108_p1258713452483"><a name="zh-cn_topic_0000002305748108_p1258713452483"></a><a name="zh-cn_topic_0000002305748108_p1258713452483"></a>指定通信网卡的rank在通信域中的rank id组成的数组。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002305748108_row761312542469"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002305748108_p1561325454610"><a name="zh-cn_topic_0000002305748108_p1561325454610"></a><a name="zh-cn_topic_0000002305748108_p1561325454610"></a>useBackup</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002305748108_p96131954134613"><a name="zh-cn_topic_0000002305748108_p96131954134613"></a><a name="zh-cn_topic_0000002305748108_p96131954134613"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002305748108_p1556913518211"><a name="zh-cn_topic_0000002305748108_p1556913518211"></a><a name="zh-cn_topic_0000002305748108_p1556913518211"></a>指定ranks中的卡是否使用备用网卡。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002305748108_row6482175112259"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002305748108_p6206859185514"><a name="zh-cn_topic_0000002305748108_p6206859185514"></a><a name="zh-cn_topic_0000002305748108_p6206859185514"></a>nRanks</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002305748108_p12068593559"><a name="zh-cn_topic_0000002305748108_p12068593559"></a><a name="zh-cn_topic_0000002305748108_p12068593559"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002305748108_p192061359185514"><a name="zh-cn_topic_0000002305748108_p192061359185514"></a><a name="zh-cn_topic_0000002305748108_p192061359185514"></a>指定切换网卡的rank数量。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002305748108_section51595365"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002305748108_section61705107"></a>

-   配置前，请确保当前环境上的通信任务已完成。
-   属于同一通信域的rank调用该接口时传入的ranks和useBackup数组长度与nRanks数量保持一致。
-   使用该接口需满足以下两种情况时，才会发生实际的网卡切换。
    -   HCCL\_OP\_RETRY\_ENABLE的“L2”开启重执行，即“L2”配置为1。关于环境变量的详细说明，可参见《环境变量参考》。
    -   拓扑形态存在RDMA链路。

-   对于不支持的场景，如HCCL\_OP\_RETRY\_ENABLE未开启重执行时，会返回HCCL\_SUCCESS并在日志中打印WARNING，但实际未切换网卡。
-   针对同一个rank，HcclCommWorkingDevNicSet接口需要one by one保序调用，不支持并发下发。
-   针对整个通信域，调用HcclCommWorkingDevNicSet接口时，在不同rank间要保证同一下发顺序。
-   comm句柄指向的通信域必须已下发过算子才能执行网卡配置，后续新下发同类型同参数的算子会继续使用同样的网卡配置，其他新下发的算子会使用默认网卡通信。不满足以上要求，会出现网卡配置失败。

## 调用示例<a name="zh-cn_topic_0000002305748108_section10236329223"></a>

```c
HcclComm comm;
uint32_t rankSize = 4;
uint32_t rankIds[rankSize] = {0, 3, 7, 12};
bool useBackup[rankSize] = {true, true, true, true};
HcclCommWorkingDevNicSet(comm, rankIds, useBackup, rankSize);
```

