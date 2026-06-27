# set\_split\_strategy\_by\_size<a name="ZH-CN_TOPIC_0000001265233750"></a>

## 产品支持情况<a name="section10594071513"></a>

<a name="zh-cn_topic_0000001312713837_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001312713837_row20831180131817"><th class="cellrowborder" valign="top" width="57.86%" id="mcps1.1.3.1.1"><p id="zh-cn_topic_0000001312713837_p1883113061818"><a name="zh-cn_topic_0000001312713837_p1883113061818"></a><a name="zh-cn_topic_0000001312713837_p1883113061818"></a>产品</p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42.14%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001312713837_p783113012187"><a name="zh-cn_topic_0000001312713837_p783113012187"></a><a name="zh-cn_topic_0000001312713837_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001312713837_row220181016240"><td class="cellrowborder" valign="top" width="57.86%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001312713837_p48327011813"><a name="zh-cn_topic_0000001312713837_p48327011813"></a><a name="zh-cn_topic_0000001312713837_p48327011813"></a><span id="zh-cn_topic_0000001312713837_ph583230201815"><a name="zh-cn_topic_0000001312713837_ph583230201815"></a><a name="zh-cn_topic_0000001312713837_ph583230201815"></a><term id="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42.14%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001312713837_p7948163910184"><a name="zh-cn_topic_0000001312713837_p7948163910184"></a><a name="zh-cn_topic_0000001312713837_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312713837_row173226882415"><td class="cellrowborder" valign="top" width="57.86%" headers="mcps1.1.3.1.1 "><p id="zh-cn_topic_0000001312713837_p14832120181815"><a name="zh-cn_topic_0000001312713837_p14832120181815"></a><a name="zh-cn_topic_0000001312713837_p14832120181815"></a><span id="zh-cn_topic_0000001312713837_ph1292674871116"><a name="zh-cn_topic_0000001312713837_ph1292674871116"></a><a name="zh-cn_topic_0000001312713837_ph1292674871116"></a><term id="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001312713837_zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42.14%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001312713837_p19948143911820"><a name="zh-cn_topic_0000001312713837_p19948143911820"></a><a name="zh-cn_topic_0000001312713837_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="section15101187760"></a>

基于梯度数据量百分比，在集合通信group内设置反向梯度切分策略，实现allreduce的融合，用于进行集合通信的性能调优。

## 函数原型<a name="section19138102360"></a>

```
def set_split_strategy_by_size(dataSizeList, group="hccl_world_group")
```

## 参数说明<a name="section75724101161"></a>

<a name="zh-cn_topic_0146324969_table29998725"></a>
<table><thead align="left"><tr id="zh-cn_topic_0146324969_row8953505"><th class="cellrowborder" valign="top" width="20.7%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0146324969_p54145286"><a name="zh-cn_topic_0146324969_p54145286"></a><a name="zh-cn_topic_0146324969_p54145286"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.18%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0146324969_p23692060"><a name="zh-cn_topic_0146324969_p23692060"></a><a name="zh-cn_topic_0146324969_p23692060"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.12%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0146324969_p19480441"><a name="zh-cn_topic_0146324969_p19480441"></a><a name="zh-cn_topic_0146324969_p19480441"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row147134185511"><td class="cellrowborder" valign="top" width="20.7%" headers="mcps1.1.4.1.1 "><p id="p94727413556"><a name="p94727413556"></a><a name="p94727413556"></a>dataSizeList</p>
</td>
<td class="cellrowborder" valign="top" width="17.18%" headers="mcps1.1.4.1.2 "><p id="p13472164165518"><a name="p13472164165518"></a><a name="p13472164165518"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.12%" headers="mcps1.1.4.1.3 "><p id="p853634516545"><a name="p853634516545"></a><a name="p853634516545"></a>list类型。</p>
<p id="p947214455519"><a name="p947214455519"></a><a name="p947214455519"></a>梯度参数数据量百分比列表。</p>
<a name="ul1932616379374"></a><a name="ul1932616379374"></a><ul id="ul1932616379374"><li>梯度的索引id列表需为非负，且梯度数据量序列总百分比之和必须为100。</li><li>梯度的切分最多支持8段。</li><li>比如模型总共有150M梯度数据量，需要切分90M，30M，30M三段，则可以设置dataSizeList =[60,20,20]。</li></ul>
</td>
</tr>
<tr id="zh-cn_topic_0146324969_row41106249"><td class="cellrowborder" valign="top" width="20.7%" headers="mcps1.1.4.1.1 "><p id="p1010834583413"><a name="p1010834583413"></a><a name="p1010834583413"></a>group</p>
</td>
<td class="cellrowborder" valign="top" width="17.18%" headers="mcps1.1.4.1.2 "><p id="p11066451345"><a name="p11066451345"></a><a name="p11066451345"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.12%" headers="mcps1.1.4.1.3 "><p id="p493650133717"><a name="p493650133717"></a><a name="p493650133717"></a>String类型，最大长度为128字节，含结束符。</p>
<p id="p5203181563915"><a name="p5203181563915"></a><a name="p5203181563915"></a>group名称，可以为"hccl_world_group"或自定义group，默认为"hccl_world_group"。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section26662142616"></a>

无。

## 约束说明<a name="section86843302218"></a>

-   调用该接口的rank必须在当前接口入参group定义的范围内，不在此范围内的rank调用该接口会失败。
-   在同时基于梯度数据量百分比及梯度的索引id设置反向梯度切分策略时，以基于梯度数据量百分比设置结果优先。
-   若用户不调用梯度切分接口设置切分策略，则会按默认反向梯度切分策略切分。

    默认切分策略：ResNet50的最优切分位置，即按梯度数据量切分为2段，第一段数据量为96.54%，第二段数据量为3.46%。

## 调用示例<a name="section1221995817532"></a>

```python
from hccl.split.api import *
set_split_strategy_by_size([60, 20, 20], "group")
```

