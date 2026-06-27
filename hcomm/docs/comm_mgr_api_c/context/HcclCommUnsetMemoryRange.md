# HcclCommUnsetMemoryRange<a name="ZH-CN_TOPIC_0000002486848100"></a>

## 产品支持情况<a name="zh-cn_topic_0000002152626788_section10594071513"></a>

<a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p1883113061818"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p1883113061818"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p1883113061818"></a><span id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph20833205312295"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph20833205312295"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p783113012187"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p783113012187"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p48327011813"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p48327011813"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p48327011813"></a><span id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph583230201815"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph583230201815"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph583230201815"></a><term id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p7948163910184"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p7948163910184"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p14832120181815"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p14832120181815"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p14832120181815"></a><span id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph1292674871116"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph1292674871116"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_ph1292674871116"></a><term id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p19948143911820"><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p19948143911820"></a><a name="zh-cn_topic_0000002152626788_zh-cn_topic_0000002152624620_p19948143911820"></a>☓</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002152626788_section212645315215"></a>

该接口用于通知HCCL通信域取消使用预留的虚拟内存。

## 函数原型<a name="zh-cn_topic_0000002152626788_section13125135314218"></a>

```
HcclResult HcclCommUnsetMemoryRange(HcclComm comm, void *baseVirPtr)
```

## 参数说明<a name="zh-cn_topic_0000002152626788_section1812717539212"></a>

<a name="zh-cn_topic_0000002152626788_table18137135310213"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152626788_row1417285311217"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002152626788_p131726530216"><a name="zh-cn_topic_0000002152626788_p131726530216"></a><a name="zh-cn_topic_0000002152626788_p131726530216"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002152626788_p01721653524"><a name="zh-cn_topic_0000002152626788_p01721653524"></a><a name="zh-cn_topic_0000002152626788_p01721653524"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002152626788_p7172195319214"><a name="zh-cn_topic_0000002152626788_p7172195319214"></a><a name="zh-cn_topic_0000002152626788_p7172195319214"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152626788_row1117295311215"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152626788_p43711463187"><a name="zh-cn_topic_0000002152626788_p43711463187"></a><a name="zh-cn_topic_0000002152626788_p43711463187"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152626788_p7370176201810"><a name="zh-cn_topic_0000002152626788_p7370176201810"></a><a name="zh-cn_topic_0000002152626788_p7370176201810"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152626788_p204171552184111"><a name="zh-cn_topic_0000002152626788_p204171552184111"></a><a name="zh-cn_topic_0000002152626788_p204171552184111"></a>HCCL通信域，建议使用Server内最大的通信域，即覆盖最大卡数的通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152626788_row41722531724"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152626788_p3369968182"><a name="zh-cn_topic_0000002152626788_p3369968182"></a><a name="zh-cn_topic_0000002152626788_p3369968182"></a>baseVirPtr</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152626788_p93681763183"><a name="zh-cn_topic_0000002152626788_p93681763183"></a><a name="zh-cn_topic_0000002152626788_p93681763183"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152626788_p1336811671820"><a name="zh-cn_topic_0000002152626788_p1336811671820"></a><a name="zh-cn_topic_0000002152626788_p1336811671820"></a>预留的虚拟内存基地址。</p>
<p id="zh-cn_topic_0000002152626788_p1856125215910"><a name="zh-cn_topic_0000002152626788_p1856125215910"></a><a name="zh-cn_topic_0000002152626788_p1856125215910"></a>指定的基地址需已成功执行<a href="HcclCommSetMemoryRange.md#ZH-CN_TOPIC_0000002487008060">HcclCommSetMemoryRange</a>，否则会报错。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002152626788_section1513715531221"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002152626788_section86843302218"></a>

如果本虚拟地址空间内仍存在激活的内存，此接口会执行失败。

