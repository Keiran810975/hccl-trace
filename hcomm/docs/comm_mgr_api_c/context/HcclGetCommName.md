# HcclGetCommName<a name="ZH-CN_TOPIC_0000002487008056"></a>

## 产品支持情况<a name="zh-cn_topic_0000001798290361_section10594071513"></a>

<a name="zh-cn_topic_0000001798290361_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001798290361_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001798290361_p1883113061818"><a name="zh-cn_topic_0000001798290361_p1883113061818"></a><a name="zh-cn_topic_0000001798290361_p1883113061818"></a><span id="zh-cn_topic_0000001798290361_ph20833205312295"><a name="zh-cn_topic_0000001798290361_ph20833205312295"></a><a name="zh-cn_topic_0000001798290361_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001798290361_p783113012187"><a name="zh-cn_topic_0000001798290361_p783113012187"></a><a name="zh-cn_topic_0000001798290361_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001798290361_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001798290361_p48327011813"><a name="zh-cn_topic_0000001798290361_p48327011813"></a><a name="zh-cn_topic_0000001798290361_p48327011813"></a><span id="zh-cn_topic_0000001798290361_ph583230201815"><a name="zh-cn_topic_0000001798290361_ph583230201815"></a><a name="zh-cn_topic_0000001798290361_ph583230201815"></a><term id="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001798290361_p7948163910184"><a name="zh-cn_topic_0000001798290361_p7948163910184"></a><a name="zh-cn_topic_0000001798290361_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001798290361_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001798290361_p14832120181815"><a name="zh-cn_topic_0000001798290361_p14832120181815"></a><a name="zh-cn_topic_0000001798290361_p14832120181815"></a><span id="zh-cn_topic_0000001798290361_ph1292674871116"><a name="zh-cn_topic_0000001798290361_ph1292674871116"></a><a name="zh-cn_topic_0000001798290361_ph1292674871116"></a><term id="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001798290361_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001798290361_p19948143911820"><a name="zh-cn_topic_0000001798290361_p19948143911820"></a><a name="zh-cn_topic_0000001798290361_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001798290361_section31291646"></a>

获取当前集合通信操作所在的通信域的名称。

## 函数原型<a name="zh-cn_topic_0000001798290361_section18389930"></a>

```
HcclResult HcclGetCommName(HcclComm comm, char* commName)
```

## 参数说明<a name="zh-cn_topic_0000001798290361_section13189358"></a>

<a name="zh-cn_topic_0000001798290361_table24749807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001798290361_row60665573"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001798290361_p14964341"><a name="zh-cn_topic_0000001798290361_p14964341"></a><a name="zh-cn_topic_0000001798290361_p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001798290361_p4152081"><a name="zh-cn_topic_0000001798290361_p4152081"></a><a name="zh-cn_topic_0000001798290361_p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001798290361_p774306"><a name="zh-cn_topic_0000001798290361_p774306"></a><a name="zh-cn_topic_0000001798290361_p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001798290361_row11144211"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001798290361_p12413174715201"><a name="zh-cn_topic_0000001798290361_p12413174715201"></a><a name="zh-cn_topic_0000001798290361_p12413174715201"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001798290361_p183421737145616"><a name="zh-cn_topic_0000001798290361_p183421737145616"></a><a name="zh-cn_topic_0000001798290361_p183421737145616"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001798290361_p66572856"><a name="zh-cn_topic_0000001798290361_p66572856"></a><a name="zh-cn_topic_0000001798290361_p66572856"></a>集合通信操作所在的通信域。</p>
<p id="zh-cn_topic_0000001798290361_p677348172020"><a name="zh-cn_topic_0000001798290361_p677348172020"></a><a name="zh-cn_topic_0000001798290361_p677348172020"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001798290361_row62284798"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001798290361_p2341143715563"><a name="zh-cn_topic_0000001798290361_p2341143715563"></a><a name="zh-cn_topic_0000001798290361_p2341143715563"></a>commName</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001798290361_p534013705613"><a name="zh-cn_topic_0000001798290361_p534013705613"></a><a name="zh-cn_topic_0000001798290361_p534013705613"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001798290361_p1133873712563"><a name="zh-cn_topic_0000001798290361_p1133873712563"></a><a name="zh-cn_topic_0000001798290361_p1133873712563"></a>获取到的通信域名称。</p>
<p id="zh-cn_topic_0000001798290361_p1321014424199"><a name="zh-cn_topic_0000001798290361_p1321014424199"></a><a name="zh-cn_topic_0000001798290361_p1321014424199"></a>char*类型，最大长度支持128。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001798290361_section51595365"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HcclSuccess，其他失败。

## 约束说明<a name="zh-cn_topic_0000001798290361_section764575019568"></a>

无

## 调用示例<a name="zh-cn_topic_0000001798290361_section10236329223"></a>

```c
// 初始化通信域
HcclComm comm;
// 查询通信域名称
string commName;
HcclGetCommName(comm, &commName);
```

