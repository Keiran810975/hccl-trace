# HcclCommDeactivateCommMemory<a name="ZH-CN_TOPIC_0000002519007959"></a>

## 产品支持情况<a name="zh-cn_topic_0000002152468756_section10594071513"></a>

<a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p1883113061818"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p1883113061818"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p1883113061818"></a><span id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph20833205312295"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph20833205312295"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p783113012187"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p783113012187"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p48327011813"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p48327011813"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p48327011813"></a><span id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph583230201815"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph583230201815"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph583230201815"></a><term id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p7948163910184"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p7948163910184"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p14832120181815"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p14832120181815"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p14832120181815"></a><span id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph1292674871116"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph1292674871116"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_ph1292674871116"></a><term id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p19948143911820"><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p19948143911820"></a><a name="zh-cn_topic_0000002152468756_zh-cn_topic_0000002152624620_p19948143911820"></a>☓</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002152468756_section212645315215"></a>

将已经激活的虚拟内存反激活，反激活后如果再使用该地址进行集合通信，将不会使能零拷贝功能。

## 函数原型<a name="zh-cn_topic_0000002152468756_section13125135314218"></a>

```
HcclResult HcclCommDeactivateCommMemory(HcclComm comm, void *virPtr)
```

## 参数说明<a name="zh-cn_topic_0000002152468756_section1812717539212"></a>

<a name="zh-cn_topic_0000002152468756_table18137135310213"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152468756_row1417285311217"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002152468756_p131726530216"><a name="zh-cn_topic_0000002152468756_p131726530216"></a><a name="zh-cn_topic_0000002152468756_p131726530216"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002152468756_p01721653524"><a name="zh-cn_topic_0000002152468756_p01721653524"></a><a name="zh-cn_topic_0000002152468756_p01721653524"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002152468756_p7172195319214"><a name="zh-cn_topic_0000002152468756_p7172195319214"></a><a name="zh-cn_topic_0000002152468756_p7172195319214"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152468756_row1117295311215"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152468756_p43711463187"><a name="zh-cn_topic_0000002152468756_p43711463187"></a><a name="zh-cn_topic_0000002152468756_p43711463187"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152468756_p17221218134319"><a name="zh-cn_topic_0000002152468756_p17221218134319"></a><a name="zh-cn_topic_0000002152468756_p17221218134319"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152468756_p937012611187"><a name="zh-cn_topic_0000002152468756_p937012611187"></a><a name="zh-cn_topic_0000002152468756_p937012611187"></a>HCCL通信域，建议使用Server内最大的通信域，即覆盖最大卡数的通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152468756_row41722531724"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152468756_p660991213482"><a name="zh-cn_topic_0000002152468756_p660991213482"></a><a name="zh-cn_topic_0000002152468756_p660991213482"></a>virPtr</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152468756_p9565172510439"><a name="zh-cn_topic_0000002152468756_p9565172510439"></a><a name="zh-cn_topic_0000002152468756_p9565172510439"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152468756_p148451725175611"><a name="zh-cn_topic_0000002152468756_p148451725175611"></a><a name="zh-cn_topic_0000002152468756_p148451725175611"></a>需要反激活的虚拟地址的起始地址，即<a href="HcclCommActivateCommMemory.md#ZH-CN_TOPIC_0000002519087951">HcclCommActivateCommMemory</a>接口“virPtr”参数指定的虚拟内存地址。</p>
<p id="zh-cn_topic_0000002152468756_p39451525145712"><a name="zh-cn_topic_0000002152468756_p39451525145712"></a><a name="zh-cn_topic_0000002152468756_p39451525145712"></a>需要注意，指定的虚拟内存必须是已成功激活的内存，且仅支持整个地址块反激活。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002152468756_section1513715531221"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002152468756_section86843302218"></a>

无

