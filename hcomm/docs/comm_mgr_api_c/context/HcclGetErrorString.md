# HcclGetErrorString<a name="ZH-CN_TOPIC_0000002519087953"></a>

## 产品支持情况<a name="zh-cn_topic_0000001729193541_section10594071513"></a>

<a name="zh-cn_topic_0000001729193541_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001729193541_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001729193541_p1883113061818"><a name="zh-cn_topic_0000001729193541_p1883113061818"></a><a name="zh-cn_topic_0000001729193541_p1883113061818"></a><span id="zh-cn_topic_0000001729193541_ph20833205312295"><a name="zh-cn_topic_0000001729193541_ph20833205312295"></a><a name="zh-cn_topic_0000001729193541_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001729193541_p783113012187"><a name="zh-cn_topic_0000001729193541_p783113012187"></a><a name="zh-cn_topic_0000001729193541_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001729193541_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001729193541_p48327011813"><a name="zh-cn_topic_0000001729193541_p48327011813"></a><a name="zh-cn_topic_0000001729193541_p48327011813"></a><span id="zh-cn_topic_0000001729193541_ph583230201815"><a name="zh-cn_topic_0000001729193541_ph583230201815"></a><a name="zh-cn_topic_0000001729193541_ph583230201815"></a><term id="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001729193541_p7948163910184"><a name="zh-cn_topic_0000001729193541_p7948163910184"></a><a name="zh-cn_topic_0000001729193541_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001729193541_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001729193541_p14832120181815"><a name="zh-cn_topic_0000001729193541_p14832120181815"></a><a name="zh-cn_topic_0000001729193541_p14832120181815"></a><span id="zh-cn_topic_0000001729193541_ph1292674871116"><a name="zh-cn_topic_0000001729193541_ph1292674871116"></a><a name="zh-cn_topic_0000001729193541_ph1292674871116"></a><term id="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001729193541_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001729193541_p19948143911820"><a name="zh-cn_topic_0000001729193541_p19948143911820"></a><a name="zh-cn_topic_0000001729193541_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001729193541_section37208511199"></a>

解析HcclResult类型的错误码。

## 函数原型<a name="zh-cn_topic_0000001729193541_section35919731916"></a>

```
const char* HcclGetErrorString (HcclResult code)
```

## 参数说明<a name="zh-cn_topic_0000001729193541_section2586134311199"></a>

<a name="zh-cn_topic_0000001729193541_table0576473316"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001729193541_row1060511716320"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001729193541_p146051071139"><a name="zh-cn_topic_0000001729193541_p146051071139"></a><a name="zh-cn_topic_0000001729193541_p146051071139"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001729193541_p1160527939"><a name="zh-cn_topic_0000001729193541_p1160527939"></a><a name="zh-cn_topic_0000001729193541_p1160527939"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001729193541_p86058714320"><a name="zh-cn_topic_0000001729193541_p86058714320"></a><a name="zh-cn_topic_0000001729193541_p86058714320"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001729193541_row166054719318"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001729193541_p111231019101719"><a name="zh-cn_topic_0000001729193541_p111231019101719"></a><a name="zh-cn_topic_0000001729193541_p111231019101719"></a>code</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001729193541_p51231519111711"><a name="zh-cn_topic_0000001729193541_p51231519111711"></a><a name="zh-cn_topic_0000001729193541_p51231519111711"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001729193541_p612301916172"><a name="zh-cn_topic_0000001729193541_p612301916172"></a><a name="zh-cn_topic_0000001729193541_p612301916172"></a>需要解析的错误码，<a href="HcclResult.md#ZH-CN_TOPIC_0000002487008064">HcclResult</a>类型。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001729193541_section12554172517195"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)类型错误码的解析结果。

## 约束说明<a name="zh-cn_topic_0000001729193541_section92549325194"></a>

无。

