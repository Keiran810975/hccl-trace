# HcommLocalCopyOnThread<a name="ZH-CN_TOPIC_0000002508101102"></a>

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

提供本地内存拷贝功能，将src指向的长度为len的内存数据，拷贝到dst所指向的相同长度的内存中。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommLocalCopyOnThread(ThreadHandle thread, void *dst, const void *src, uint64_t len)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.150000000000002%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.64999999999999%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p10949854144013"><a name="p10949854144013"></a><a name="p10949854144013"></a>thread</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="p10678184712424"><a name="p10678184712424"></a><a name="p10678184712424"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="p1729642414713"><a name="p1729642414713"></a><a name="p1729642414713"></a>通信线程句柄，为通过<a href="HcclThreadAcquire.md">HcclThreadAcquire</a>接口获取到的threads。</p>
<p id="p116943995018"><a name="p116943995018"></a><a name="p116943995018"></a>ThreadHandle的类型的定义请参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p994914542406"><a name="p994914542406"></a><a name="p994914542406"></a>dst</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="p267718470424"><a name="p267718470424"></a><a name="p267718470424"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="p109453294111"><a name="p109453294111"></a><a name="p109453294111"></a>目的内存地址，Device内存。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p199491854204015"><a name="p199491854204015"></a><a name="p199491854204015"></a>src</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="p156766470425"><a name="p156766470425"></a><a name="p156766470425"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="p494513220412"><a name="p494513220412"></a><a name="p494513220412"></a>源内存地址，Device内存。</p>
</td>
</tr>
<tr id="row12694114054015"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p8949185404017"><a name="p8949185404017"></a><a name="p8949185404017"></a>len</p>
</td>
<td class="cellrowborder" valign="top" width="17.150000000000002%" headers="mcps1.1.4.1.2 "><p id="p1969418409401"><a name="p1969418409401"></a><a name="p1969418409401"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.64999999999999%" headers="mcps1.1.4.1.3 "><p id="p1094519215415"><a name="p1094519215415"></a><a name="p1094519215415"></a>数据长度（字节）。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

int32\_t：接口成功返回0，其他失败。

## 约束说明<a name="section15114764"></a>

源内存地址、目的内存地址要能被执行引擎直接访问。

## 调用示例<a name="section204039211474"></a>

```
HcclComm comm;
CommEngine engine = COMM_ENGINE_CPU_TS;
ThreadHandle threads[2];
// 申请2条流，每条流2个Notify
HcclResult result = HcclThreadAcquire(comm, engine, 2, 2, &threads);
uint64_t memSize = 256;
DeviceMem inputMem = DeviceMem::alloc(memSize);
DeviceMem outputMem = DeviceMem::alloc(memSize);
// 执行 D2D 拷贝
HcommLocalCopyOnThread(threads[0], outputMem.ptr(), inputMem.ptr(), memSize);
```

