# HcclSetConfig<a name="ZH-CN_TOPIC_0000002519087945"></a>

## 产品支持情况<a name="zh-cn_topic_0000001751331662_section10594071513"></a>

<a name="zh-cn_topic_0000001751331662_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001751331662_row20831180131817"><th class="cellrowborder" valign="top" width="55.76%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001751331662_p1883113061818"><a name="zh-cn_topic_0000001751331662_p1883113061818"></a><a name="zh-cn_topic_0000001751331662_p1883113061818"></a><span id="zh-cn_topic_0000001751331662_ph20833205312295"><a name="zh-cn_topic_0000001751331662_ph20833205312295"></a><a name="zh-cn_topic_0000001751331662_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="44.24%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001751331662_p783113012187"><a name="zh-cn_topic_0000001751331662_p783113012187"></a><a name="zh-cn_topic_0000001751331662_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001751331662_row220181016240"><td class="cellrowborder" valign="top" width="55.76%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001751331662_p48327011813"><a name="zh-cn_topic_0000001751331662_p48327011813"></a><a name="zh-cn_topic_0000001751331662_p48327011813"></a><span id="zh-cn_topic_0000001751331662_ph583230201815"><a name="zh-cn_topic_0000001751331662_ph583230201815"></a><a name="zh-cn_topic_0000001751331662_ph583230201815"></a><term id="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="44.24%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001751331662_p7948163910184"><a name="zh-cn_topic_0000001751331662_p7948163910184"></a><a name="zh-cn_topic_0000001751331662_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001751331662_row173226882415"><td class="cellrowborder" valign="top" width="55.76%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001751331662_p14832120181815"><a name="zh-cn_topic_0000001751331662_p14832120181815"></a><a name="zh-cn_topic_0000001751331662_p14832120181815"></a><span id="zh-cn_topic_0000001751331662_ph1292674871116"><a name="zh-cn_topic_0000001751331662_ph1292674871116"></a><a name="zh-cn_topic_0000001751331662_ph1292674871116"></a><term id="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001751331662_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="44.24%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001751331662_p19948143911820"><a name="zh-cn_topic_0000001751331662_p19948143911820"></a><a name="zh-cn_topic_0000001751331662_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001751331662_section31291646"></a>

进行集合通信相关配置，当前仅支持配置是否支持确定性计算。

在不开启确定性计算的场景下，多次执行的结果可能不同。这个差异的来源，一般是因为在算子实现中存在异步的多线程执行，会导致浮点数累加的顺序变化。当开启确定性计算后，算子在相同的硬件和输入下，多次执行将产生相同的输出。

默认情况下，无需开启确定性计算或保序功能，但当发现模型执行多次结果不同或者精度调优时，可以开启确定性计算或保序功能辅助进行调测调优，但开启后，算子执行时间会变慢，导致性能下降。

## 函数原型<a name="zh-cn_topic_0000001751331662_section18389930"></a>

```
HcclResult HcclSetConfig(HcclConfig config, HcclConfigValue configValue)
```

## 参数说明<a name="zh-cn_topic_0000001751331662_section13189358"></a>

<a name="zh-cn_topic_0000001751331662_table24749807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001751331662_row60665573"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001751331662_p14964341"><a name="zh-cn_topic_0000001751331662_p14964341"></a><a name="zh-cn_topic_0000001751331662_p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.24%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001751331662_p4152081"><a name="zh-cn_topic_0000001751331662_p4152081"></a><a name="zh-cn_topic_0000001751331662_p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.56%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001751331662_p774306"><a name="zh-cn_topic_0000001751331662_p774306"></a><a name="zh-cn_topic_0000001751331662_p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001751331662_row11144211"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001751331662_p7343193710565"><a name="zh-cn_topic_0000001751331662_p7343193710565"></a><a name="zh-cn_topic_0000001751331662_p7343193710565"></a>config</p>
</td>
<td class="cellrowborder" valign="top" width="17.24%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001751331662_p183421737145616"><a name="zh-cn_topic_0000001751331662_p183421737145616"></a><a name="zh-cn_topic_0000001751331662_p183421737145616"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.56%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001751331662_p19431944195710"><a name="zh-cn_topic_0000001751331662_p19431944195710"></a><a name="zh-cn_topic_0000001751331662_p19431944195710"></a>config中可配置的参数。</p>
<p id="zh-cn_topic_0000001751331662_p877193113519"><a name="zh-cn_topic_0000001751331662_p877193113519"></a><a name="zh-cn_topic_0000001751331662_p877193113519"></a><a href="HcclConfig.md#ZH-CN_TOPIC_0000002519007963">HcclConfig</a>类型，当前版本仅支持配置“HCCL_DETERMINISTIC”。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001751331662_row62284798"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001751331662_p2341143715563"><a name="zh-cn_topic_0000001751331662_p2341143715563"></a><a name="zh-cn_topic_0000001751331662_p2341143715563"></a>configValue</p>
</td>
<td class="cellrowborder" valign="top" width="17.24%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001751331662_p534013705613"><a name="zh-cn_topic_0000001751331662_p534013705613"></a><a name="zh-cn_topic_0000001751331662_p534013705613"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.56%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001751331662_p034310365353"><a name="zh-cn_topic_0000001751331662_p034310365353"></a><a name="zh-cn_topic_0000001751331662_p034310365353"></a>config中所配置参数的取值。</p>
<p id="zh-cn_topic_0000001751331662_p8493152920013"><a name="zh-cn_topic_0000001751331662_p8493152920013"></a><a name="zh-cn_topic_0000001751331662_p8493152920013"></a>请参见<a href="HcclConfigValue.md#ZH-CN_TOPIC_0000002487008066">HcclConfigValue</a>类型。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001751331662_section51595365"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000001751331662_section61705107"></a>

无

## 调用示例<a name="zh-cn_topic_0000001751331662_section204039211474"></a>

```c
// 开启确定性计算
HcclConfig config = HCCL_DETERMINISTIC;
union HcclConfigValue configValue;
configValue.value = 1;
HcclSetConfig(config, configValue);
```

