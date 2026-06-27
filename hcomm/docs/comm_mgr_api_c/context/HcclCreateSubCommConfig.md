# HcclCreateSubCommConfig<a name="ZH-CN_TOPIC_0000002487008058"></a>

## 产品支持情况<a name="zh-cn_topic_0000002001711534_section10594071513"></a>

<a name="zh-cn_topic_0000002001711534_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002001711534_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000002001711534_p1883113061818"><a name="zh-cn_topic_0000002001711534_p1883113061818"></a><a name="zh-cn_topic_0000002001711534_p1883113061818"></a><span id="zh-cn_topic_0000002001711534_ph20833205312295"><a name="zh-cn_topic_0000002001711534_ph20833205312295"></a><a name="zh-cn_topic_0000002001711534_ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000002001711534_p783113012187"><a name="zh-cn_topic_0000002001711534_p783113012187"></a><a name="zh-cn_topic_0000002001711534_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002001711534_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002001711534_p48327011813"><a name="zh-cn_topic_0000002001711534_p48327011813"></a><a name="zh-cn_topic_0000002001711534_p48327011813"></a><span id="zh-cn_topic_0000002001711534_ph583230201815"><a name="zh-cn_topic_0000002001711534_ph583230201815"></a><a name="zh-cn_topic_0000002001711534_ph583230201815"></a><term id="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002001711534_p7948163910184"><a name="zh-cn_topic_0000002001711534_p7948163910184"></a><a name="zh-cn_topic_0000002001711534_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000002001711534_p14832120181815"><a name="zh-cn_topic_0000002001711534_p14832120181815"></a><a name="zh-cn_topic_0000002001711534_p14832120181815"></a><span id="zh-cn_topic_0000002001711534_ph1292674871116"><a name="zh-cn_topic_0000002001711534_ph1292674871116"></a><a name="zh-cn_topic_0000002001711534_ph1292674871116"></a><term id="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000002001711534_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000002001711534_p19948143911820"><a name="zh-cn_topic_0000002001711534_p19948143911820"></a><a name="zh-cn_topic_0000002001711534_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="zh-cn_topic_0000002001711534_section31291646"></a>

基于既有的全局通信域，切分具有特定配置的子通信域。

该子通信域创建方式无需进行socket建链与rank信息交换，可应用于业务故障下的快速通信域创建。

> [!NOTE]说明
>如果组网中卡间存在负载不均衡的情况，使用该接口创建的子通信域可能会由于卡间不同步发生建链超时。此时可通过环境变量HCCL\_CONNECT\_TIMEOUT增加设备间的建链超时时间。示例：
>```
>export HCCL_CONNECT_TIMEOUT=600
>```

## 函数原型<a name="zh-cn_topic_0000002001711534_section18389930"></a>

```
HcclResult HcclCreateSubCommConfig(HcclComm *comm, uint32_t rankNum, uint32_t *rankIds, uint64_t subCommId, uint32_t subCommRankId, HcclCommConfig *config, HcclComm *subComm)
```

## 参数说明<a name="zh-cn_topic_0000002001711534_section13189358"></a>

