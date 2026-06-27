# HcclThreadAcquire<a name="ZH-CN_TOPIC_0000002508101116"></a>

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

基于通信域获取通信线程。

## 函数原型<a name="section62999330"></a>

```
HcclResult HcclThreadAcquire(HcclComm comm, CommEngine engine, uint32_t threadNum, uint32_t notifyNumPerThread, ThreadHandle *threads)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.04%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.760000000000005%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p82552057155510"><a name="p82552057155510"></a><a name="p82552057155510"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.04%" headers="mcps1.1.4.1.2 "><p id="p11161232560"><a name="p11161232560"></a><a name="p11161232560"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.760000000000005%" headers="mcps1.1.4.1.3 "><p id="p10447102914165"><a name="p10447102914165"></a><a name="p10447102914165"></a>通信域。</p>
<p id="p11441511175312"><a name="p11441511175312"></a><a name="p11441511175312"></a>HcclComm类型的定义如下：</p>
<a name="screen5220172285515"></a><a name="screen5220172285515"></a><pre class="screen" codetype="C" id="screen5220172285515">typedef void *HcclComm;</pre>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p11255165714554"><a name="p11255165714554"></a><a name="p11255165714554"></a>engine</p>
</td>
<td class="cellrowborder" valign="top" width="17.04%" headers="mcps1.1.4.1.2 "><p id="p611614315569"><a name="p611614315569"></a><a name="p611614315569"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.760000000000005%" headers="mcps1.1.4.1.3 "><p id="p17945774568"><a name="p17945774568"></a><a name="p17945774568"></a>通信引擎类型。</p>
<p id="p362115913713"><a name="p362115913713"></a><a name="p362115913713"></a>CommEngine类型的定义可参见<a href="CommEngine.md">CommEngine</a>。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p1925535713552"><a name="p1925535713552"></a><a name="p1925535713552"></a>threadNum</p>
</td>
<td class="cellrowborder" valign="top" width="17.04%" headers="mcps1.1.4.1.2 "><p id="p11167310567"><a name="p11167310567"></a><a name="p11167310567"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.760000000000005%" headers="mcps1.1.4.1.3 "><p id="p1945137155617"><a name="p1945137155617"></a><a name="p1945137155617"></a>通信线程数量。一个通信域内最多申请40条流。</p>
</td>
</tr>
<tr id="row890074810555"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p9255165705511"><a name="p9255165705511"></a><a name="p9255165705511"></a>notifyNumPerThread</p>
</td>
<td class="cellrowborder" valign="top" width="17.04%" headers="mcps1.1.4.1.2 "><p id="p71168315564"><a name="p71168315564"></a><a name="p71168315564"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.760000000000005%" headers="mcps1.1.4.1.3 "><p id="p66685425012"><a name="p66685425012"></a><a name="p66685425012"></a>每个通信线程中的同步资源（Notify）数量。一个通信域内最多申请64个同步资源。</p>
</td>
</tr>
<tr id="row10874105015552"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p32551757115514"><a name="p32551757115514"></a><a name="p32551757115514"></a>threads</p>
</td>
<td class="cellrowborder" valign="top" width="17.04%" headers="mcps1.1.4.1.2 "><p id="p111643165612"><a name="p111643165612"></a><a name="p111643165612"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.760000000000005%" headers="mcps1.1.4.1.3 "><p id="p594547125619"><a name="p594547125619"></a><a name="p594547125619"></a>返回的通信线程句柄。需传入threadNum大小的ThreadHandle类型数组。</p>
<p id="p14685627185312"><a name="p14685627185312"></a><a name="p14685627185312"></a>ThreadHandle类型的定义可参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

[HcclResult](../../comm_mgr_api_c/context/HcclResult.md)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="section15114764"></a>

返回的通信线程与同步资源由库内管理，调用者严禁释放。

## 调用示例<a name="section204039211474"></a>

```
HcclComm comm;
CommEngine engine = COMM_ENGINE_AICPU_TS;
ThreadHandle threads[5];
// 申请5条流，每条流2个notify
HcclResult result = HcclThreadAcquire(comm, engine, 5, 2, threads);
```

