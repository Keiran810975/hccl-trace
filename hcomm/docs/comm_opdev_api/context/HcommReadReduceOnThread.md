# HcommReadReduceOnThread<a name="ZH-CN_TOPIC_0000002539660995"></a>

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

从channel上的指定内存读数据，从src中读取长度为count\*sizeof\(dataType\)的内存数据，与dst所指向的相同长度的内存数据进行reduceOp操作，并将结果输出到dst中。接口调用方为dst所在节点。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommReadReduceOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t count, HcommDataType dataType, HcommReduceOp reduceOp)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.169999999999998%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.2%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p09686269404"><a name="p09686269404"></a><a name="p09686269404"></a>thread</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p207913834011"><a name="p207913834011"></a><a name="p207913834011"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p17355201413612"><a name="p17355201413612"></a><a name="p17355201413612"></a>通信线程句柄，为通过<a href="HcclThreadAcquire.md">HcclThreadAcquire</a>接口获取到的threads。</p>
<p id="p3415184125317"><a name="p3415184125317"></a><a name="p3415184125317"></a>ThreadHandle类型的定义可参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p2968122611409"><a name="p2968122611409"></a><a name="p2968122611409"></a>channel</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p07923894015"><a name="p07923894015"></a><a name="p07923894015"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1835518149364"><a name="p1835518149364"></a><a name="p1835518149364"></a>通信通道句柄，为通过<a href="HcclChannelAcquire.md">HcclChannelAcquire</a>接口获取到的channels。</p>
<p id="p1674334335318"><a name="p1674334335318"></a><a name="p1674334335318"></a>ChannelHandle类型的定义可参见<a href="ChannelHandle.md">ChannelHandle</a>。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p496822634014"><a name="p496822634014"></a><a name="p496822634014"></a>dst</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p157943864013"><a name="p157943864013"></a><a name="p157943864013"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p66311232164011"><a name="p66311232164011"></a><a name="p66311232164011"></a>目的内存地址。</p>
</td>
</tr>
<tr id="row5254181954016"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p18968326124015"><a name="p18968326124015"></a><a name="p18968326124015"></a>src</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p8377449124013"><a name="p8377449124013"></a><a name="p8377449124013"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p163123210406"><a name="p163123210406"></a><a name="p163123210406"></a>源内存地址。</p>
</td>
</tr>
<tr id="row1525481904012"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p69681026184017"><a name="p69681026184017"></a><a name="p69681026184017"></a>count</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p1038054914018"><a name="p1038054914018"></a><a name="p1038054914018"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p15632153213401"><a name="p15632153213401"></a><a name="p15632153213401"></a>元素个数。</p>
</td>
</tr>
<tr id="row102541519154016"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p199681726104012"><a name="p199681726104012"></a><a name="p199681726104012"></a>dataType</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p2038124912405"><a name="p2038124912405"></a><a name="p2038124912405"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1463263214406"><a name="p1463263214406"></a><a name="p1463263214406"></a>数据类型。</p>
<p id="p1651414615320"><a name="p1651414615320"></a><a name="p1651414615320"></a>HcommDataType类型的定义可参见<a href="HcommDataType.md">HcommDataType</a>。</p>
</td>
</tr>
<tr id="row51659228405"><td class="cellrowborder" valign="top" width="20.169999999999998%" headers="mcps1.1.4.1.1 "><p id="p199681526174012"><a name="p199681526174012"></a><a name="p199681526174012"></a>reduceOp</p>
</td>
<td class="cellrowborder" valign="top" width="17.2%" headers="mcps1.1.4.1.2 "><p id="p338234917402"><a name="p338234917402"></a><a name="p338234917402"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p5632193284016"><a name="p5632193284016"></a><a name="p5632193284016"></a>归约操作类型。</p>
<p id="p15757148165313"><a name="p15757148165313"></a><a name="p15757148165313"></a>HcommReduceOp类型的定义可参见<a href="HcommReduceOp.md">HcommReduceOp</a>。</p>
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
       // 将本端内存和对端内存数据进行reduce，输出到本端内存上
        HcommWriteReduceOnThread(threadHandle, channel, localBuf.addr, remoteBuf.addr, count, HCCL_DATA_TYPE_FP32, HCCL_REDUCE_SUM);
        // 数据写完成同步，通知对端本端数据读完成，并接收对端数据读完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 1);
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 1, NOTIFY_TIMEOUT);
        // 后同步，通知对端本端已完成读数据，并接收对端读数据完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 2);
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 2, NOTIFY_TIMEOUT);
    } else {
        // 前同步，通知对端本端已准备完成，并接收对端准备完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 0));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 0, NOTIFY_TIMEOUT);
        // 数据写完成同步，通知对端本端数据读完成，并接收对端数据读完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 1));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 1, NOTIFY_TIMEOUT);
        // 后同步，通知对端本端已完成读数据，并接收对端读数据完成信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 2));
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 2, NOTIFY_TIMEOUT);
    }
    return;
}
```

