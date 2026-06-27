# HcclChannelAcquire<a name="ZH-CN_TOPIC_0000002539660961"></a>

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

基于通信域获取多个通信通道，如果通信域中没有对应的通信通道则直接创建。

channel是否复用，依据 commId + engine + remoterank + channelProtocol 组成的channel唯一标识判断。

## 函数原型<a name="section62999330"></a>

```
HcclResult HcclChannelAcquire(HcclComm comm, CommEngine engine, const HcclChannelDesc *channelDescs, uint32_t channelNum, ChannelHandle *channels)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.26%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.53999999999999%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p08341137987"><a name="p08341137987"></a><a name="p08341137987"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.26%" headers="mcps1.1.4.1.2 "><p id="p15352743188"><a name="p15352743188"></a><a name="p15352743188"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.53999999999999%" headers="mcps1.1.4.1.3 "><p id="p10447102914165"><a name="p10447102914165"></a><a name="p10447102914165"></a>通信域句柄。</p>
<p id="p11441511175312"><a name="p11441511175312"></a><a name="p11441511175312"></a>HcclComm类型的定义如下：</p>
<a name="screen5220172285515"></a><a name="screen5220172285515"></a><pre class="screen" codetype="C" id="screen5220172285515">typedef void *HcclComm;</pre>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p198347373817"><a name="p198347373817"></a><a name="p198347373817"></a>engine</p>
</td>
<td class="cellrowborder" valign="top" width="17.26%" headers="mcps1.1.4.1.2 "><p id="p178903171898"><a name="p178903171898"></a><a name="p178903171898"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.53999999999999%" headers="mcps1.1.4.1.3 "><p id="p192227485820"><a name="p192227485820"></a><a name="p192227485820"></a>通信引擎类型。</p>
<p id="p362115913713"><a name="p362115913713"></a><a name="p362115913713"></a>CommEngine类型的定义可参见<a href="CommEngine.md">CommEngine</a>。</p>
</td>
</tr>
<tr id="row68332241782"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p88341537682"><a name="p88341537682"></a><a name="p88341537682"></a>channelDescs</p>
</td>
<td class="cellrowborder" valign="top" width="17.26%" headers="mcps1.1.4.1.2 "><p id="p158914171795"><a name="p158914171795"></a><a name="p158914171795"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.53999999999999%" headers="mcps1.1.4.1.3 "><p id="p72239481983"><a name="p72239481983"></a><a name="p72239481983"></a>通信通道描述列表，列表长度为channelNum。</p>
<p id="p10912917141213"><a name="p10912917141213"></a><a name="p10912917141213"></a>HcclChannelDesc类型的定义可参见<a href="HcclChannelDesc.md">HcclChannelDesc</a>。</p>
</td>
</tr>
<tr id="row0833102413816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p883419371987"><a name="p883419371987"></a><a name="p883419371987"></a>channelNum</p>
</td>
<td class="cellrowborder" valign="top" width="17.26%" headers="mcps1.1.4.1.2 "><p id="p1489211171390"><a name="p1489211171390"></a><a name="p1489211171390"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.53999999999999%" headers="mcps1.1.4.1.3 "><p id="p122231448481"><a name="p122231448481"></a><a name="p122231448481"></a>通信通道数量，channelNum的取值范围为(0, 1024*1024]。</p>
</td>
</tr>
<tr id="row457782815815"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p1983413715818"><a name="p1983413715818"></a><a name="p1983413715818"></a>channels</p>
</td>
<td class="cellrowborder" valign="top" width="17.26%" headers="mcps1.1.4.1.2 "><p id="p1935204314814"><a name="p1935204314814"></a><a name="p1935204314814"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.53999999999999%" headers="mcps1.1.4.1.3 "><p id="p622324817816"><a name="p622324817816"></a><a name="p622324817816"></a>通信通道句柄列表。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

[HcclResult](../../comm_mgr_api_c/context/HcclResult.md)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="section15114764"></a>

无

## 调用示例<a name="section204039211474"></a>

以rank0与rank1和rank2进行批量通信通道获取为例：

```
uint32_t channelNum = 2;
std::vector<HcclChannelDesc> channelDesc(channelNum);
HcclChannelDescInit(channelDesc.data(), channelNum);

channelDesc[0].remoteRank = 1;
channelDesc[0].channelProtocol = CommProtocol::COMM_PROTOCOL_HCCS;
channelDesc[0].notifyNum = 3;

channelDesc[1].remoteRank = 2;
channelDesc[1].channelProtocol = CommProtocol::COMM_PROTOCOL_HCCS;
channelDesc[1].notifyNum = 3;

HcclComm comm; // 需使用对应通信域句柄，此处仅示例
CommEngine engine = CommEngine::COMM_ENGINE_CPU_TS;
std::vector<ChannelHandle> channels(channelNum);
HcclChannelAcquire(comm, engine, channelDesc.data(), channelNum, channels.data());
```

