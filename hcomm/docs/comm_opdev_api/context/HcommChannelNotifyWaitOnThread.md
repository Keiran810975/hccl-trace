# HcommChannelNotifyWaitOnThread<a name="ZH-CN_TOPIC_0000002507941298"></a>

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

等待同步信号，阻塞等待Thread的运行，直到指定的Notify完成。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommChannelNotifyWaitOnThread(ThreadHandle thread, ChannelHandle channel, uint32_t localNotifyIdx, uint32_t timeout)
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
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p7178361470"><a name="p7178361470"></a><a name="p7178361470"></a>thread</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p10678184712424"><a name="p10678184712424"></a><a name="p10678184712424"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p12623151017476"><a name="p12623151017476"></a><a name="p12623151017476"></a>通信线程句柄，为通过<a href="HcclThreadAcquire.md">HcclThreadAcquire</a>接口获取到的threads。</p>
<p id="p591620458319"><a name="p591620458319"></a><a name="p591620458319"></a>ThreadHandle类型的定义可参见<a href="ThreadHandle.md">ThreadHandle</a>。</p>
</td>
</tr>
<tr id="row63522246"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p13178186204712"><a name="p13178186204712"></a><a name="p13178186204712"></a>channel</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p118122715475"><a name="p118122715475"></a><a name="p118122715475"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p1835518149364"><a name="p1835518149364"></a><a name="p1835518149364"></a>通信通道句柄，为通过<a href="HcclChannelAcquire.md">HcclChannelAcquire</a>接口获取到的channels。</p>
<p id="p65951038151317"><a name="p65951038151317"></a><a name="p65951038151317"></a>ChannelHandle类型的定义可参见<a href="ChannelHandle.md">ChannelHandle</a>。</p>
</td>
</tr>
<tr id="row20735233"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p111781561476"><a name="p111781561476"></a><a name="p111781561476"></a>localNotifyIdx</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p16841227184718"><a name="p16841227184718"></a><a name="p16841227184718"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p92001442121818"><a name="p92001442121818"></a><a name="p92001442121818"></a>本地Notify索引。</p>
<p id="p262361016478"><a name="p262361016478"></a><a name="p262361016478"></a>取值范围：[0, <a href="HcclChannelAcquire.md">HcclChannelAcquire</a>接口传入的channelDescs参数中的notifyNum)。</p>
</td>
</tr>
<tr id="row175001219470"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p417896134720"><a name="p417896134720"></a><a name="p417896134720"></a>timeout</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p12877275471"><a name="p12877275471"></a><a name="p12877275471"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><div class="p" id="p2091895534715"><a name="p2091895534715"></a><a name="p2091895534715"></a>超时时间，单位：毫秒。<a name="ul3398449141718"></a><a name="ul3398449141718"></a><ul id="ul3398449141718"><li>0：表示永久等待。</li><li>&gt;0：配置的具体超时时间。</li></ul>
</div>
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
        // 发送同步信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 0));
        // 等待同步信号
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 0, NOTIFY_TIMEOUT);
    } else {
        // 发送同步信号
        HcommChannelNotifyRecordOnThread(threadHandle, channel, 0));
        // 等待同步信号
        HcommChannelNotifyWaitOnThread(threadHandle, channel, 0, NOTIFY_TIMEOUT);
    }
    return;
}
```

