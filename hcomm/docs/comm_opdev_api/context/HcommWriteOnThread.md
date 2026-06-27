# HcommWriteOnThread<a name="ZH-CN_TOPIC_0000002539780955"></a>

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

向channel上的指定内存写数据，将src中长度为len的内存数据写入dst所指向的相同长度的内存区域。接口调用方为src所在节点，该接口为异步接口。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommWriteOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len)
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
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p759413341827"><a name="p759413341827"></a><a name="p759413341827"></a>thread</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p10678184712424"><a name="p10678184712424"></a><a name="p10678184712424"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p511245620216"><a name="p511245620216"></a><a name="p511245620216"></a>通信线程句柄，为通过<a href="HcclThreadAcquire.md">HcclThreadAcquire</a>接口获取到的threads。</p>
<p id="p12422192414409"><a name="p12422192414409"></a><a name="p12422192414409"></a>ThreadHandle类型的定义可参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p1159417341425"><a name="p1159417341425"></a><a name="p1159417341425"></a>channel</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p267718470424"><a name="p267718470424"></a><a name="p267718470424"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p11125566215"><a name="p11125566215"></a><a name="p11125566215"></a>通信通道句柄，为通过<a href="HcclChannelAcquire.md">HcclChannelAcquire</a>接口获取到的channels。</p>
<p id="p48471353131"><a name="p48471353131"></a><a name="p48471353131"></a>ChannelHandle类型的定义可参见<a href="ChannelHandle.md">ChannelHandle</a>。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p559413420216"><a name="p559413420216"></a><a name="p559413420216"></a>dst</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p156766470425"><a name="p156766470425"></a><a name="p156766470425"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p5112556425"><a name="p5112556425"></a><a name="p5112556425"></a>目的内存地址。</p>
</td>
</tr>
<tr id="row4499529423"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p2059412341722"><a name="p2059412341722"></a><a name="p2059412341722"></a>src</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p5499929822"><a name="p5499929822"></a><a name="p5499929822"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1511220561227"><a name="p1511220561227"></a><a name="p1511220561227"></a>源内存地址。</p>
</td>
</tr>
<tr id="row1449915299217"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p155941934020"><a name="p155941934020"></a><a name="p155941934020"></a>len</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p749972911215"><a name="p749972911215"></a><a name="p749972911215"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p151121456920"><a name="p151121456920"></a><a name="p151121456920"></a>数据长度（字节）。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

int32\_t：接口成功返回0，其他失败。

## 约束说明<a name="section15114764"></a>

无

## 调用示例<a name="section204039211474"></a>

```
typedef struct {
    HcclMemType type; ///< 缓存物理位置类型，参见HcclMemType
    void *addr;       ///< 缓存地址
    uint64_t size;    ///< 缓存区域字节数
} CommBuffer;
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

ThreadHandle threads[2];
// 申请2条流，每条流2个notify
HcclResult result = HcclThreadAcquire(comm, engine, 2, 2, threads);

u32 NOTIFY_TIMEOUT = 1;
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
        // 将本端内存的内容写到对端内存上
        HcommWriteOnThread(threadHandle, channel, remoteBuf.addr, localBuf.addr, len);
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

