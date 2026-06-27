# create\_group<a name="ZH-CN_TOPIC_0000001312713837"></a>

## 产品支持情况<a name="section10594071513"></a>

<a name="table38301303189"></a>
<table><thead align="left"><tr id="row20831180131817"><th class="cellrowborder" valign="top" width="57.86%" id="mcps1.1.3.1.1"><p id="p1883113061818"><a name="p1883113061818"></a><a name="p1883113061818"></a>产品</p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42.14%" id="mcps1.1.3.1.2"><p id="p783113012187"><a name="p783113012187"></a><a name="p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="row220181016240"><td class="cellrowborder" valign="top" width="57.86%" headers="mcps1.1.3.1.1 "><p id="p48327011813"><a name="p48327011813"></a><a name="p48327011813"></a><span id="ph583230201815"><a name="ph583230201815"></a><a name="ph583230201815"></a><term id="zh-cn_topic_0000001312391781_term1253731311225"><a name="zh-cn_topic_0000001312391781_term1253731311225"></a><a name="zh-cn_topic_0000001312391781_term1253731311225"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42.14%" headers="mcps1.1.3.1.2 "><p id="p7948163910184"><a name="p7948163910184"></a><a name="p7948163910184"></a>√</p>
</td>
</tr>
<tr id="row173226882415"><td class="cellrowborder" valign="top" width="57.86%" headers="mcps1.1.3.1.1 "><p id="p14832120181815"><a name="p14832120181815"></a><a name="p14832120181815"></a><span id="ph1292674871116"><a name="ph1292674871116"></a><a name="ph1292674871116"></a><term id="zh-cn_topic_0000001312391781_term11962195213215"><a name="zh-cn_topic_0000001312391781_term11962195213215"></a><a name="zh-cn_topic_0000001312391781_term11962195213215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42.14%" headers="mcps1.1.3.1.2 "><p id="p19948143911820"><a name="p19948143911820"></a><a name="p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

> [!NOTE]说明
> 针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，仅支持Atlas 800T A2 训练服务器、Atlas 900 A2 PoD 集群基础单元、Atlas 200T A2 Box16 异构子框。

## 功能说明<a name="section15101187760"></a>

创建集合通信用户自定义group。

如果开发者不调用此接口创建用户自定义group，则默认将所有参与集群训练的设备创建为全局的hccl\_world\_group。

group为参与集合通信的进程组，其中：

-   hccl\_world\_group：默认的全局group，包含所有参与集合通信的rank，由HCCL自动创建。
-   自定义group：hccl\_world\_group包含的进程组的子集。

## 函数原型<a name="section19138102360"></a>

```
def create_group(group, rank_num, rank_ids)
```

## 参数说明<a name="section75724101161"></a>

