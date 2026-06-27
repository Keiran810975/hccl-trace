# HcclCommDestroy<a name="ZH-CN_TOPIC_0000002519007951"></a>

## 产品支持情况<a name="zh-cn_topic_0000001312721321_section10594071513"></a>

<a name="zh-cn_topic_0000001312721321_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001312721321_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001312721321_p1883113061818"><a name="zh-cn_topic_0000001312721321_p1883113061818"></a><a name="zh-cn_topic_0000001312721321_p1883113061818"></a><span id="zh-cn_topic_0000001312721321_ph20833205312295"><a name="zh-cn_topic_0000001312721321_ph20833205312295"></a><a name="zh-cn_topic_0000001312721321_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001312721321_p783113012187"><a name="zh-cn_topic_0000001312721321_p783113012187"></a><a name="zh-cn_topic_0000001312721321_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001312721321_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001312721321_p48327011813"><a name="zh-cn_topic_0000001312721321_p48327011813"></a><a name="zh-cn_topic_0000001312721321_p48327011813"></a><span id="zh-cn_topic_0000001312721321_ph583230201815"><a name="zh-cn_topic_0000001312721321_ph583230201815"></a><a name="zh-cn_topic_0000001312721321_ph583230201815"></a><term id="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001312721321_p7948163910184"><a name="zh-cn_topic_0000001312721321_p7948163910184"></a><a name="zh-cn_topic_0000001312721321_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721321_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001312721321_p14832120181815"><a name="zh-cn_topic_0000001312721321_p14832120181815"></a><a name="zh-cn_topic_0000001312721321_p14832120181815"></a><span id="zh-cn_topic_0000001312721321_ph1292674871116"><a name="zh-cn_topic_0000001312721321_ph1292674871116"></a><a name="zh-cn_topic_0000001312721321_ph1292674871116"></a><term id="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001312721321_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001312721321_p19948143911820"><a name="zh-cn_topic_0000001312721321_p19948143911820"></a><a name="zh-cn_topic_0000001312721321_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001312721321_section57787318"></a>

销毁指定的HCCL通信域。

## 函数原型<a name="zh-cn_topic_0000001312721321_section36246974"></a>

```
HcclResult HcclCommDestroy(HcclComm comm)
```

## 参数说明<a name="zh-cn_topic_0000001312721321_section50323820"></a>

<a name="zh-cn_topic_0000001312721321_table50198807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001312721321_row52060794"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001312721321_p56174818"><a name="zh-cn_topic_0000001312721321_p56174818"></a><a name="zh-cn_topic_0000001312721321_p56174818"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001312721321_p53866394"><a name="zh-cn_topic_0000001312721321_p53866394"></a><a name="zh-cn_topic_0000001312721321_p53866394"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001312721321_p1101770"><a name="zh-cn_topic_0000001312721321_p1101770"></a><a name="zh-cn_topic_0000001312721321_p1101770"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001312721321_row22134555"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001312721321_p48068532"><a name="zh-cn_topic_0000001312721321_p48068532"></a><a name="zh-cn_topic_0000001312721321_p48068532"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001312721321_p1237054"><a name="zh-cn_topic_0000001312721321_p1237054"></a><a name="zh-cn_topic_0000001312721321_p1237054"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001312721321_p33092577"><a name="zh-cn_topic_0000001312721321_p33092577"></a><a name="zh-cn_topic_0000001312721321_p33092577"></a>指向需要销毁的通信域的指针。</p>
<p id="zh-cn_topic_0000001312721321_p11441511175312"><a name="zh-cn_topic_0000001312721321_p11441511175312"></a><a name="zh-cn_topic_0000001312721321_p11441511175312"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001312721321_section50261201"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000001312721321_section49697630"></a>

-   此接口支持跨线程调用：
    -   当通信域状态处于建链卡住或者未被占用状态时，支持跨线程调用此接口销毁通信域，并返回HCCL\_SUCCESS。

        通信域销毁成功后，正在执行的通信算子无需等待超时时间会直接报错退出，并打印ERROR级别日志，日志关键字为“Terminating operation due to external request”。

    -   当通信域处于非建链卡住状态，或者其他被占用状态（例如通信域建链过程中、通信算子执行过程中等），跨线程调用此接口时会返回HCCL\_E\_AGAIN错误，并打印WARNING级别日志，日志关键字为“\[HcclCommDestroy\] comm is in use, please try again later”。

-   多线程场景下，需要确保HCCL接口的调用时序，调用此接口销毁通信域后不再支持调用其他集合通信相关接口。

## 调用示例<a name="zh-cn_topic_0000001312721321_section204039211474"></a>

```c
uint32_t rankSize = 2;
int32_t devices[rankSize] = {0, 1};
HcclComm comms[rankSize];
// 初始化通信域
HcclCommInitAll(rankSize, devices, comms);
// 销毁通信域
for (uint32_t i = 0; i &lt; rankSize; i++) {
    HcclCommDestroy(comms[i]);
}
```

