# HcclCommSetMemoryRange<a name="ZH-CN_TOPIC_0000002487008060"></a>

## 产品支持情况<a name="zh-cn_topic_0000002152624620_section10594071513"></a>

<a name="zh-cn_topic_0000002152624620_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152624620_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002152624620_p1883113061818"><a name="zh-cn_topic_0000002152624620_p1883113061818"></a><a name="zh-cn_topic_0000002152624620_p1883113061818"></a><span id="zh-cn_topic_0000002152624620_ph20833205312295"><a name="zh-cn_topic_0000002152624620_ph20833205312295"></a><a name="zh-cn_topic_0000002152624620_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002152624620_p783113012187"><a name="zh-cn_topic_0000002152624620_p783113012187"></a><a name="zh-cn_topic_0000002152624620_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152624620_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152624620_p48327011813"><a name="zh-cn_topic_0000002152624620_p48327011813"></a><a name="zh-cn_topic_0000002152624620_p48327011813"></a><span id="zh-cn_topic_0000002152624620_ph583230201815"><a name="zh-cn_topic_0000002152624620_ph583230201815"></a><a name="zh-cn_topic_0000002152624620_ph583230201815"></a><term id="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152624620_p7948163910184"><a name="zh-cn_topic_0000002152624620_p7948163910184"></a><a name="zh-cn_topic_0000002152624620_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152624620_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002152624620_p14832120181815"><a name="zh-cn_topic_0000002152624620_p14832120181815"></a><a name="zh-cn_topic_0000002152624620_p14832120181815"></a><span id="zh-cn_topic_0000002152624620_ph1292674871116"><a name="zh-cn_topic_0000002152624620_ph1292674871116"></a><a name="zh-cn_topic_0000002152624620_ph1292674871116"></a><term id="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002152624620_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002152624620_p19948143911820"><a name="zh-cn_topic_0000002152624620_p19948143911820"></a><a name="zh-cn_topic_0000002152624620_p19948143911820"></a>☓</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002152624620_section212645315215"></a>

用户通过aclrtReserveMemAddress接口成功申请虚拟内存后，可调用此接口通知HCCL预留的虚拟内存地址。调用此接口后，该虚拟内存对当前进程中的所有通信域可见。

## 函数原型<a name="zh-cn_topic_0000002152624620_section13125135314218"></a>

```
HcclResult HcclCommSetMemoryRange(HcclComm comm, void *baseVirPtr, size_t size, size_t alignment, uint64_t flags)
```

## 参数说明<a name="zh-cn_topic_0000002152624620_section1812717539212"></a>