<a name="zh-cn_topic_0000002001711534_table24749807"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000002001711534_row60665573"><th class="cellrowborder" valign="top" width="17.61%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0000002001711534_p14964341"><a name="zh-cn_topic_0000002001711534_p14964341"></a><a name="zh-cn_topic_0000002001711534_p14964341"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="12.870000000000001%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0000002001711534_p4152081"><a name="zh-cn_topic_0000002001711534_p4152081"></a><a name="zh-cn_topic_0000002001711534_p4152081"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="69.52000000000001%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0000002001711534_p774306"><a name="zh-cn_topic_0000002001711534_p774306"></a><a name="zh-cn_topic_0000002001711534_p774306"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000002001711534_row13564174312568"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p14564134316565"><a name="zh-cn_topic_0000002001711534_p14564134316565"></a><a name="zh-cn_topic_0000002001711534_p14564134316565"></a>comm</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p95641043195610"><a name="zh-cn_topic_0000002001711534_p95641043195610"></a><a name="zh-cn_topic_0000002001711534_p95641043195610"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p16564154315618"><a name="zh-cn_topic_0000002001711534_p16564154315618"></a><a name="zh-cn_topic_0000002001711534_p16564154315618"></a>被切分的全局通信域。</p>
<p id="zh-cn_topic_0000002001711534_p429419337019"><a name="zh-cn_topic_0000002001711534_p429419337019"></a><a name="zh-cn_topic_0000002001711534_p429419337019"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row1206959155511"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p6206859185514"><a name="zh-cn_topic_0000002001711534_p6206859185514"></a><a name="zh-cn_topic_0000002001711534_p6206859185514"></a>rankNum</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p12068593559"><a name="zh-cn_topic_0000002001711534_p12068593559"></a><a name="zh-cn_topic_0000002001711534_p12068593559"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p192061359185514"><a name="zh-cn_topic_0000002001711534_p192061359185514"></a><a name="zh-cn_topic_0000002001711534_p192061359185514"></a>需要切分的子通信域中的rank数量。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row43502734719"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p1935132714473"><a name="zh-cn_topic_0000002001711534_p1935132714473"></a><a name="zh-cn_topic_0000002001711534_p1935132714473"></a>rankIds</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p535112718471"><a name="zh-cn_topic_0000002001711534_p535112718471"></a><a name="zh-cn_topic_0000002001711534_p535112718471"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p1258713452483"><a name="zh-cn_topic_0000002001711534_p1258713452483"></a><a name="zh-cn_topic_0000002001711534_p1258713452483"></a>子通信域中rank在全局通信域中的rank id组成的数组。</p>
<p id="zh-cn_topic_0000002001711534_p735142719472"><a name="zh-cn_topic_0000002001711534_p735142719472"></a><a name="zh-cn_topic_0000002001711534_p735142719472"></a><strong id="zh-cn_topic_0000002001711534_b16205134974918"><a name="zh-cn_topic_0000002001711534_b16205134974918"></a><a name="zh-cn_topic_0000002001711534_b16205134974918"></a>需要注意</strong>：该数组应当是有序的，数组中每个rank的下标将映射为其在子通信域的rank id。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row761312542469"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p1561325454610"><a name="zh-cn_topic_0000002001711534_p1561325454610"></a><a name="zh-cn_topic_0000002001711534_p1561325454610"></a>subCommId</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p96131954134613"><a name="zh-cn_topic_0000002001711534_p96131954134613"></a><a name="zh-cn_topic_0000002001711534_p96131954134613"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p154664534584"><a name="zh-cn_topic_0000002001711534_p154664534584"></a><a name="zh-cn_topic_0000002001711534_p154664534584"></a>当前子通信域标识，用户自定义。</p>
<a name="zh-cn_topic_0000002001711534_ul20633174410598"></a><a name="zh-cn_topic_0000002001711534_ul20633174410598"></a><ul id="zh-cn_topic_0000002001711534_ul20633174410598"><li>若未在config参数中配置子通信域名称“hcclCommName”，系统会使用“{全局通信域名}_sub_{subCommId}”作为子通信域名称，此种场景下，需要确保“subCommId”在全局通信域中保持唯一。</li><li>若在config参数中配置了子通信域名称“hcclCommName”，则优先以config中配置为准，此参数不再做校验。</li></ul>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row4219101917458"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p921911191455"><a name="zh-cn_topic_0000002001711534_p921911191455"></a><a name="zh-cn_topic_0000002001711534_p921911191455"></a>subCommRankId</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p18219131917451"><a name="zh-cn_topic_0000002001711534_p18219131917451"></a><a name="zh-cn_topic_0000002001711534_p18219131917451"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p1220141984513"><a name="zh-cn_topic_0000002001711534_p1220141984513"></a><a name="zh-cn_topic_0000002001711534_p1220141984513"></a>本rank在子通信域中的rank id。</p>
<p id="zh-cn_topic_0000002001711534_p114105013419"><a name="zh-cn_topic_0000002001711534_p114105013419"></a><a name="zh-cn_topic_0000002001711534_p114105013419"></a>请配置为当前rank在rankIds数组中的下标索引。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row11144211"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p240214111093"><a name="zh-cn_topic_0000002001711534_p240214111093"></a><a name="zh-cn_topic_0000002001711534_p240214111093"></a>config</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p940218116912"><a name="zh-cn_topic_0000002001711534_p940218116912"></a><a name="zh-cn_topic_0000002001711534_p940218116912"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p184021111894"><a name="zh-cn_topic_0000002001711534_p184021111894"></a><a name="zh-cn_topic_0000002001711534_p184021111894"></a>通信域配置项，包括buffer大小、确定性计算开关、通信域名称、通信算法编排展开位置等信息，配置参数需确保在合法值域内，关于HcclCommConfig中的详细参数含义及优先级可参见<a href="HcclCommConfig.md#ZH-CN_TOPIC_0000002486848108">HcclCommConfig</a>的定义。</p>
<p id="zh-cn_topic_0000002001711534_p4711134111213"><a name="zh-cn_topic_0000002001711534_p4711134111213"></a><a name="zh-cn_topic_0000002001711534_p4711134111213"></a>需要注意：传入的config必须先调用<a href="HcclCommConfigInit.md#ZH-CN_TOPIC_0000002486848092">HcclCommConfigInit</a>对其进行初始化。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000002001711534_row62284798"><td class="cellrowborder" valign="top" width="17.61%" headers="mcps1.1.4.1.1 "><p id="zh-cn_topic_0000002001711534_p1832323"><a name="zh-cn_topic_0000002001711534_p1832323"></a><a name="zh-cn_topic_0000002001711534_p1832323"></a>subComm</p>
</td>
<td class="cellrowborder" valign="top" width="12.870000000000001%" headers="mcps1.1.4.1.2 "><p id="zh-cn_topic_0000002001711534_p14200498"><a name="zh-cn_topic_0000002001711534_p14200498"></a><a name="zh-cn_topic_0000002001711534_p14200498"></a>输出</p>
</td>
<td class="cellrowborder" valign="top" width="69.52000000000001%" headers="mcps1.1.4.1.3 "><p id="zh-cn_topic_0000002001711534_p9389685"><a name="zh-cn_topic_0000002001711534_p9389685"></a><a name="zh-cn_topic_0000002001711534_p9389685"></a>将初始化后的子通信域以指针的信息回传给调用者。</p>
<p id="zh-cn_topic_0000002001711534_p2077615118500"><a name="zh-cn_topic_0000002001711534_p2077615118500"></a><a name="zh-cn_topic_0000002001711534_p2077615118500"></a>HcclComm类型的定义可参见<a href="HcclComm.md#ZH-CN_TOPIC_0000002519087957">HcclComm</a>。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="zh-cn_topic_0000002001711534_section51595365"></a>

