# HcclCommResume<a name="ZH-CN_TOPIC_0000002519007955"></a>

> [!NOTE]说明
>本接口为预留接口，后续有可能变更，不支持开发者使用。

## 产品支持情况<a name="zh-cn_topic_0000001972113570_section10594071513"></a>

<a name="zh-cn_topic_0000001972113570_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001972113570_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001972113570_p1883113061818"><a name="zh-cn_topic_0000001972113570_p1883113061818"></a><a name="zh-cn_topic_0000001972113570_p1883113061818"></a><span id="zh-cn_topic_0000001972113570_ph20833205312295"><a name="zh-cn_topic_0000001972113570_ph20833205312295"></a><a name="zh-cn_topic_0000001972113570_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001972113570_p783113012187"><a name="zh-cn_topic_0000001972113570_p783113012187"></a><a name="zh-cn_topic_0000001972113570_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001972113570_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001972113570_p48327011813"><a name="zh-cn_topic_0000001972113570_p48327011813"></a><a name="zh-cn_topic_0000001972113570_p48327011813"></a><span id="zh-cn_topic_0000001972113570_ph583230201815"><a name="zh-cn_topic_0000001972113570_ph583230201815"></a><a name="zh-cn_topic_0000001972113570_ph583230201815"></a><term id="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001972113570_p7948163910184"><a name="zh-cn_topic_0000001972113570_p7948163910184"></a><a name="zh-cn_topic_0000001972113570_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001972113570_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001972113570_p14832120181815"><a name="zh-cn_topic_0000001972113570_p14832120181815"></a><a name="zh-cn_topic_0000001972113570_p14832120181815"></a><span id="zh-cn_topic_0000001972113570_ph1292674871116"><a name="zh-cn_topic_0000001972113570_ph1292674871116"></a><a name="zh-cn_topic_0000001972113570_ph1292674871116"></a><term id="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001972113570_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001972113570_p19948143911820"><a name="zh-cn_topic_0000001972113570_p19948143911820"></a><a name="zh-cn_topic_0000001972113570_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001972113570_section48254661"></a>

本接口用于恢复集合通信域的状态。

若开发者调用[HcclCommSuspend](HcclCommSuspend.md#ZH-CN_TOPIC_0000002519087947)接口或者acl提供的aclrtDeviceTaskAbort接口挂起了通信域，故障恢复后，需要调用本接口将通信域恢复为正常状态。

## 函数原型<a name="zh-cn_topic_0000001972113570_section57557412"></a>

```
HcclResult HcclCommResume(HcclComm comm)
```

## 参数说明<a name="zh-cn_topic_0000001972113570_section31638772"></a>

<a name="zh-cn_topic_0000001972113570_table66592127"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001972113570_row61502840"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001972113570_p15674164"><a name="zh-cn_topic_0000001972113570_p15674164"></a><a name="zh-cn_topic_0000001972113570_p15674164"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.03%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001972113570_p61647805"><a name="zh-cn_topic_0000001972113570_p61647805"></a><a name="zh-cn_topic_0000001972113570_p61647805"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.77%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001972113570_p27416314"><a name="zh-cn_topic_0000001972113570_p27416314"></a><a name="zh-cn_topic_0000001972113570_p27416314"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001972113570_row24345054"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001972113570_p25792371"><a name="zh-cn_topic_0000001972113570_p25792371"></a><a name="zh-cn_topic_0000001972113570_p25792371"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.03%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001972113570_p8807292"><a name="zh-cn_topic_0000001972113570_p8807292"></a><a name="zh-cn_topic_0000001972113570_p8807292"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.77%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001972113570_p7967184982012"><a name="zh-cn_topic_0000001972113570_p7967184982012"></a><a name="zh-cn_topic_0000001972113570_p7967184982012"></a>需要从挂起状态恢复为正常状态的通信域。</p>
<p id="zh-cn_topic_0000001972113570_p2077615118500"><a name="zh-cn_topic_0000001972113570_p2077615118500"></a><a name="zh-cn_topic_0000001972113570_p2077615118500"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001972113570_section16313497"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000001972113570_section61705107"></a>

-   调用本接口前，需要调用acl提供的aclrtDeviceTaskAbort接口停止本Device上的任务执行。
-   调用本接口恢复集合域通信前，需要进行一次集群同步操作。

