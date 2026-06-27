# HcclCommSuspend<a name="ZH-CN_TOPIC_0000002519087947"></a>

> [!NOTE]说明
>本接口为预留接口，后续有可能变更，不支持开发者使用。

## 产品支持情况<a name="zh-cn_topic_0000002008554129_section10594071513"></a>

<a name="zh-cn_topic_0000002008554129_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002008554129_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002008554129_p1883113061818"><a name="zh-cn_topic_0000002008554129_p1883113061818"></a><a name="zh-cn_topic_0000002008554129_p1883113061818"></a><span id="zh-cn_topic_0000002008554129_ph20833205312295"><a name="zh-cn_topic_0000002008554129_ph20833205312295"></a><a name="zh-cn_topic_0000002008554129_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002008554129_p783113012187"><a name="zh-cn_topic_0000002008554129_p783113012187"></a><a name="zh-cn_topic_0000002008554129_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002008554129_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002008554129_p48327011813"><a name="zh-cn_topic_0000002008554129_p48327011813"></a><a name="zh-cn_topic_0000002008554129_p48327011813"></a><span id="zh-cn_topic_0000002008554129_ph583230201815"><a name="zh-cn_topic_0000002008554129_ph583230201815"></a><a name="zh-cn_topic_0000002008554129_ph583230201815"></a><term id="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002008554129_p7948163910184"><a name="zh-cn_topic_0000002008554129_p7948163910184"></a><a name="zh-cn_topic_0000002008554129_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002008554129_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002008554129_p14832120181815"><a name="zh-cn_topic_0000002008554129_p14832120181815"></a><a name="zh-cn_topic_0000002008554129_p14832120181815"></a><span id="zh-cn_topic_0000002008554129_ph1292674871116"><a name="zh-cn_topic_0000002008554129_ph1292674871116"></a><a name="zh-cn_topic_0000002008554129_ph1292674871116"></a><term id="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002008554129_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002008554129_p19948143911820"><a name="zh-cn_topic_0000002008554129_p19948143911820"></a><a name="zh-cn_topic_0000002008554129_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002008554129_section48254661"></a>

当片上内存UCE（uncorrect error）故障时（ACL接口返回ACL\_ERROR\_RT\_DEVICE\_MTE\_ERROR错误码），可调用本接口将通信域置为挂起状态。

使用此接口挂起集合通信域，无需退出Host侧进程，后续故障修复后，可调用[HcclCommResume](HcclCommResume.md#ZH-CN_TOPIC_0000002519007955)接口恢复通信域状态。

## 函数原型<a name="zh-cn_topic_0000002008554129_section57557412"></a>

```
HcclResult HcclCommSuspend(HcclComm comm)
```

## 参数说明<a name="zh-cn_topic_0000002008554129_section31638772"></a>

<a name="zh-cn_topic_0000002008554129_table66592127"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002008554129_row61502840"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002008554129_p15674164"><a name="zh-cn_topic_0000002008554129_p15674164"></a><a name="zh-cn_topic_0000002008554129_p15674164"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.03%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002008554129_p61647805"><a name="zh-cn_topic_0000002008554129_p61647805"></a><a name="zh-cn_topic_0000002008554129_p61647805"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.77%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002008554129_p27416314"><a name="zh-cn_topic_0000002008554129_p27416314"></a><a name="zh-cn_topic_0000002008554129_p27416314"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002008554129_row24345054"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002008554129_p25792371"><a name="zh-cn_topic_0000002008554129_p25792371"></a><a name="zh-cn_topic_0000002008554129_p25792371"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.03%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002008554129_p18316194201314"><a name="zh-cn_topic_0000002008554129_p18316194201314"></a><a name="zh-cn_topic_0000002008554129_p18316194201314"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.77%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002008554129_p25117316136"><a name="zh-cn_topic_0000002008554129_p25117316136"></a><a name="zh-cn_topic_0000002008554129_p25117316136"></a>需要将状态置为挂起的通信域。</p>
<p id="zh-cn_topic_0000002008554129_p2077615118500"><a name="zh-cn_topic_0000002008554129_p2077615118500"></a><a name="zh-cn_topic_0000002008554129_p2077615118500"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002008554129_section16313497"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002008554129_section12290877477"></a>

-   本接口需要与[HcclCommResume](HcclCommResume.md#ZH-CN_TOPIC_0000002519007955)接口配对使用。
-   本接口不能与[集合通信](zh-cn_topic_0000001683293554.md)、[点对点通信](zh-cn_topic_0000001683310714.md)的相关接口并发执行。

