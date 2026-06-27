# HcclRankGraphGetLinks<a name="ZH-CN_TOPIC_0000002508101126"></a>

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

## 功能说明<a name="section30123063"></a>

给定通信域和拓扑层级编号，查询源rank和目的rank之间的通信连接信息。

以Atlas A3 训练系列产品/Atlas A3 推理系列产品为例：

-   示例1：源rank与目的rank分别在两个超节点。

    netLayer = 0， 无连接。

    netLayer = 1， 无连接。

    netLayer = 2， RDMA连接。

-   示例2：源rank与目的rank在同一个超节点，但不在同一个AI Server内。

    netLayer = 0， 无连接。

    netLayer = 1， HCCS连接。

    netLayer = 2， 无连接。

-   示例3：源rank与目的rank在同一个AI Server内，不在同一个DIE中。

    netLayer = 0， HCCS连接。

    netLayer = 1， 无连接。

    netLayer = 2， 无连接。

## 函数原型<a name="section62999330"></a>

```
HcclResult HcclRankGraphGetLinks(HcclComm comm, uint32_t netLayer, uint32_t srcRank, uint32_t dstRank, CommLink **links, uint32_t *linkNum)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p4801173119149"><a name="p4801173119149"></a><a name="p4801173119149"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1215811499149"><a name="p1215811499149"></a><a name="p1215811499149"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1471813717143"><a name="p1471813717143"></a><a name="p1471813717143"></a>通信域。</p>
<p id="p11441511175312"><a name="p11441511175312"></a><a name="p11441511175312"></a>HcclComm类型的定义如下：</p>
<a name="screen5220172285515"></a><a name="screen5220172285515"></a><pre class="screen" codetype="C" id="screen5220172285515">typedef void *HcclComm;</pre>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p18012313142"><a name="p18012313142"></a><a name="p18012313142"></a>netLayer</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p71586491149"><a name="p71586491149"></a><a name="p71586491149"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1724351976"><a name="p1724351976"></a><a name="p1724351976"></a>拓扑层级编号。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p1801431191415"><a name="p1801431191415"></a><a name="p1801431191415"></a>srcRank</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p191586490147"><a name="p191586490147"></a><a name="p191586490147"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p7718193714143"><a name="p7718193714143"></a><a name="p7718193714143"></a>源rank编号。</p>
</td>
</tr>
<tr id="row16220710151410"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p98011531161417"><a name="p98011531161417"></a><a name="p98011531161417"></a>dstRank</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p10158184910140"><a name="p10158184910140"></a><a name="p10158184910140"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p57181637171419"><a name="p57181637171419"></a><a name="p57181637171419"></a>目的rank编号。</p>
</td>
</tr>
<tr id="row16220151010145"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p17801133117145"><a name="p17801133117145"></a><a name="p17801133117145"></a>links</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p6158104916145"><a name="p6158104916145"></a><a name="p6158104916145"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p871811379147"><a name="p871811379147"></a><a name="p871811379147"></a>通信连接列表。</p>
<p id="p370893415496"><a name="p370893415496"></a><a name="p370893415496"></a>CommLink类型的定义请参见<a href="CommLink.md">CommLink</a>。</p>
</td>
</tr>
<tr id="row15220121014142"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p9801143171410"><a name="p9801143171410"></a><a name="p9801143171410"></a>linkNum</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1115874961413"><a name="p1115874961413"></a><a name="p1115874961413"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p19718113716147"><a name="p19718113716147"></a><a name="p19718113716147"></a>通信连接数量。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

[HcclResult](../../comm_mgr_api_c/context/HcclResult.md)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="section15114764"></a>

无

## 调用示例<a name="section204039211474"></a>

```
HcclComm comm;
CommLink *links;
uint32_t linkNum;
uint32_t netlayer = 0;
// 查询机内rank0与rank1间的链路
HcclRankGraphGetLinks(comm, netlayer, 0, 1, &links, &linkNum);
```

