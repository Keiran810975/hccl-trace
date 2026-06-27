# HcclCommConfigInit<a name="ZH-CN_TOPIC_0000002486848092"></a>

## 产品支持情况<a name="zh-cn_topic_0000001936349613_section10594071513"></a>

<a name="zh-cn_topic_0000001936349613_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001936349613_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001936349613_p1883113061818"><a name="zh-cn_topic_0000001936349613_p1883113061818"></a><a name="zh-cn_topic_0000001936349613_p1883113061818"></a><span id="zh-cn_topic_0000001936349613_ph20833205312295"><a name="zh-cn_topic_0000001936349613_ph20833205312295"></a><a name="zh-cn_topic_0000001936349613_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001936349613_p783113012187"><a name="zh-cn_topic_0000001936349613_p783113012187"></a><a name="zh-cn_topic_0000001936349613_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001936349613_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001936349613_p48327011813"><a name="zh-cn_topic_0000001936349613_p48327011813"></a><a name="zh-cn_topic_0000001936349613_p48327011813"></a><span id="zh-cn_topic_0000001936349613_ph583230201815"><a name="zh-cn_topic_0000001936349613_ph583230201815"></a><a name="zh-cn_topic_0000001936349613_ph583230201815"></a><term id="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001936349613_p7948163910184"><a name="zh-cn_topic_0000001936349613_p7948163910184"></a><a name="zh-cn_topic_0000001936349613_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001936349613_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001936349613_p14832120181815"><a name="zh-cn_topic_0000001936349613_p14832120181815"></a><a name="zh-cn_topic_0000001936349613_p14832120181815"></a><span id="zh-cn_topic_0000001936349613_ph1292674871116"><a name="zh-cn_topic_0000001936349613_ph1292674871116"></a><a name="zh-cn_topic_0000001936349613_ph1292674871116"></a><term id="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001936349613_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001936349613_p19948143911820"><a name="zh-cn_topic_0000001936349613_p19948143911820"></a><a name="zh-cn_topic_0000001936349613_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000001936349613_section60885635"></a>

初始化通信域配置项，并将其中的可配置参数设为默认值。

## 函数原型<a name="zh-cn_topic_0000001936349613_section14221611"></a>

```
inline void HcclCommConfigInit(HcclCommConfig *config)
```

## 参数说明<a name="zh-cn_topic_0000001936349613_section11099805"></a>

<a name="zh-cn_topic_0000001936349613_table49150562"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001936349613_row42137308"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000001936349613_p57678784"><a name="zh-cn_topic_0000001936349613_p57678784"></a><a name="zh-cn_topic_0000001936349613_p57678784"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000001936349613_p41469957"><a name="zh-cn_topic_0000001936349613_p41469957"></a><a name="zh-cn_topic_0000001936349613_p41469957"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000001936349613_p3623379"><a name="zh-cn_topic_0000001936349613_p3623379"></a><a name="zh-cn_topic_0000001936349613_p3623379"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001936349613_row25058257"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000001936349613_p872317575144"><a name="zh-cn_topic_0000001936349613_p872317575144"></a><a name="zh-cn_topic_0000001936349613_p872317575144"></a>config</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000001936349613_p11723157141410"><a name="zh-cn_topic_0000001936349613_p11723157141410"></a><a name="zh-cn_topic_0000001936349613_p11723157141410"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000001936349613_p172215573143"><a name="zh-cn_topic_0000001936349613_p172215573143"></a><a name="zh-cn_topic_0000001936349613_p172215573143"></a>需要初始化的通信域配置项。</p>
<p id="zh-cn_topic_0000001936349613_p394110131393"><a name="zh-cn_topic_0000001936349613_p394110131393"></a><a name="zh-cn_topic_0000001936349613_p394110131393"></a>HcclCommConfig类型的定义可参见<a href="HcclCommConfig.md#ZH-CN_TOPIC_0000002486848108">HcclCommConfig</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000001936349613_section32789387"></a>

无

## 约束说明<a name="zh-cn_topic_0000001936349613_section26669028"></a>

无

## 调用示例<a name="zh-cn_topic_0000001936349613_section204039211474"></a>

```c
uint32_t rankSize = 8;
uint32_t deviceId = 0;
// 生成 root 节点的 rank 标识信息
HcclRootInfo rootInfo;
HcclGetRootInfo(&rootInfo);

// 创建并初始化通信域配置项
HcclCommConfig config;
HcclCommConfigInit(&config);
// 按需修改通信域配置
config.hcclBufferSize = 1024;  // 共享数据的缓存区大小，单位为：MB，取值需 >= 1，默认值为：200
config.hcclDeterministic = 1;  // 开启归约类通信算子的确定性计算，默认值为：0，表示关闭确定性计算功能
std::strcpy(config.hcclCommName, "comm_1");
// 初始化集合通信域
HcclComm hcclComm;
HCCLCHECK(HcclCommInitRootInfoConfig(rankSize, &rootInfo, deviceId, &config, &hcclComm));

// 销毁通信域
HcclCommDestroy(hcclComm);
```

