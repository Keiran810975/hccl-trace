# HcclCommActivateCommMemory<a name="ZH-CN_TOPIC_0000002519087951"></a>

## 产品支持情况<a name="zh-cn_topic_0000002187787605_section10594071513"></a>

<a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p1883113061818"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p1883113061818"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p1883113061818"></a><span id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph20833205312295"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph20833205312295"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p783113012187"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p783113012187"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p48327011813"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p48327011813"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p48327011813"></a><span id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph583230201815"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph583230201815"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph583230201815"></a><term id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p7948163910184"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p7948163910184"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p14832120181815"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p14832120181815"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p14832120181815"></a><span id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph1292674871116"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph1292674871116"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_ph1292674871116"></a><term id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p19948143911820"><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p19948143911820"></a><a name="zh-cn_topic_0000002187787605_zh-cn_topic_0000002152624620_p19948143911820"></a>☓</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002187787605_section212645315215"></a>

激活预留的虚拟内存，只有使用激活后的内存作为通信算子的输入、输出才可使能零拷贝功能。

## 函数原型<a name="zh-cn_topic_0000002187787605_section13125135314218"></a>

```
HcclResult HcclCommActivateCommMemory(HcclComm comm, void *virPtr, size_t size, size_t offset, aclrtDrvMemHandle handle, uint64_t flags)
```

## 参数说明<a name="zh-cn_topic_0000002187787605_section1812717539212"></a>

<a name="zh-cn_topic_0000002187787605_table18137135310213"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002187787605_row1417285311217"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002187787605_p131726530216"><a name="zh-cn_topic_0000002187787605_p131726530216"></a><a name="zh-cn_topic_0000002187787605_p131726530216"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.150000000000002%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002187787605_p01721653524"><a name="zh-cn_topic_0000002187787605_p01721653524"></a><a name="zh-cn_topic_0000002187787605_p01721653524"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.64999999999999%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002187787605_p7172195319214"><a name="zh-cn_topic_0000002187787605_p7172195319214"></a><a name="zh-cn_topic_0000002187787605_p7172195319214"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002187787605_row1117295311215"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p43711463187"><a name="zh-cn_topic_0000002187787605_p43711463187"></a><a name="zh-cn_topic_0000002187787605_p43711463187"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p17221218134319"><a name="zh-cn_topic_0000002187787605_p17221218134319"></a><a name="zh-cn_topic_0000002187787605_p17221218134319"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p937012611187"><a name="zh-cn_topic_0000002187787605_p937012611187"></a><a name="zh-cn_topic_0000002187787605_p937012611187"></a>HCCL通信域，建议使用Server内最大的通信域，即覆盖最大卡数的通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_row41722531724"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p3369968182"><a name="zh-cn_topic_0000002187787605_p3369968182"></a><a name="zh-cn_topic_0000002187787605_p3369968182"></a>virPtr</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p9565172510439"><a name="zh-cn_topic_0000002187787605_p9565172510439"></a><a name="zh-cn_topic_0000002187787605_p9565172510439"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p56748132385"><a name="zh-cn_topic_0000002187787605_p56748132385"></a><a name="zh-cn_topic_0000002187787605_p56748132385"></a>需要激活的虚拟内存地址，即用户调用aclrtMapMem接口进行物理内存与虚拟内存映射时，传入的待映射的虚拟内存地址。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_row1117220531028"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p1736719612184"><a name="zh-cn_topic_0000002187787605_p1736719612184"></a><a name="zh-cn_topic_0000002187787605_p1736719612184"></a>size</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p5366126171816"><a name="zh-cn_topic_0000002187787605_p5366126171816"></a><a name="zh-cn_topic_0000002187787605_p5366126171816"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p11366206131811"><a name="zh-cn_topic_0000002187787605_p11366206131811"></a><a name="zh-cn_topic_0000002187787605_p11366206131811"></a>需要激活的内存大小，单位：Byte。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_row18172165315213"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p113636611186"><a name="zh-cn_topic_0000002187787605_p113636611186"></a><a name="zh-cn_topic_0000002187787605_p113636611186"></a>offset</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p11362126131815"><a name="zh-cn_topic_0000002187787605_p11362126131815"></a><a name="zh-cn_topic_0000002187787605_p11362126131815"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p16108191917498"><a name="zh-cn_topic_0000002187787605_p16108191917498"></a><a name="zh-cn_topic_0000002187787605_p16108191917498"></a>预留字段。</p>
<p id="zh-cn_topic_0000002187787605_p16292191517406"><a name="zh-cn_topic_0000002187787605_p16292191517406"></a><a name="zh-cn_topic_0000002187787605_p16292191517406"></a>当前仅支持配置为“0”。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_row16172165312215"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p5361965187"><a name="zh-cn_topic_0000002187787605_p5361965187"></a><a name="zh-cn_topic_0000002187787605_p5361965187"></a>handle</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p1360469188"><a name="zh-cn_topic_0000002187787605_p1360469188"></a><a name="zh-cn_topic_0000002187787605_p1360469188"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p10360106131814"><a name="zh-cn_topic_0000002187787605_p10360106131814"></a><a name="zh-cn_topic_0000002187787605_p10360106131814"></a>申请的物理内存信息handle，即用户调用aclrtMallocPhysical接口申请的Device物理内存信息handle。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002187787605_row6172135311215"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002187787605_p9359768183"><a name="zh-cn_topic_0000002187787605_p9359768183"></a><a name="zh-cn_topic_0000002187787605_p9359768183"></a>flags</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002187787605_p93581968188"><a name="zh-cn_topic_0000002187787605_p93581968188"></a><a name="zh-cn_topic_0000002187787605_p93581968188"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002187787605_p132538101431"><a name="zh-cn_topic_0000002187787605_p132538101431"></a><a name="zh-cn_topic_0000002187787605_p132538101431"></a>预留字段。</p>
<p id="zh-cn_topic_0000002187787605_p125311024313"><a name="zh-cn_topic_0000002187787605_p125311024313"></a><a name="zh-cn_topic_0000002187787605_p125311024313"></a>当前仅支持配置为“0”。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002187787605_section1513715531221"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002187787605_section86843302218"></a>

-   待激活的虚拟内存地址必须在[HcclCommSetMemoryRange](HcclCommSetMemoryRange.md#ZH-CN_TOPIC_0000002487008060)设置的地址范围内。
-   该虚拟内存地址不能与已经激活的虚拟内存地址有重叠、交叠。

