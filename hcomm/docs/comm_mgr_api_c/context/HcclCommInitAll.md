# HcclCommInitAll<a name="ZH-CN_TOPIC_0000002519087943"></a>

## 产品支持情况<a name="zh-cn_topic_0000001613857522_section10594071513"></a>

<a name="zh-cn_topic_0000001613857522_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001613857522_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001613857522_p1883113061818"><a name="zh-cn_topic_0000001613857522_p1883113061818"></a><a name="zh-cn_topic_0000001613857522_p1883113061818"></a><span id="zh-cn_topic_0000001613857522_ph20833205312295"><a name="zh-cn_topic_0000001613857522_ph20833205312295"></a><a name="zh-cn_topic_0000001613857522_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001613857522_p783113012187"><a name="zh-cn_topic_0000001613857522_p783113012187"></a><a name="zh-cn_topic_0000001613857522_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001613857522_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001613857522_p48327011813"><a name="zh-cn_topic_0000001613857522_p48327011813"></a><a name="zh-cn_topic_0000001613857522_p48327011813"></a><span id="zh-cn_topic_0000001613857522_ph583230201815"><a name="zh-cn_topic_0000001613857522_ph583230201815"></a><a name="zh-cn_topic_0000001613857522_ph583230201815"></a><term id="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001613857522_p7948163910184"><a name="zh-cn_topic_0000001613857522_p7948163910184"></a><a name="zh-cn_topic_0000001613857522_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001613857522_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001613857522_p14832120181815"><a name="zh-cn_topic_0000001613857522_p14832120181815"></a><a name="zh-cn_topic_0000001613857522_p14832120181815"></a><span id="zh-cn_topic_0000001613857522_ph1292674871116"><a name="zh-cn_topic_0000001613857522_ph1292674871116"></a><a name="zh-cn_topic_0000001613857522_ph1292674871116"></a><term id="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001613857522_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001613857522_p19948143911820"><a name="zh-cn_topic_0000001613857522_p19948143911820"></a><a name="zh-cn_topic_0000001613857522_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001613857522_section37208511199"></a>

单机通信场景中，通过一个进程统一创建多张卡的通信域（其中一张卡对应一个线程）。在初始化通信域的过程中，devices\[0\]作为root rank自动收集集群信息。

## 函数原型<a name="zh-cn_topic_0000001613857522_section35919731916"></a>

```
HcclResult HcclCommInitAll(uint32_t ndev, int32_t*  devices, HcclComm* comms)
```

## 参数说明<a name="zh-cn_topic_0000001613857522_section2586134311199"></a>

<a name="zh-cn_topic_0000001613857522_table0576473316"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001613857522_row1060511716320"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001613857522_p146051071139"><a name="zh-cn_topic_0000001613857522_p146051071139"></a><a name="zh-cn_topic_0000001613857522_p146051071139"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001613857522_p1160527939"><a name="zh-cn_topic_0000001613857522_p1160527939"></a><a name="zh-cn_topic_0000001613857522_p1160527939"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001613857522_p86058714320"><a name="zh-cn_topic_0000001613857522_p86058714320"></a><a name="zh-cn_topic_0000001613857522_p86058714320"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001613857522_row166054719318"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001613857522_p111231019101719"><a name="zh-cn_topic_0000001613857522_p111231019101719"></a><a name="zh-cn_topic_0000001613857522_p111231019101719"></a>ndev</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001613857522_p51231519111711"><a name="zh-cn_topic_0000001613857522_p51231519111711"></a><a name="zh-cn_topic_0000001613857522_p51231519111711"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001613857522_p612301916172"><a name="zh-cn_topic_0000001613857522_p612301916172"></a><a name="zh-cn_topic_0000001613857522_p612301916172"></a>通信域内的device个数。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001613857522_row460577337"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001613857522_p412311914178"><a name="zh-cn_topic_0000001613857522_p412311914178"></a><a name="zh-cn_topic_0000001613857522_p412311914178"></a>devices</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001613857522_p01231219171717"><a name="zh-cn_topic_0000001613857522_p01231219171717"></a><a name="zh-cn_topic_0000001613857522_p01231219171717"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001613857522_p5123171961713"><a name="zh-cn_topic_0000001613857522_p5123171961713"></a><a name="zh-cn_topic_0000001613857522_p5123171961713"></a>通信域中的device列表，其值为device的逻辑ID，可通过<strong id="zh-cn_topic_0000001613857522_b1854925810171"><a name="zh-cn_topic_0000001613857522_b1854925810171"></a><a name="zh-cn_topic_0000001613857522_b1854925810171"></a>npu-smi info -m</strong>命令查询，HCCL按照devices中设置的顺序创建通信域。</p>
<p id="zh-cn_topic_0000001613857522_p3412162713354"><a name="zh-cn_topic_0000001613857522_p3412162713354"></a><a name="zh-cn_topic_0000001613857522_p3412162713354"></a>需要注意，输入的devices列表中不能包含重复的device ID。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001613857522_row156051072036"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001613857522_p141232019171715"><a name="zh-cn_topic_0000001613857522_p141232019171715"></a><a name="zh-cn_topic_0000001613857522_p141232019171715"></a>comms</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001613857522_p912413193178"><a name="zh-cn_topic_0000001613857522_p912413193178"></a><a name="zh-cn_topic_0000001613857522_p912413193178"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001613857522_p11241919151718"><a name="zh-cn_topic_0000001613857522_p11241919151718"></a><a name="zh-cn_topic_0000001613857522_p11241919151718"></a>生成的通信域句柄数组，其大小为：ndev * sizeof(HcclComm)。</p>
<p id="zh-cn_topic_0000001613857522_p11441511175312"><a name="zh-cn_topic_0000001613857522_p11441511175312"></a><a name="zh-cn_topic_0000001613857522_p11441511175312"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001613857522_section12554172517195"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000001613857522_section92549325194"></a>

-   该接口仅支持单机通信场景使用，不支持多机通信场景。
-   多线程调用通信操作API时（例如HcclAllReduce等），用户需确保不同线程中调用通信操作API的前后时间差不超过环境变量HCCL\_CONNECT\_TIMEOUT的时间，避免建链超时。
-   不支持一张卡同时调用多个通信操作API。

## 调用示例<a name="zh-cn_topic_0000001613857522_section204039211474"></a>

```c
uint32_t rankSize = 2;
int32_t devices[rankSize] = {0, 1};
HcclComm comms[rankSize];
// 初始化通信域
HcclCommInitAll(rankSize, devices, comms);
// 销毁通信域
for (uint32_t i = 0; i &lt; rankSize; i++) {
    HcclCommDestroy(comms[i]);
}
```

