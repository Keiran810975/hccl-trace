# set\_split\_strategy\_by\_idx<a name="ZH-CN_TOPIC_0000001264913938"></a>

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

基于梯度的索引id，在集合通信group内设置反向梯度切分策略，实现allreduce的融合，用于进行集合通信的性能调优。

## 函数原型<a name="section19138102360"></a>

```
def set_split_strategy_by_idx(idxList, group="hccl_world_group")
```

## 参数说明<a name="section75724101161"></a>

<a name="zh-cn_topic_0146324969_table29998725"></a>
<table><thead align="left"><tr id="zh-cn_topic_0146324969_row8953505"><th class="cellrowborder" valign="top" width="20.76%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0146324969_p54145286"><a name="zh-cn_topic_0146324969_p54145286"></a><a name="zh-cn_topic_0146324969_p54145286"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.119999999999997%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0146324969_p23692060"><a name="zh-cn_topic_0146324969_p23692060"></a><a name="zh-cn_topic_0146324969_p23692060"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.12%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0146324969_p19480441"><a name="zh-cn_topic_0146324969_p19480441"></a><a name="zh-cn_topic_0146324969_p19480441"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row147134185511"><td class="cellrowborder" valign="top" width="20.76%" headers="mcps1.1.4.1.1 "><p id="p94727413556"><a name="p94727413556"></a><a name="p94727413556"></a>idxList</p>
</td>
<td class="cellrowborder" valign="top" width="17.119999999999997%" headers="mcps1.1.4.1.2 "><p id="p13472164165518"><a name="p13472164165518"></a><a name="p13472164165518"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.12%" headers="mcps1.1.4.1.3 "><p id="p947214455519"><a name="p947214455519"></a><a name="p947214455519"></a>list类型。</p>
<p id="p154731630165414"><a name="p154731630165414"></a><a name="p154731630165414"></a>梯度的索引id列表。</p>
<a name="ul13731114912358"></a><a name="ul13731114912358"></a><ul id="ul13731114912358"><li>梯度的索引id列表需为非负，升序序列。</li><li>梯度的索引id必须基于模型的总梯度参数个数去设置。索引id从0开始，最大值可通过以下方法获得：<a name="ul18523114342319"></a><a name="ul18523114342319"></a><ul id="ul18523114342319"><li>不调用梯度切分接口设置梯度切分策略进行训练，此时脚本会使用<a href="set_split_strategy_by_size.md">set_split_strategy_by_size</a>中的默认梯度切分方式进行训练。</li><li>训练结束后，在INFO级别的Host训练日志中搜索"segment result"关键字，可以得到梯度切分的分段的情况如: segment index list: [0,107] [108,159]。此分段序列中最大的数字（例如159）即总梯度参数索引最大的值。<div class="note" id="note16381121218218"><a name="note16381121218218"></a><a name="note16381121218218"></a><span class="notetitle"> 说明： </span><div class="notebody"><p id="p1638151262111"><a name="p1638151262111"></a><a name="p1638151262111"></a>完整的训练过程可能出现日志覆盖情况，此时用户可以修改“/var/log/npu/conf/slog/slog.conf”中的配置项<strong id="b18269114115236"><a name="b18269114115236"></a><a name="b18269114115236"></a>LogAgentMaxFileNum</strong>，提高Host侧保存日志文件的数量。或可以只进行一次迭代训练。</p>
</div></div>
</li></ul>
</li><li>梯度的切分最多支持8段。</li><li>比如模型总共有160个参数会产生梯度，需要切分[0,20]、[21,100]和[101,159]三段，则可以设置为idxList=[20,100,159]。</li></ul>
</td>
</tr>
<tr id="zh-cn_topic_0146324969_row41106249"><td class="cellrowborder" valign="top" width="20.76%" headers="mcps1.1.4.1.1 "><p id="p1010834583413"><a name="p1010834583413"></a><a name="p1010834583413"></a>group</p>
</td>
<td class="cellrowborder" valign="top" width="17.119999999999997%" headers="mcps1.1.4.1.2 "><p id="p11066451345"><a name="p11066451345"></a><a name="p11066451345"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.12%" headers="mcps1.1.4.1.3 "><p id="p126072037105211"><a name="p126072037105211"></a><a name="p126072037105211"></a>String类型。</p>
<p id="p4169123417514"><a name="p4169123417514"></a><a name="p4169123417514"></a>group名称，可以为"hccl_world_group"或自定义group，默认为"hccl_world_group"。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section26662142616"></a>

无。

## 约束说明<a name="section86843302218"></a>

-   调用该接口的rank必须在当前接口入参group定义的范围内，不在此范围内的rank调用该接口会失败。
-   若用户不调用梯度切分接口设置切分策略，则会按默认反向梯度切分策略切分。

    默认切分策略：按梯度数据量切分为2段，第一段数据量为96.54%，第二段数据量为3.46%（部分情况可能出现为一段情况）。

## 调用示例<a name="section1221995817532"></a>

```python
from hccl.split.api import *
set_split_strategy_by_idx([20, 100, 159], "group")
```

