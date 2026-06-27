# HcclCommInitClusterInfoConfig<a name="ZH-CN_TOPIC_0000002486848090"></a>

## 产品支持情况<a name="zh-cn_topic_0000002037828213_section161778316247"></a>

<a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p1883113061818"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p1883113061818"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p1883113061818"></a><span id="zh-cn_topic_0000002037828213_ph20833205312295"><a name="zh-cn_topic_0000002037828213_ph20833205312295"></a><a name="zh-cn_topic_0000002037828213_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p783113012187"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p783113012187"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002037828213_p48327011813"><a name="zh-cn_topic_0000002037828213_p48327011813"></a><a name="zh-cn_topic_0000002037828213_p48327011813"></a><span id="zh-cn_topic_0000002037828213_ph583230201815"><a name="zh-cn_topic_0000002037828213_ph583230201815"></a><a name="zh-cn_topic_0000002037828213_ph583230201815"></a><term id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p7948163910184"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p7948163910184"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002037828213_p14832120181815"><a name="zh-cn_topic_0000002037828213_p14832120181815"></a><a name="zh-cn_topic_0000002037828213_p14832120181815"></a><span id="zh-cn_topic_0000002037828213_ph1292674871116"><a name="zh-cn_topic_0000002037828213_ph1292674871116"></a><a name="zh-cn_topic_0000002037828213_ph1292674871116"></a><term id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p19948143911820"><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p19948143911820"></a><a name="zh-cn_topic_0000002037828213_zh-cn_topic_0000001264921398_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002037828213_section31291646"></a>

基于rank table初始化HCCL，创建具有特定配置的HCCL通信域。

## 函数原型<a name="zh-cn_topic_0000002037828213_section18389930"></a>

```
HcclResult HcclCommInitClusterInfoConfig(const char *clusterInfo, uint32_t rank, HcclCommConfig *config, HcclComm *comm)
```

## 参数说明<a name="zh-cn_topic_0000002037828213_section13189358"></a>

<a name="zh-cn_topic_0000002037828213_table24749807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002037828213_row60665573"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002037828213_p14964341"><a name="zh-cn_topic_0000002037828213_p14964341"></a><a name="zh-cn_topic_0000002037828213_p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002037828213_p4152081"><a name="zh-cn_topic_0000002037828213_p4152081"></a><a name="zh-cn_topic_0000002037828213_p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002037828213_p774306"><a name="zh-cn_topic_0000002037828213_p774306"></a><a name="zh-cn_topic_0000002037828213_p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002037828213_row11144211"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002037828213_p137161266200"><a name="zh-cn_topic_0000002037828213_p137161266200"></a><a name="zh-cn_topic_0000002037828213_p137161266200"></a>clusterInfo</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002037828213_p17209562"><a name="zh-cn_topic_0000002037828213_p17209562"></a><a name="zh-cn_topic_0000002037828213_p17209562"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002037828213_p51797270"><a name="zh-cn_topic_0000002037828213_p51797270"></a><a name="zh-cn_topic_0000002037828213_p51797270"></a>rank table文件路径（含文件名），作为字符串最大长度为4096字节，含结束符。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002037828213_row62284798"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002037828213_p45028263"><a name="zh-cn_topic_0000002037828213_p45028263"></a><a name="zh-cn_topic_0000002037828213_p45028263"></a>rank</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002037828213_p23410681"><a name="zh-cn_topic_0000002037828213_p23410681"></a><a name="zh-cn_topic_0000002037828213_p23410681"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002037828213_p17216995"><a name="zh-cn_topic_0000002037828213_p17216995"></a><a name="zh-cn_topic_0000002037828213_p17216995"></a>本rank的id。</p>
<p id="zh-cn_topic_0000002037828213_p62591941105"><a name="zh-cn_topic_0000002037828213_p62591941105"></a><a name="zh-cn_topic_0000002037828213_p62591941105"></a>需要注意，此参数取值需要与rank table中对应的“rank_id”字段取值一致。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002037828213_row12142072118"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002037828213_p240214111093"><a name="zh-cn_topic_0000002037828213_p240214111093"></a><a name="zh-cn_topic_0000002037828213_p240214111093"></a>config</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002037828213_p940218116912"><a name="zh-cn_topic_0000002037828213_p940218116912"></a><a name="zh-cn_topic_0000002037828213_p940218116912"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002037828213_p184021111894"><a name="zh-cn_topic_0000002037828213_p184021111894"></a><a name="zh-cn_topic_0000002037828213_p184021111894"></a>通信域配置项，包括buffer大小、确定性计算开关、通信域名称、通信算法编排展开位置等信息，配置参数需确保在合法值域内，关于HcclCommConfig中的详细参数含义及优先级可参见<a href="HcclCommConfig.md#ZH-CN_TOPIC_0000002486848108">HcclCommConfig</a>的定义。</p>
<p id="zh-cn_topic_0000002037828213_p19668115113415"><a name="zh-cn_topic_0000002037828213_p19668115113415"></a><a name="zh-cn_topic_0000002037828213_p19668115113415"></a>需要注意：传入的config必须先调用<a href="HcclCommConfigInit.md#ZH-CN_TOPIC_0000002486848092">HcclCommConfigInit</a>对其进行初始化。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002037828213_row1541041491118"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002037828213_p1832323"><a name="zh-cn_topic_0000002037828213_p1832323"></a><a name="zh-cn_topic_0000002037828213_p1832323"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002037828213_p14200498"><a name="zh-cn_topic_0000002037828213_p14200498"></a><a name="zh-cn_topic_0000002037828213_p14200498"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002037828213_p9389685"><a name="zh-cn_topic_0000002037828213_p9389685"></a><a name="zh-cn_topic_0000002037828213_p9389685"></a>将初始化后的通信域以指针的信息回传给调用者。</p>
<p id="zh-cn_topic_0000002037828213_p2077615118500"><a name="zh-cn_topic_0000002037828213_p2077615118500"></a><a name="zh-cn_topic_0000002037828213_p2077615118500"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002037828213_section51595365"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002037828213_section61705107"></a>

同一通信域不支持重复初始化。

## 调用示例<a name="zh-cn_topic_0000002037828213_section10236329223"></a>

```c
// 设备资源初始化
aclInit(NULL);
// rank table配置文件路径
const char *rankTableFile = "/path/to/rank_table.json";
// 指定集合通信操作使用的设备
uint32_t rankSize = 8;
uint32_t devId = 0;
aclrtSetDevice(devId);
// 创建并初始化通信域配置项
HcclCommConfig config;
HcclCommConfigInit(&config);
// 按需修改通信域配置
config.hcclBufferSize = 50;  // 共享数据的缓存区大小，单位为：MB，取值需 >= 1，默认值为：200
std::strcpy(config.hcclCommName, "comm_1");
// 初始化通信域
HcclComm hcclComm;
HcclCommInitClusterInfoConfig(rankTableFile, devId, &config, &hcclComm);
// 销毁通信域
HcclCommDestroy(hcclComm);
// 设备资源去初始化
aclFinalize();
```

