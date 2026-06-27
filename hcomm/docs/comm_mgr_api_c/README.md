# 通信域管理接口列表（C语言）

HCCL提供了C语言的通信域管理接口，框架开发者可以通过这些接口进行单算子模式下的框架适配，实现分布式能力。

<a name="zh-cn_topic_0000001312721317_table1554562693420"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001312721317_row125461626123420"><th class="cellrowborder" valign="top" width="25.47%" id="mcps1.2.3.1.1"><p id="zh-cn_topic_0000001312721317_p8546826113410"><a name="zh-cn_topic_0000001312721317_p8546826113410"></a><a name="zh-cn_topic_0000001312721317_p8546826113410"></a><strong id="zh-cn_topic_0000001312721317_b225214248340"><a name="zh-cn_topic_0000001312721317_b225214248340"></a><a name="zh-cn_topic_0000001312721317_b225214248340"></a>接口</strong></p>
</th>
<th class="cellrowborder" valign="top" width="74.53%" id="mcps1.2.3.1.2"><p id="zh-cn_topic_0000001312721317_p10546122613347"><a name="zh-cn_topic_0000001312721317_p10546122613347"></a><a name="zh-cn_topic_0000001312721317_p10546122613347"></a><strong id="zh-cn_topic_0000001312721317_b132536244347"><a name="zh-cn_topic_0000001312721317_b132536244347"></a><a name="zh-cn_topic_0000001312721317_b132536244347"></a>简介</strong></p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001312721317_row794895782410"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1673318236501"><a name="zh-cn_topic_0000001312721317_p1673318236501"></a><a name="zh-cn_topic_0000001312721317_p1673318236501"></a><a href="./context/HcclCommInitClusterInfo.md">HcclCommInitClusterInfo</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p6949857132413"><a name="zh-cn_topic_0000001312721317_p6949857132413"></a><a name="zh-cn_topic_0000001312721317_p6949857132413"></a>基于rank table初始化HCCL，创建HCCL通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row154453368493"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p34466369493"><a name="zh-cn_topic_0000001312721317_p34466369493"></a><a name="zh-cn_topic_0000001312721317_p34466369493"></a><a href="./context/HcclCommInitClusterInfoConfig.md">HcclCommInitClusterInfoConfig</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p7446536164910"><a name="zh-cn_topic_0000001312721317_p7446536164910"></a><a name="zh-cn_topic_0000001312721317_p7446536164910"></a>基于rank table初始化HCCL，创建具有特定配置的HCCL通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row12335120142516"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p11533172420517"><a name="zh-cn_topic_0000001312721317_p11533172420517"></a><a name="zh-cn_topic_0000001312721317_p11533172420517"></a><a href="./context/HcclGetRootInfo.md">HcclGetRootInfo</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p1033512018251"><a name="zh-cn_topic_0000001312721317_p1033512018251"></a><a name="zh-cn_topic_0000001312721317_p1033512018251"></a>此接口需要在HCCL初始化接口<a href="./context/HcclCommInitRootInfo.md">HcclCommInitRootInfo</a>或<a href="./context/HcclCommInitRootInfoConfig.md">HcclCommInitRootInfoConfig</a>前调用，仅需在root节点调用，用于生成root节点的rank标识信息（HcclRootInfo）。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row8475340112611"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p3476194014267"><a name="zh-cn_topic_0000001312721317_p3476194014267"></a><a name="zh-cn_topic_0000001312721317_p3476194014267"></a><a href="./context/HcclCommInitRootInfo.md">HcclCommInitRootInfo</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p1547612404268"><a name="zh-cn_topic_0000001312721317_p1547612404268"></a><a name="zh-cn_topic_0000001312721317_p1547612404268"></a>根据rootInfo初始化HCCL，创建HCCL通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row108841212235"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p988412210235"><a name="zh-cn_topic_0000001312721317_p988412210235"></a><a name="zh-cn_topic_0000001312721317_p988412210235"></a><a href="./context/HcclCommInitRootInfoConfig.md">HcclCommInitRootInfoConfig</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p32089967"><a name="zh-cn_topic_0000001312721317_p32089967"></a><a name="zh-cn_topic_0000001312721317_p32089967"></a>根据rootInfo初始化HCCL，创建具有特定配置的HCCL通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row3905144172312"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p69059414234"><a name="zh-cn_topic_0000001312721317_p69059414234"></a><a name="zh-cn_topic_0000001312721317_p69059414234"></a><a href="./context/HcclCommConfigInit.md">HcclCommConfigInit</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p119051346233"><a name="zh-cn_topic_0000001312721317_p119051346233"></a><a name="zh-cn_topic_0000001312721317_p119051346233"></a>初始化通信域配置项，并将其中的可配置参数设为默认值。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row114031738102611"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1840318382266"><a name="zh-cn_topic_0000001312721317_p1840318382266"></a><a name="zh-cn_topic_0000001312721317_p1840318382266"></a><a href="./context/HcclCommInitAll.md">HcclCommInitAll</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p3403123816263"><a name="zh-cn_topic_0000001312721317_p3403123816263"></a><a name="zh-cn_topic_0000001312721317_p3403123816263"></a>单机通信场景中，通过一个进程统一创建多张卡的通信域（其中一张卡对应一个线程）。在初始化通信域的过程中，devices[0]作为root rank自动收集集群信息。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row250343610268"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1168119461959"><a name="zh-cn_topic_0000001312721317_p1168119461959"></a><a name="zh-cn_topic_0000001312721317_p1168119461959"></a><a href="./context/HcclCommDestroy.md">HcclCommDestroy</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p1250363613262"><a name="zh-cn_topic_0000001312721317_p1250363613262"></a><a name="zh-cn_topic_0000001312721317_p1250363613262"></a>销毁指定的HCCL通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row12943547114713"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p194334734715"><a name="zh-cn_topic_0000001312721317_p194334734715"></a><a name="zh-cn_topic_0000001312721317_p194334734715"></a><a href="./context/HcclGetRankSize.md">HcclGetRankSize</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p3943104774717"><a name="zh-cn_topic_0000001312721317_p3943104774717"></a><a name="zh-cn_topic_0000001312721317_p3943104774717"></a>查询当前集合通信域的rank总数。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row1121210508472"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p152138505479"><a name="zh-cn_topic_0000001312721317_p152138505479"></a><a name="zh-cn_topic_0000001312721317_p152138505479"></a><a href="./context/HcclGetRankId.md">HcclGetRankId</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p221319506475"><a name="zh-cn_topic_0000001312721317_p221319506475"></a><a name="zh-cn_topic_0000001312721317_p221319506475"></a>获取device在集合通信域中对应的rank序号。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row2913102219481"><td class="cellrowborder" valign="top" width="25.46%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p645175273118"><a href="./context/HcclBarrier.md">HcclBarrier</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p791372217484">将指定通信域内所有rank的stream阻塞，直到所有rank都下发执行该操作为止。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row148927214351"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p51823489259"><a name="zh-cn_topic_0000001312721317_p51823489259"></a><a name="zh-cn_topic_0000001312721317_p51823489259"></a><a href="./context/HcclSetConfig.md">HcclSetConfig</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p17893162119356"><a name="zh-cn_topic_0000001312721317_p17893162119356"></a><a name="zh-cn_topic_0000001312721317_p17893162119356"></a>进行集合通信相关配置，当前仅支持配置是否支持确定性计算。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row152201822143514"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p143133533256"><a name="zh-cn_topic_0000001312721317_p143133533256"></a><a name="zh-cn_topic_0000001312721317_p143133533256"></a><a href="./context/HcclGetConfig.md">HcclGetConfig</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p22211622103515"><a name="zh-cn_topic_0000001312721317_p22211622103515"></a><a name="zh-cn_topic_0000001312721317_p22211622103515"></a>获取集合通信相关配置。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row7408192253513"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1157695002514"><a name="zh-cn_topic_0000001312721317_p1157695002514"></a><a name="zh-cn_topic_0000001312721317_p1157695002514"></a><a href="./context/HcclGetCommName.md">HcclGetCommName</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p154098224358"><a name="zh-cn_topic_0000001312721317_p154098224358"></a><a name="zh-cn_topic_0000001312721317_p154098224358"></a>获取当前集合通信操作所在的通信域的名称。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row9744161812229"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1774461842217"><a name="zh-cn_topic_0000001312721317_p1774461842217"></a><a name="zh-cn_topic_0000001312721317_p1774461842217"></a><a href="./context/HcclGetCommConfigCapability.md">HcclGetCommConfigCapability</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p1745151817229"><a name="zh-cn_topic_0000001312721317_p1745151817229"></a><a name="zh-cn_topic_0000001312721317_p1745151817229"></a>该接口用于判断当前版本软件是否支持某项通信域初始化配置。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row9786142318275"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p47861223102715"><a name="zh-cn_topic_0000001312721317_p47861223102715"></a><a name="zh-cn_topic_0000001312721317_p47861223102715"></a><a href="./context/HcclCommSuspend.md">HcclCommSuspend</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p20786823132712"><a name="zh-cn_topic_0000001312721317_p20786823132712"></a><a name="zh-cn_topic_0000001312721317_p20786823132712"></a>当片上内存UCE（uncorrect error）故障时（ACL接口返回ACL_ERROR_RT_DEVICE_MTE_ERROR错误码），可调用本接口将通信域置为挂起状态。</p>
<p id="zh-cn_topic_0000001312721317_p206661725112816"><a name="zh-cn_topic_0000001312721317_p206661725112816"></a><a name="zh-cn_topic_0000001312721317_p206661725112816"></a>注意：本接口为预留接口，后续有可能变更，不支持开发者使用。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row7555192622711"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p45556265279"><a name="zh-cn_topic_0000001312721317_p45556265279"></a><a name="zh-cn_topic_0000001312721317_p45556265279"></a><a href="./context/HcclCommResume.md">HcclCommResume</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p14555122614276"><a name="zh-cn_topic_0000001312721317_p14555122614276"></a><a name="zh-cn_topic_0000001312721317_p14555122614276"></a>本接口用于恢复集合通信域的状态。</p>
<p id="zh-cn_topic_0000001312721317_p1534864312289"><a name="zh-cn_topic_0000001312721317_p1534864312289"></a><a name="zh-cn_topic_0000001312721317_p1534864312289"></a>注意：本接口为预留接口，后续有可能变更，不支持开发者使用。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row5507192317227"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p20508122315226"><a name="zh-cn_topic_0000001312721317_p20508122315226"></a><a name="zh-cn_topic_0000001312721317_p20508122315226"></a><a href="./context/HcclCreateSubCommConfig.md">HcclCreateSubCommConfig</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p class="msonormal" id="zh-cn_topic_0000001312721317_p105083237229"><a name="zh-cn_topic_0000001312721317_p105083237229"></a><a name="zh-cn_topic_0000001312721317_p105083237229"></a>基于既有的全局通信域，切分具有特定配置的子通信域。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row6182102113416"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p13182421742"><a name="zh-cn_topic_0000001312721317_p13182421742"></a><a name="zh-cn_topic_0000001312721317_p13182421742"></a><a href="./context/HcclCommWorkingDevNicSet.md">HcclCommWorkingDevNicSet</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p918272116418"><a name="zh-cn_topic_0000001312721317_p918272116418"></a><a name="zh-cn_topic_0000001312721317_p918272116418"></a>在集群场景下，配置通信域内的通信网卡。支持在同一NPU下，在某一Device网卡和备用网卡之间切换通信，备用网卡为同一NPU中的另一个Die网卡。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row10128328134511"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p11281428174510"><a name="zh-cn_topic_0000001312721317_p11281428174510"></a><a name="zh-cn_topic_0000001312721317_p11281428174510"></a><a href="./context/HcclCommSetMemoryRange.md">HcclCommSetMemoryRange</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p1812822813453"><a name="zh-cn_topic_0000001312721317_p1812822813453"></a><a name="zh-cn_topic_0000001312721317_p1812822813453"></a>用户通过aclrtReserveMemAddress接口成功申请虚拟内存后，可调用此接口通知HCCL预留的虚拟内存地址。调用此接口后，该虚拟内存对当前进程中的所有通信域可见。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row148812614453"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1148892664517"><a name="zh-cn_topic_0000001312721317_p1148892664517"></a><a name="zh-cn_topic_0000001312721317_p1148892664517"></a><a href="./context/HcclCommUnsetMemoryRange.md">HcclCommUnsetMemoryRange</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p1048822664517"><a name="zh-cn_topic_0000001312721317_p1048822664517"></a><a name="zh-cn_topic_0000001312721317_p1048822664517"></a>该接口用于通知HCCL通信域取消使用预留的虚拟内存。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row16228824174516"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1622812416455"><a name="zh-cn_topic_0000001312721317_p1622812416455"></a><a name="zh-cn_topic_0000001312721317_p1622812416455"></a><a href="./context/HcclCommActivateCommMemory.md">HcclCommActivateCommMemory</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p622802484520"><a name="zh-cn_topic_0000001312721317_p622802484520"></a><a name="zh-cn_topic_0000001312721317_p622802484520"></a>激活预留的虚拟内存，只有使用激活后的内存作为通信算子的输入、输出才可使能零拷贝功能。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row5387152112451"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1638812134517"><a name="zh-cn_topic_0000001312721317_p1638812134517"></a><a name="zh-cn_topic_0000001312721317_p1638812134517"></a><a href="./context/HcclCommDeactivateCommMemory.md">HcclCommDeactivateCommMemory</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p5388122112455"><a name="zh-cn_topic_0000001312721317_p5388122112455"></a><a name="zh-cn_topic_0000001312721317_p5388122112455"></a>将已经激活的虚拟内存反激活，反激活后如果再使用该地址进行集合通信，将不会使能零拷贝功能。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row53151442485"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p14315744124814"><a name="zh-cn_topic_0000001312721317_p14315744124814"></a><a name="zh-cn_topic_0000001312721317_p14315744124814"></a><a href="./context/HcclGetCommAsyncError.md">HcclGetCommAsyncError</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p10207124312514"><a name="zh-cn_topic_0000001312721317_p10207124312514"></a><a name="zh-cn_topic_0000001312721317_p10207124312514"></a>当集群信息中存在Device网口通信链路不稳定、出现网络拥塞的情况时，Device日志中会存在“error cqe”的打印，我们称这种错误为“RDMA ERROR CQE”错误。</p>
<p id="zh-cn_topic_0000001312721317_p178561454953"><a name="zh-cn_topic_0000001312721317_p178561454953"></a><a name="zh-cn_topic_0000001312721317_p178561454953"></a>当前版本，此接口仅支持查询通信域内是否存在“RDMA ERROR CQE”的错误。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001312721317_row1795645520353"><td class="cellrowborder" valign="top" width="25.47%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001312721317_p1695618559357"><a name="zh-cn_topic_0000001312721317_p1695618559357"></a><a name="zh-cn_topic_0000001312721317_p1695618559357"></a><a href="./context/HcclGetErrorString.md">HcclGetErrorString</a></p>
</td>
<td class="cellrowborder" valign="top" width="74.53%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001312721317_p1495712557356"><a name="zh-cn_topic_0000001312721317_p1495712557356"></a><a name="zh-cn_topic_0000001312721317_p1495712557356"></a>解析HcclResult类型的错误码。</p>
</td>
</tr>
</tbody>
</table>