<a name="zh-cn_topic_0000002152624620_table18137135310213"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002152624620_row1417285311217"><th class="cellrowborder" valign="top" width="17.88%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002152624620_p131726530216"><a name="zh-cn_topic_0000002152624620_p131726530216"></a><a name="zh-cn_topic_0000002152624620_p131726530216"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.810000000000002%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002152624620_p01721653524"><a name="zh-cn_topic_0000002152624620_p01721653524"></a><a name="zh-cn_topic_0000002152624620_p01721653524"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="64.31%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002152624620_p7172195319214"><a name="zh-cn_topic_0000002152624620_p7172195319214"></a><a name="zh-cn_topic_0000002152624620_p7172195319214"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002152624620_row1117295311215"><td class="cellrowborder" valign="top" width="17.88%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152624620_p2840827182218"><a name="zh-cn_topic_0000002152624620_p2840827182218"></a><a name="zh-cn_topic_0000002152624620_p2840827182218"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.810000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152624620_p7370176201810"><a name="zh-cn_topic_0000002152624620_p7370176201810"></a><a name="zh-cn_topic_0000002152624620_p7370176201810"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="64.31%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152624620_p937012611187"><a name="zh-cn_topic_0000002152624620_p937012611187"></a><a name="zh-cn_topic_0000002152624620_p937012611187"></a>HCCL通信域，建议使用Server内最大的通信域，即覆盖最大卡数的通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152624620_row41722531724"><td class="cellrowborder" valign="top" width="17.88%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152624620_p157572692217"><a name="zh-cn_topic_0000002152624620_p157572692217"></a><a name="zh-cn_topic_0000002152624620_p157572692217"></a>baseVirPtr</p>
</td>
<td class="cellrowborder" valign="top" width="17.810000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152624620_p93681763183"><a name="zh-cn_topic_0000002152624620_p93681763183"></a><a name="zh-cn_topic_0000002152624620_p93681763183"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="64.31%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152624620_p1336811671820"><a name="zh-cn_topic_0000002152624620_p1336811671820"></a><a name="zh-cn_topic_0000002152624620_p1336811671820"></a>需要预留的虚拟内存基地址，即aclrtReserveMemAddress接口输出的虚拟内存地址。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152624620_row1117220531028"><td class="cellrowborder" valign="top" width="17.88%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152624620_p1736719612184"><a name="zh-cn_topic_0000002152624620_p1736719612184"></a><a name="zh-cn_topic_0000002152624620_p1736719612184"></a>size</p>
</td>
<td class="cellrowborder" valign="top" width="17.810000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152624620_p5366126171816"><a name="zh-cn_topic_0000002152624620_p5366126171816"></a><a name="zh-cn_topic_0000002152624620_p5366126171816"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="64.31%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152624620_p11366206131811"><a name="zh-cn_topic_0000002152624620_p11366206131811"></a><a name="zh-cn_topic_0000002152624620_p11366206131811"></a>虚拟内存的大小，单位：Byte。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152624620_row18172165315213"><td class="cellrowborder" valign="top" width="17.88%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152624620_p113636611186"><a name="zh-cn_topic_0000002152624620_p113636611186"></a><a name="zh-cn_topic_0000002152624620_p113636611186"></a>alignment</p>
</td>
<td class="cellrowborder" valign="top" width="17.810000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152624620_p11362126131815"><a name="zh-cn_topic_0000002152624620_p11362126131815"></a><a name="zh-cn_topic_0000002152624620_p11362126131815"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="64.31%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152624620_p26531952154018"><a name="zh-cn_topic_0000002152624620_p26531952154018"></a><a name="zh-cn_topic_0000002152624620_p26531952154018"></a>预留字段。</p>
<p id="zh-cn_topic_0000002152624620_p336210613187"><a name="zh-cn_topic_0000002152624620_p336210613187"></a><a name="zh-cn_topic_0000002152624620_p336210613187"></a>当前仅支持配置为“0”。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002152624620_row16172165312215"><td class="cellrowborder" valign="top" width="17.88%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002152624620_p5361965187"><a name="zh-cn_topic_0000002152624620_p5361965187"></a><a name="zh-cn_topic_0000002152624620_p5361965187"></a>flags</p>
</td>
<td class="cellrowborder" valign="top" width="17.810000000000002%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002152624620_p1360469188"><a name="zh-cn_topic_0000002152624620_p1360469188"></a><a name="zh-cn_topic_0000002152624620_p1360469188"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="64.31%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002152624620_p138687570103"><a name="zh-cn_topic_0000002152624620_p138687570103"></a><a name="zh-cn_topic_0000002152624620_p138687570103"></a>预留字段。</p>
<p id="zh-cn_topic_0000002152624620_p154071034415"><a name="zh-cn_topic_0000002152624620_p154071034415"></a><a name="zh-cn_topic_0000002152624620_p154071034415"></a><span>当前仅支持配置为“0”。</span></p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002152624620_section1513715531221"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002152624620_section86843302218"></a>

-   该接口在通信域内首次被调用时会进行建链操作，因此用户首次调用该接口时需确保通信域内所有进程均调用该接口，且调用时刻相同，避免建链超时。后续再调用该接口时，无此约束。
-   该接口仅支持在范围是单Server的通信域内调用，否则会报错。
-   多次调用该接口时，输入的内存地址不能重复或存在区间交叠。
-   其他约束请参见[通用约束](使用前必读.md#zh-cn_topic_0000002152466612_section153114015141)。

