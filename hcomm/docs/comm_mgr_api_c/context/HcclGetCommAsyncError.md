# HcclGetCommAsyncError<a name="ZH-CN_TOPIC_0000002486848102"></a>

## 产品支持情况<a name="zh-cn_topic_0000001657705734_section10594071513"></a>

<a name="zh-cn_topic_0000001657705734_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001657705734_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001657705734_p1883113061818"><a name="zh-cn_topic_0000001657705734_p1883113061818"></a><a name="zh-cn_topic_0000001657705734_p1883113061818"></a><span id="zh-cn_topic_0000001657705734_ph20833205312295"><a name="zh-cn_topic_0000001657705734_ph20833205312295"></a><a name="zh-cn_topic_0000001657705734_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001657705734_p783113012187"><a name="zh-cn_topic_0000001657705734_p783113012187"></a><a name="zh-cn_topic_0000001657705734_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001657705734_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001657705734_p48327011813"><a name="zh-cn_topic_0000001657705734_p48327011813"></a><a name="zh-cn_topic_0000001657705734_p48327011813"></a><span id="zh-cn_topic_0000001657705734_ph583230201815"><a name="zh-cn_topic_0000001657705734_ph583230201815"></a><a name="zh-cn_topic_0000001657705734_ph583230201815"></a><term id="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001657705734_p7948163910184"><a name="zh-cn_topic_0000001657705734_p7948163910184"></a><a name="zh-cn_topic_0000001657705734_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001657705734_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001657705734_p14832120181815"><a name="zh-cn_topic_0000001657705734_p14832120181815"></a><a name="zh-cn_topic_0000001657705734_p14832120181815"></a><span id="zh-cn_topic_0000001657705734_ph1292674871116"><a name="zh-cn_topic_0000001657705734_ph1292674871116"></a><a name="zh-cn_topic_0000001657705734_ph1292674871116"></a><term id="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001657705734_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001657705734_p19948143911820"><a name="zh-cn_topic_0000001657705734_p19948143911820"></a><a name="zh-cn_topic_0000001657705734_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001657705734_section37208511199"></a>

当集群信息中存在Device网口通信链路不稳定、出现网络拥塞的情况时，Device日志中会存在“error cqe”的打印，我们称这种错误为“RDMA ERROR CQE”错误。

当前版本，此接口仅支持查询通信域内是否存在“RDMA ERROR CQE”的错误。

> [!NOTE]说明
>此接口为同步接口，即接口调用后需要等待返回结果。

## 函数原型<a name="zh-cn_topic_0000001657705734_section35919731916"></a>

```
HcclResult HcclGetCommAsyncError(HcclComm comm, HcclResult *asyncError)
```

## 参数说明<a name="zh-cn_topic_0000001657705734_section2586134311199"></a>

<a name="zh-cn_topic_0000001657705734_table0576473316"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001657705734_row1060511716320"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001657705734_p146051071139"><a name="zh-cn_topic_0000001657705734_p146051071139"></a><a name="zh-cn_topic_0000001657705734_p146051071139"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001657705734_p1160527939"><a name="zh-cn_topic_0000001657705734_p1160527939"></a><a name="zh-cn_topic_0000001657705734_p1160527939"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001657705734_p86058714320"><a name="zh-cn_topic_0000001657705734_p86058714320"></a><a name="zh-cn_topic_0000001657705734_p86058714320"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001657705734_row166054719318"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001657705734_p111231019101719"><a name="zh-cn_topic_0000001657705734_p111231019101719"></a><a name="zh-cn_topic_0000001657705734_p111231019101719"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001657705734_p51231519111711"><a name="zh-cn_topic_0000001657705734_p51231519111711"></a><a name="zh-cn_topic_0000001657705734_p51231519111711"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001657705734_p72871361588"><a name="zh-cn_topic_0000001657705734_p72871361588"></a><a name="zh-cn_topic_0000001657705734_p72871361588"></a>需要查询是否存在错误信息的通信域。</p>
<p id="zh-cn_topic_0000001657705734_p85221504584"><a name="zh-cn_topic_0000001657705734_p85221504584"></a><a name="zh-cn_topic_0000001657705734_p85221504584"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001657705734_row146051372315"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001657705734_p512431910174"><a name="zh-cn_topic_0000001657705734_p512431910174"></a><a name="zh-cn_topic_0000001657705734_p512431910174"></a>asyncError</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001657705734_p151241419131716"><a name="zh-cn_topic_0000001657705734_p151241419131716"></a><a name="zh-cn_topic_0000001657705734_p151241419131716"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><a name="zh-cn_topic_0000001657705734_ul1863016513418"></a><a name="zh-cn_topic_0000001657705734_ul1863016513418"></a><ul id="zh-cn_topic_0000001657705734_ul1863016513418"><li>0：表示该通信域内无错误发生。</li><li>21：表示该通信域内发生了“RDMA ERROR CQE”的错误。</li></ul>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001657705734_section12554172517195"></a>

参见[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)类型，当前版本仅返回HCCL\_E\_REMOTE错误类型。

## 约束说明<a name="zh-cn_topic_0000001657705734_section92549325194"></a>

-   建立通信域后，才可调用此接口。
-   通信域销毁后，不可调用此接口。

