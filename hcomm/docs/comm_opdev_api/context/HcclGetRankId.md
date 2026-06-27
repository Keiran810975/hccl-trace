# HcclGetRankId<a name="ZH-CN_TOPIC_0000002507941288"></a>

## 产品支持情况<a name="section10594071513"></a>

<a name="zh-cn_topic_0000001264921398_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001264921398_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="p1883113061818"><a name="p1883113061818"></a><a name="p1883113061818"></a><span id="ph20833205312295"><a name="ph20833205312295"></a><a name="ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001264921398_p783113012187"><a name="zh-cn_topic_0000001264921398_p783113012187"></a><a name="zh-cn_topic_0000001264921398_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001264921398_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="p48327011813"><a name="p48327011813"></a><a name="p48327011813"></a><span id="ph583230201815"><a name="ph583230201815"></a><a name="ph583230201815"></a><term id="zh-cn_topic_0000002534508309_term1253731311225"><a name="zh-cn_topic_0000002534508309_term1253731311225"></a><a name="zh-cn_topic_0000002534508309_term1253731311225"></a>Atlas A3 训练系列产品</term>/<term id="zh-cn_topic_0000002534508309_term131434243115"><a name="zh-cn_topic_0000002534508309_term131434243115"></a><a name="zh-cn_topic_0000002534508309_term131434243115"></a>Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001264921398_p7948163910184"><a name="zh-cn_topic_0000001264921398_p7948163910184"></a><a name="zh-cn_topic_0000001264921398_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001264921398_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="p14832120181815"><a name="p14832120181815"></a><a name="p14832120181815"></a><span id="ph1292674871116"><a name="ph1292674871116"></a><a name="ph1292674871116"></a><term id="zh-cn_topic_0000002534508309_term11962195213215"><a name="zh-cn_topic_0000002534508309_term11962195213215"></a><a name="zh-cn_topic_0000002534508309_term11962195213215"></a>Atlas A2 训练系列产品</term>/<term id="zh-cn_topic_0000002534508309_term184716139811"><a name="zh-cn_topic_0000002534508309_term184716139811"></a><a name="zh-cn_topic_0000002534508309_term184716139811"></a>Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001264921398_p19948143911820"><a name="zh-cn_topic_0000001264921398_p19948143911820"></a><a name="zh-cn_topic_0000001264921398_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

## 功能说明<a name="section31291646"></a>

获取Device在指定通信域中对应的rank序号。

## 函数原型<a name="section18389930"></a>

```
HcclResult HcclGetRankId(HcclComm comm, uint32_t *rank)
```

## 参数说明<a name="section13189358"></a>

<a name="table24749807"></a>
<table><thead align="left"><tr id="row60665573"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p14964341"><a name="p14964341"></a><a name="p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.06%" id="mcps1.1.4.1.2"><p id="p4152081"><a name="p4152081"></a><a name="p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.739999999999995%" id="mcps1.1.4.1.3"><p id="p774306"><a name="p774306"></a><a name="p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row11144211"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p30265903"><a name="p30265903"></a><a name="p30265903"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.06%" headers="mcps1.1.4.1.2 "><p id="p35619075"><a name="p35619075"></a><a name="p35619075"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.739999999999995%" headers="mcps1.1.4.1.3 "><p id="p66572856"><a name="p66572856"></a><a name="p66572856"></a>集合通信操作所在的通信域。</p>
<p id="p11441511175312"><a name="p11441511175312"></a><a name="p11441511175312"></a>HcclComm类型的定义如下：</p>
<a name="screen5220172285515"></a><a name="screen5220172285515"></a><pre class="screen" codetype="C" id="screen5220172285515">typedef void *HcclComm;</pre>
</td>
</tr>
<tr id="row62284798"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p11903911"><a name="p11903911"></a><a name="p11903911"></a>rank</p>
</td>
<td class="cellrowborder" valign="top" width="17.06%" headers="mcps1.1.4.1.2 "><p id="p24692740"><a name="p24692740"></a><a name="p24692740"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.739999999999995%" headers="mcps1.1.4.1.3 "><p id="p745044132619"><a name="p745044132619"></a><a name="p745044132619"></a>集合通信域中rank序号的输出地址指针。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section51595365"></a>

[HcclResult](../../comm_mgr_api_c/context/HcclResult.md)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="section61705107"></a>

无

## 调用示例<a name="section10236329223"></a>

```
uint32_t rank;
HcclComm comm;
HcclGetRankId(comm, &rank);
```

