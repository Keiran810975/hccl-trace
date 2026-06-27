# HcclGetCommConfigCapability<a name="ZH-CN_TOPIC_0000002486848096"></a>

## 产品支持情况<a name="zh-cn_topic_0000002023304797_section10594071513"></a>

<a name="zh-cn_topic_0000002023304797_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002023304797_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002023304797_p1883113061818"><a name="zh-cn_topic_0000002023304797_p1883113061818"></a><a name="zh-cn_topic_0000002023304797_p1883113061818"></a><span id="zh-cn_topic_0000002023304797_ph20833205312295"><a name="zh-cn_topic_0000002023304797_ph20833205312295"></a><a name="zh-cn_topic_0000002023304797_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002023304797_p783113012187"><a name="zh-cn_topic_0000002023304797_p783113012187"></a><a name="zh-cn_topic_0000002023304797_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002023304797_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002023304797_p48327011813"><a name="zh-cn_topic_0000002023304797_p48327011813"></a><a name="zh-cn_topic_0000002023304797_p48327011813"></a><span id="zh-cn_topic_0000002023304797_ph583230201815"><a name="zh-cn_topic_0000002023304797_ph583230201815"></a><a name="zh-cn_topic_0000002023304797_ph583230201815"></a><term id="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002023304797_p7948163910184"><a name="zh-cn_topic_0000002023304797_p7948163910184"></a><a name="zh-cn_topic_0000002023304797_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002023304797_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002023304797_p14832120181815"><a name="zh-cn_topic_0000002023304797_p14832120181815"></a><a name="zh-cn_topic_0000002023304797_p14832120181815"></a><span id="zh-cn_topic_0000002023304797_ph1292674871116"><a name="zh-cn_topic_0000002023304797_ph1292674871116"></a><a name="zh-cn_topic_0000002023304797_ph1292674871116"></a><term id="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002023304797_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002023304797_p19948143911820"><a name="zh-cn_topic_0000002023304797_p19948143911820"></a><a name="zh-cn_topic_0000002023304797_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002023304797_section31291646"></a>

该接口用于判断当前版本软件是否支持某项通信域初始化配置。

通信域初始化时支持的完整配置项可参见[HcclCommConfigCapability](HcclCommConfigCapability.md#ZH-CN_TOPIC_0000002519087959)，包括共享数据的缓存区大小、确定性计算开关、通信域名称、通信算法的编排展开位置等。

使用HcclGetCommConfigCapability接口判断当前软件是否支持某项配置的流程为：

1.  调用HcclGetCommConfigCapability接口，获取一个代表当前软件通信域初始化配置能力的数值。
2.  比较该数值与[HcclCommConfigCapability](HcclCommConfigCapability.md#ZH-CN_TOPIC_0000002519087959)中某项配置枚举值的大小，若该数值大于枚举值，代表当前软件支持[HcclCommConfigCapability](HcclCommConfigCapability.md#ZH-CN_TOPIC_0000002519087959)中对应枚举值的配置能力；若该数值小于等于枚举值，代表不支持。

    例如，若想判断当前软件是否支持配置通信域名称，可使用HcclGetCommConfigCapability接口的返回值与枚举值“HCCL\_COMM\_CONFIG\_COMM\_NAME”做比较，若返回值大于“HCCL\_COMM\_CONFIG\_COMM\_NAME”，代表当前软件支持配置通信域名称；若返回值小于等于“HCCL\_COMM\_CONFIG\_COMM\_NAME”，代表当前软件不支持配置通信域名称。

## 函数原型<a name="zh-cn_topic_0000002023304797_section18389930"></a>

```
uint32_t HcclGetCommConfigCapability()
```

## 参数说明<a name="zh-cn_topic_0000002023304797_section13189358"></a>

无

## 返回值<a name="zh-cn_topic_0000002023304797_section51595365"></a>

uint32\_t：表示通信域初始化配置能力的数值。

## 约束说明<a name="zh-cn_topic_0000002023304797_section764575019568"></a>

无

## 调用示例<a name="zh-cn_topic_0000002023304797_section10236329223"></a>

```c
uint32_t configCapability = HcclGetCommConfigCapability();
bool isSupportCommName = configCapability > HCCL_COMM_CONFIG_COMM_NAME;  // 判断是否支持配置通信域名称
```

