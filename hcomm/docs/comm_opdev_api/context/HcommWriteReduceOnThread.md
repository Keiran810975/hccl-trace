# HcommWriteReduceOnThread<a name="ZH-CN_TOPIC_0000002539780965"></a>

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

向channel上的指定内存写数据，将src中长度为count\*sizeof\(dataType\)的内存数据，与dst所指向的相同长度的内存数据进行reduceOp操作，并将结果输出到dst中。接口调用方为src所在节点。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommWriteReduceOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t count, HcommDataType dataType, HcommReduceOp reduceOp)
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
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p124505112612"><a name="p124505112612"></a><a name="p124505112612"></a>thread</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p16313204615265"><a name="p16313204615265"></a><a name="p16313204615265"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p47942029192618"><a name="p47942029192618"></a><a name="p47942029192618"></a>通信线程句柄，为通过<a href="HcclThreadAcquire.md">HcclThreadAcquire</a>接口获取到的threads。</p>
<p id="p11358172417460"><a name="p11358172417460"></a><a name="p11358172417460"></a>ThreadHandle类型的定义可参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p102451651202615"><a name="p102451651202615"></a><a name="p102451651202615"></a>channel</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1731354615260"><a name="p1731354615260"></a><a name="p1731354615260"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p3794132912262"><a name="p3794132912262"></a><a name="p3794132912262"></a>通信通道句柄，为通过<a href="HcclChannelAcquire.md">HcclChannelAcquire</a>接口获取到的channels。</p>
<p id="p2879124274614"><a name="p2879124274614"></a><a name="p2879124274614"></a>ChannelHandle类型的定义可参见<a href="ChannelHandle.md">ChannelHandle</a>。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p7245185182614"><a name="p7245185182614"></a><a name="p7245185182614"></a>dst</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p931414622611"><a name="p931414622611"></a><a name="p931414622611"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1979452932610"><a name="p1979452932610"></a><a name="p1979452932610"></a>目的内存地址。</p>
</td>
</tr>
<tr id="row14552121612269"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p02451051152619"><a name="p02451051152619"></a><a name="p02451051152619"></a>src</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1065271362717"><a name="p1065271362717"></a><a name="p1065271362717"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p14794829122618"><a name="p14794829122618"></a><a name="p14794829122618"></a>源内存地址。</p>
</td>
</tr>
<tr id="row175521116142617"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p142451551112619"><a name="p142451551112619"></a><a name="p142451551112619"></a>count</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1965414133276"><a name="p1965414133276"></a><a name="p1965414133276"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p7794192912260"><a name="p7794192912260"></a><a name="p7794192912260"></a>元素个数。</p>
</td>
</tr>
<tr id="row19552316202616"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p152455518269"><a name="p152455518269"></a><a name="p152455518269"></a>dataType</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1265517139273"><a name="p1265517139273"></a><a name="p1265517139273"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p157956292264"><a name="p157956292264"></a><a name="p157956292264"></a>数据类型。</p>
<p id="p92761111115"><a name="p92761111115"></a><a name="p92761111115"></a>HcommDataType类型的定义可参见<a href="HcommDataType.md">HcommDataType</a>。</p>
</td>
</tr>
<tr id="row7832102019268"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p10245751142615"><a name="p10245751142615"></a><a name="p10245751142615"></a>reduceOp</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p196571213162716"><a name="p196571213162716"></a><a name="p196571213162716"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1279511294267"><a name="p1279511294267"></a><a name="p1279511294267"></a>归约操作类型。</p>
<p id="p176965115515"><a name="p176965115515"></a><a name="p176965115515"></a>HcommReduceOp类型的定义可参见<a href="HcommReduceOp.md">HcommReduceOp</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

int32\_t：接口成功返回0，其他失败。

## 约束说明<a name="section15114764"></a>

无

## 调用示例<a name="section204039211474"></a>

资源初始化相关代码请参见[HcommWriteOnThread](HcommWriteOnThread.md)的调用示例。

```
void Sample(HcclComm comm, ChannelHandle channel, HcclThread threadHandle, uint32_t rank)
{
    if (rank == 0) {
        CommBuffer localBuf;
        // 获取本端通信内存信息
        HcclGetHcclBuffer(comm, &localBuf.addr, &localBuf.size);
        CommBuffer remoteBuf;
        // 获取对端通信内存信息
        HcclChannelGetHcclBuffer(comm, channel, &remoteBuf.addr, &remoteBuf.size);
        uint64_t len = std::min(localBuf.size, remoteBuf.size);

        // 前同步，通知对端本端已准备完成，并接收对端准备完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 0));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 0, NOTIFY_TIMEOUT);
        // 将本端内存和对端内存数据进行reduce，输出到对端内存上
        HcommWriteReduceOnThread(threadHandle, channel, remoteBuf.addr, localBuf.addr, count, HCCL_DATA_TYPE_FP32, HCCL_REDUCE_SUM);
        // 数据写完成同步，通知对端本端数据写完成，并接收对端数据写完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 1);
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 1, NOTIFY_TIMEOUT);
        // 后同步，通知对端本端已完成数据接收，并接收对端数据接收完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 2);
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 2, NOTIFY_TIMEOUT);
    } else {
        // 前同步，通知对端本端已准备完成，并接收对端准备完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 0));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 0, NOTIFY_TIMEOUT);
        // 数据写完成同步，通知对端本端数据写完成，并接收对端数据写完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 1));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 1, NOTIFY_TIMEOUT);
        // 后同步，通知对端本端已完成数据接收，并接收对端数据接收完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 2));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 2, NOTIFY_TIMEOUT);
    }
    return;
}
```