[HcclResult](HcclResult.md#ZH-CN_TOPIC_0000002487008064)：接口成功返回HCCL\_SUCCESS，其他失败。

## 约束说明<a name="zh-cn_topic_0000002001711534_section61705107"></a>

-   属于同一子通信域的rank调用该接口时传入的rankNum、rankIds、subCommId、config均应相同。
-   不需要创建子通信域的rank应当传入rankIds=nullptr和subCommId=0xFFFFFFFF，此场景不会对“subCommId”参数做校验。
-   只支持从全局通信域切分子通信域，不支持在子通信域中进一步切分子通信域。

## 调用示例<a name="zh-cn_topic_0000002001711534_section10236329223"></a>

```c
// 初始化全局通信域
HcclComm globalHcclComm;
HcclCommInitClusterInfo(rankTableFile, devId, &globalHcclComm);
// 通信域配置
HcclCommConfig config;
HcclCommConfigInit(&config);
config.hcclBufferSize = 50;
strcpy(config.hcclCommName, "comm_1");
// 初始化子通信域
HcclComm hcclComm;
uint32_t rankIds[4] = {0, 1, 2, 3};  // 子通信域的 Rank 列表
HcclCreateSubCommConfig(&globalHcclComm, 4, rankIds, 1, devId, &config, &hcclComm);
```