<a name="zh-cn_topic_0146324969_table29998725"></a>
<table><thead align="left"><tr id="zh-cn_topic_0146324969_row8953505"><th class="cellrowborder" valign="top" width="18.63%" id="mcps1.1.4.1.1"><p id="zh-cn_topic_0146324969_p54145286"><a name="zh-cn_topic_0146324969_p54145286"></a><a name="zh-cn_topic_0146324969_p54145286"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="14.66%" id="mcps1.1.4.1.2"><p id="zh-cn_topic_0146324969_p23692060"><a name="zh-cn_topic_0146324969_p23692060"></a><a name="zh-cn_topic_0146324969_p23692060"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="66.71000000000001%" id="mcps1.1.4.1.3"><p id="zh-cn_topic_0146324969_p19480441"><a name="zh-cn_topic_0146324969_p19480441"></a><a name="zh-cn_topic_0146324969_p19480441"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0146324969_row41106249"><td class="cellrowborder" valign="top" width="18.63%" headers="mcps1.1.4.1.1 "><p id="p1010834583413"><a name="p1010834583413"></a><a name="p1010834583413"></a>group</p>
</td>
<td class="cellrowborder" valign="top" width="14.66%" headers="mcps1.1.4.1.2 "><p id="p11066451345"><a name="p11066451345"></a><a name="p11066451345"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="66.71000000000001%" headers="mcps1.1.4.1.3 "><p id="p126072037105211"><a name="p126072037105211"></a><a name="p126072037105211"></a>String类型，最大长度为128字节，含结束符。</p>
<p id="p18177229567"><a name="p18177229567"></a><a name="p18177229567"></a>group名称，集合通信group的标识，不能为默认全局group名字“hccl_world_group”，如果用户传入的group名字是“hccl_world_group”，会创建失败。</p>
</td>
</tr>
<tr id="zh-cn_topic_0146324969_row46369059"><td class="cellrowborder" valign="top" width="18.63%" headers="mcps1.1.4.1.1 "><p id="p33531427213"><a name="p33531427213"></a><a name="p33531427213"></a>rank_num</p>
</td>
<td class="cellrowborder" valign="top" width="14.66%" headers="mcps1.1.4.1.2 "><p id="p161002045193414"><a name="p161002045193414"></a><a name="p161002045193414"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="66.71000000000001%" headers="mcps1.1.4.1.3 "><p id="p1290812392242"><a name="p1290812392242"></a><a name="p1290812392242"></a>int类型。</p>
<p id="p1249275185110"><a name="p1249275185110"></a><a name="p1249275185110"></a>组成该group的rank数量。</p>
<p id="p17811434142413"><a name="p17811434142413"></a><a name="p17811434142413"></a>最大值为32768。</p>
</td>
</tr>
<tr id="row1546418572119"><td class="cellrowborder" valign="top" width="18.63%" headers="mcps1.1.4.1.1 "><p id="p19465145172115"><a name="p19465145172115"></a><a name="p19465145172115"></a>rank_ids</p>
</td>
<td class="cellrowborder" valign="top" width="14.66%" headers="mcps1.1.4.1.2 "><p id="p114651159214"><a name="p114651159214"></a><a name="p114651159214"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="66.71000000000001%" headers="mcps1.1.4.1.3 "><p id="p194881567257"><a name="p194881567257"></a><a name="p194881567257"></a>list类型。</p>
<p id="p28368299334"><a name="p28368299334"></a><a name="p28368299334"></a>组成该group的world_rank_id列表。</p>
<p id="p15751133182617"><a name="p15751133182617"></a><a name="p15751133182617"></a>在不同单板类型上，有不同的限制。</p>
<div class="p" id="p1613649124016"><a name="p1613649124016"></a><a name="p1613649124016"></a> 针对<span id="ph14880920154918"><a name="ph14880920154918"></a><a name="ph14880920154918"></a><term id="zh-cn_topic_0000001312391781_term16184138172215"><a name="zh-cn_topic_0000001312391781_term16184138172215"></a><a name="zh-cn_topic_0000001312391781_term16184138172215"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>：<a name="ul27072714012"></a><a name="ul27072714012"></a><ul id="ul27072714012"><li>对于Server单机场景，rank_ids无限制条件。</li><li>对于Server集群场景，rank_ids需满足如下条件：<p id="p12564111118917"><a name="p12564111118917"></a><a name="p12564111118917"></a>建议各Server要选取相同数量的rank（数量大小无要求），且各Server选取的rank对应位置要相等（即rank id按8取模相等）。若各Server选取的rank数量不同，会造成性能劣化。</p>
<p id="p651125764512"><a name="p651125764512"></a><a name="p651125764512"></a>举例：</p>
<p id="p19312223152212"><a name="p19312223152212"></a><a name="p19312223152212"></a>假设对三台Server创建group，三台Server的rank id分别为：</p>
<p id="p1922461117466"><a name="p1922461117466"></a><a name="p1922461117466"></a>{0,1,2,3,4,5,6,7}</p>
<p id="p19922151234615"><a name="p19922151234615"></a><a name="p19922151234615"></a>{8,9,10,11,12,13,14,15}</p>
<p id="p1294218321415"><a name="p1294218321415"></a><a name="p1294218321415"></a>{16,17,18,19,20,21,22,23}</p>
<p id="p1064861754619"><a name="p1064861754619"></a><a name="p1064861754619"></a>则满足要求的rank_ids列表可以是：</p>
<p id="p194253211115"><a name="p194253211115"></a><a name="p194253211115"></a>rank_ids=[1,9,17]</p>
<p id="p37289201467"><a name="p37289201467"></a><a name="p37289201467"></a>rank_ids=[1,2,9,10,17,18]</p>
<p id="p1194217322110"><a name="p1194217322110"></a><a name="p1194217322110"></a>rank_ids=[4,5,6,7,12,13,14,15,20,21,22,23]</p>
</li></ul>
</div>
<p id="p6916121605114"><a name="p6916121605114"></a><a name="p6916121605114"></a> 针对<span id="ph13754548217"><a name="ph13754548217"></a><a name="ph13754548217"></a><term id="zh-cn_topic_0000001312391781_term1253731311225_1"><a name="zh-cn_topic_0000001312391781_term1253731311225_1"></a><a name="zh-cn_topic_0000001312391781_term1253731311225_1"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>：建议每个超节点中的Server数量一致，每个Server中的rank数量一致，若不一致，会造成性能劣化。</p>
<p id="p67038351313"><a name="p67038351313"></a><a name="p67038351313"></a><strong id="b1293616381436"><a name="b1293616381436"></a><a name="b1293616381436"></a>补充说明：</strong></p>
<p id="p115715491633"><a name="p115715491633"></a><a name="p115715491633"></a>建议rank_ids按照Device物理连接顺序进行排序，即将物理连接上较近的device编排在一起。例如，若device_ip按照物理连接从小到大设置，则rank_ids也建议按照从小到大的顺序设置。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section26662142616"></a>

无。

## 约束说明<a name="section12970635104311"></a>

-   必须在集合通信初始化完成之后调用。
-   调用该接口的rank必须在当前接口入参group定义的范围内，不在此范围内的rank调用该接口会失败。

## 调用示例<a name="section1221995817532"></a>

```python
from hccl.manage.api import create_group
create_group("myGroup", 4, [0, 1, 2, 3])
```

