# 通信算子开发接口列表

通信算子开发接口分为控制面接口与数据面接口。

-   控制面接口：提供拓扑信息查询、通信资源管理等功能。
-   数据面接口：提供本地操作、算子间同步、通信操作等数据搬运和计算功能。

开发者可在“include/hccl”目录中查看通信算子开发接口的定义。

-   hccl\_rank\_graph.h：控制面的拓扑信息查询接口定义文件。
-   hccl\_res.h：控制面的资源管理定义文件。
-   hcomm\_primitives.h：数据面接口定义文件。

## 控制面接口<a name="section6759577142"></a>

<a name="table838742351912"></a>
<table><thead align="left"><tr id="row14387152319190"><th class="cellrowborder" valign="top" width="12.471247124712471%" id="mcps1.1.4.1.1"><p id="p138714238195"><a name="p138714238195"></a><a name="p138714238195"></a>分类</p>
</th>
<th class="cellrowborder" valign="top" width="27.992799279927993%" id="mcps1.1.4.1.2"><p id="p438812316190"><a name="p438812316190"></a><a name="p438812316190"></a>接口</p>
</th>
<th class="cellrowborder" valign="top" width="59.53595359535954%" id="mcps1.1.4.1.3"><p id="p1338892315199"><a name="p1338892315199"></a><a name="p1338892315199"></a>简介</p>
</th>
</tr>
</thead>
<tbody><tr id="row43881423151920"><td class="cellrowborder" rowspan="8" valign="top" width="12.471247124712471%" headers="mcps1.1.4.1.1 "><p id="p5388122301918"><a name="p5388122301918"></a><a name="p5388122301918"></a>拓扑信息查询</p>
</td>
<td class="cellrowborder" valign="top" width="27.992799279927993%" headers="mcps1.1.4.1.2 "><p id="p19388182315195"><a name="p19388182315195"></a><a name="p19388182315195"></a><a href="./context/HcclGetRankId.md">HcclGetRankId</a></p>
</td>
<td class="cellrowborder" valign="top" width="59.53595359535954%" headers="mcps1.1.4.1.3 "><p class="msonormal" id="p23881523111913"><a name="p23881523111913"></a><a name="p23881523111913"></a>获取Device在指定通信域中对应的rank序号。</p>
</td>
</tr>
<tr id="row938882319191"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p038813231196"><a name="p038813231196"></a><a name="p038813231196"></a><a href="./context/HcclGetRankSize.md">HcclGetRankSize</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p class="msonormal" id="p738812310190"><a name="p738812310190"></a><a name="p738812310190"></a>查询指定通信域的rank数量。</p>
</td>
</tr>
<tr id="row938862315192"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1538872318194"><a name="p1538872318194"></a><a name="p1538872318194"></a><a href="./context/HcclRankGraphGetLayers.md">HcclRankGraphGetLayers</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p1338822314198"><a name="p1338822314198"></a><a name="p1338822314198"></a>查询包含当前rank的拓扑层级编号列表以及拓扑层级数量。</p>
</td>
</tr>
<tr id="row179421819913"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p39425119911"><a name="p39425119911"></a><a name="p39425119911"></a><a href="./context/HcclRankGraphGetRanksByLayer.md">HcclRankGraphGetRanksByLayer</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p18942101592"><a name="p18942101592"></a><a name="p18942101592"></a>给定通信域和拓扑层级编号，返回该层级下本rank所在拓扑实例的所有rank编号列表以及rank数量。</p>
</td>
</tr>
<tr id="row16388172381917"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1199112527913"><a name="p1199112527913"></a><a name="p1199112527913"></a><a href="./context/HcclRankGraphGetRankSizeByLayer.md">HcclRankGraphGetRankSizeByLayer</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p1388623111915"><a name="p1388623111915"></a><a name="p1388623111915"></a>给定通信域和拓扑层级编号，返回该层级下本rank所在拓扑实例的rank数量。</p>
</td>
</tr>
<tr id="row73741148152013"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p183741048172015"><a name="p183741048172015"></a><a name="p183741048172015"></a><a href="./context/HcclRankGraphGetTopoTypeByLayer.md">HcclRankGraphGetTopoTypeByLayer</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p11375164816208"><a name="p11375164816208"></a><a name="p11375164816208"></a>给定通信域和拓扑层级编号，返回本rank所在拓扑层级中的拓扑类型。</p>
</td>
</tr>
<tr id="row1848755018201"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p969820588203"><a name="p969820588203"></a><a name="p969820588203"></a><a href="./context/HcclRankGraphGetInstSizeListByLayer.md">HcclRankGraphGetInstSizeListByLayer</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p204871650132015"><a name="p204871650132015"></a><a name="p204871650132015"></a>给定通信域和拓扑层级编号，查询该层级下的拓扑实例数量，以及每个实例包含的rank数量。</p>
</td>
</tr>
<tr id="row1140116122119"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1240261152115"><a name="p1240261152115"></a><a name="p1240261152115"></a><a href="./context/HcclRankGraphGetLinks.md">HcclRankGraphGetLinks</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p12402181102118"><a name="p12402181102118"></a><a name="p12402181102118"></a>给定通信域和拓扑层级编号，查询源rank和目的rank之间的通信连接信息。</p>
</td>
</tr>
<tr id="row742311333215"><td class="cellrowborder" rowspan="9" valign="top" width="12.471247124712471%" headers="mcps1.1.4.1.1 "><p id="p242333319216"><a name="p242333319216"></a><a name="p242333319216"></a>资源管理</p>
</td>
<td class="cellrowborder" valign="top" width="27.992799279927993%" headers="mcps1.1.4.1.2 "><p id="p12423123332111"><a name="p12423123332111"></a><a name="p12423123332111"></a><a href="./context/HcclGetHcclBuffer.md">HcclGetHcclBuffer</a></p>
</td>
<td class="cellrowborder" valign="top" width="59.53595359535954%" headers="mcps1.1.4.1.3 "><p id="p116901312552"><a name="p116901312552"></a><a name="p116901312552"></a>获取通信域中的HCCL通信内存。</p>
</td>
</tr>
<tr id="row6794637132116"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p4794037132119"><a name="p4794037132119"></a><a name="p4794037132119"></a><a href="./context/HcclThreadAcquire.md">HcclThreadAcquire</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p752918075011"><a name="p752918075011"></a><a name="p752918075011"></a>基于通信域获取通信线程。</p>
</td>
</tr>
<tr id="row151851945132115"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p14185144520212"><a name="p14185144520212"></a><a name="p14185144520212"></a><a href="./context/HcclThreadAcquireWithStream.md">HcclThreadAcquireWithStream</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p1618517457217"><a name="p1618517457217"></a><a name="p1618517457217"></a>基于已有runtime stream获取指定notifyNum的通信线程资源。</p>
</td>
</tr>
<tr><td><p><a href="./context/HcclChannelDescInit.md">HcclChannelDescInit</a></p></td>
<td><p>初始化通信通道描述列表。</p></td>
</tr>
<tr id="row17185104582115"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p171851045132116"><a name="p171851045132116"></a><a name="p171851045132116"></a><a href="./context/HcclChannelAcquire.md">HcclChannelAcquire</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p1185104518213"><a name="p1185104518213"></a><a name="p1185104518213"></a>基于通信域获取多个通信通道，如果通信域中没有对应的通信通道则直接创建。</p>
</td>
</tr>
<tr id="row11214418182212"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p18214218142219"><a name="p18214218142219"></a><a name="p18214218142219"></a><a href="./context/HcclChannelGetHcclBuffer.md">HcclChannelGetHcclBuffer</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p4542103415538"><a name="p4542103415538"></a><a name="p4542103415538"></a>获取指定channel对端的HCCL通信内存。</p>
</td>
</tr>
<tr id="row6214111882214"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p182141618102220"><a name="p182141618102220"></a><a name="p182141618102220"></a><a href="./context/HcclEngineCtxCreate.md">HcclEngineCtxCreate</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p8214151842216"><a name="p8214151842216"></a><a name="p8214151842216"></a>指定通信域与通信引擎，使用特定标签创建对应的通信引擎上下文。</p>
</td>
</tr>
<tr id="row1521431819228"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p14214518192216"><a name="p14214518192216"></a><a name="p14214518192216"></a><a href="./context/HcclEngineCtxGet.md">HcclEngineCtxGet</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p14214151819221"><a name="p14214151819221"></a><a name="p14214151819221"></a>指定通信域和通信引擎，通过通信引擎上下文标签获取对应的通信引擎上下文。</p>
</td>
</tr>
<tr id="row11214121892215"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p11215618192211"><a name="p11215618192211"></a><a name="p11215618192211"></a><a href="./context/HcclEngineCtxCopy.md">HcclEngineCtxCopy</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p4215418132214"><a name="p4215418132214"></a><a name="p4215418132214"></a>指定通信域、通信引擎与通信引擎上下文标签，将Host侧内存数据拷贝至对应的通信引擎上下文中。</p>
</td>
</tr>
</tbody>
</table>

## 数据面接口<a name="section1279411619159"></a>

<a name="table72518298197"></a>
<table><thead align="left"><tr id="row1925132913197"><th class="cellrowborder" valign="top" width="10.25102510251025%" id="mcps1.1.4.1.1"><p id="p1625115299199"><a name="p1625115299199"></a><a name="p1625115299199"></a>分类</p>
</th>
<th class="cellrowborder" valign="top" width="30.643064306430645%" id="mcps1.1.4.1.2"><p id="p162515299199"><a name="p162515299199"></a><a name="p162515299199"></a>接口</p>
</th>
<th class="cellrowborder" valign="top" width="59.10591059105911%" id="mcps1.1.4.1.3"><p id="p0251929191916"><a name="p0251929191916"></a><a name="p0251929191916"></a>简介</p>
</th>
</tr>
</thead>
<tbody><tr id="row17251152920194"><td class="cellrowborder" rowspan="6" valign="top" width="10.25102510251025%" headers="mcps1.1.4.1.1 "><p id="p201084911314"><a name="p201084911314"></a><a name="p201084911314"></a>本地操作</p>
</td>
<td class="cellrowborder" valign="top" width="30.643064306430645%" headers="mcps1.1.4.1.2 "><p id="p13251142915197"><a name="p13251142915197"></a><a name="p13251142915197"></a><a href="./context/HcommLocalCopyOnThread.md">HcommLocalCopyOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" width="59.10591059105911%" headers="mcps1.1.4.1.3 "><p id="p122515299193"><a name="p122515299193"></a><a name="p122515299193"></a>提供本地内存拷贝功能，将src指向的长度为len的内存数据，拷贝到dst所指向的相同长度的内存中。</p>
</td>
</tr>
<tr id="row20251142941914"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p825272951911"><a name="p825272951911"></a><a name="p825272951911"></a><a href="./context/HcommLocalReduceOnThread.md">HcommLocalReduceOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p6252929181912"><a name="p6252929181912"></a><a name="p6252929181912"></a>提供本地归约操作，将src指向的长度为count*sizeof(dataType)的内存数据，与dst所指向的相同长度的内存数据进行reduceOp操作，并将结果输出到dst中。</p>
</td>
</tr>
<tr id="row32521929161910"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p22521529121914"><a name="p22521529121914"></a><a name="p22521529121914"></a><a href="./context/HcommThreadNotifyRecordOnThread.md">HcommThreadNotifyRecordOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p113741518183219"><a name="p113741518183219"></a><a name="p113741518183219"></a>向其他Thread发送同步信号，主要用于多Thread之间的同步等待场景。</p>
</td>
</tr>
<tr id="row14252329191910"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p52521299192"><a name="p52521299192"></a><a name="p52521299192"></a><a href="./context/HcommThreadNotifyWaitOnThread.md">HcommThreadNotifyWaitOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p18660202219351"><a name="p18660202219351"></a><a name="p18660202219351"></a>等待同步信号，该接口会阻塞等待Thread的运行，直到指定的Notify被record完成。</p>
</td>
</tr>
<tr id="row617020378258"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p2017153715250"><a name="p2017153715250"></a><a name="p2017153715250"></a><a href="./context/HcommAclrtNotifyRecordOnThread.md">HcommAclrtNotifyRecordOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p12171143710258"><a name="p12171143710258"></a><a name="p12171143710258"></a>基于acl接口创建的Notify发送同步信号。</p>
</td>
</tr>
<tr id="row954018394254"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1254073942519"><a name="p1254073942519"></a><a name="p1254073942519"></a><a href="./context/HcommAclrtNotifyWaitOnThread.md">HcommAclrtNotifyWaitOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p13540103915253"><a name="p13540103915253"></a><a name="p13540103915253"></a>基于acl接口创建的Notify等待同步信号。</p>
</td>
</tr>
<tr id="row858112548511"><td class="cellrowborder" rowspan="6" valign="top" width="10.25102510251025%" headers="mcps1.1.4.1.1 "><p id="p1458116542512"><a name="p1458116542512"></a><a name="p1458116542512"></a>通信操作</p>
</td>
<td class="cellrowborder" valign="top" width="30.643064306430645%" headers="mcps1.1.4.1.2 "><p id="p1758114541952"><a name="p1758114541952"></a><a name="p1758114541952"></a><a href="./context/HcommWriteOnThread.md">HcommWriteOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" width="59.10591059105911%" headers="mcps1.1.4.1.3 "><p id="p45819544515"><a name="p45819544515"></a><a name="p45819544515"></a>向channel上的指定内存写数据，将src中长度为len的内存数据写入dst所指向的相同长度的内存区域。接口调用方为src所在节点，该接口为异步接口。</p>
</td>
</tr>
<tr id="row89711056953"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p169712561858"><a name="p169712561858"></a><a name="p169712561858"></a><a href="./context/HcommWriteReduceOnThread.md">HcommWriteReduceOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p11971145611516"><a name="p11971145611516"></a><a name="p11971145611516"></a>向channel上的指定内存写数据，将src中长度为count*sizeof(dataType)的内存数据，与dst所指向的相同长度的内存数据进行reduceOp操作，并将结果输出到dst中。接口调用方为src所在节点。</p>
</td>
</tr>
<tr id="row6693131413620"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p369371419618"><a name="p369371419618"></a><a name="p369371419618"></a><a href="./context/HcommReadOnThread.md">HcommReadOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p1969471412614"><a name="p1969471412614"></a><a name="p1969471412614"></a>从channel上的指定内存读数据，从src中读取长度为len的内存数据，并写入dst。接口调用方为dst所在节点，为异步接口。</p>
</td>
</tr>
<tr id="row196941214364"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p11694131417616"><a name="p11694131417616"></a><a name="p11694131417616"></a><a href="./context/HcommReadReduceOnThread.md">HcommReadReduceOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p869410141366"><a name="p869410141366"></a><a name="p869410141366"></a>从channel上的指定内存读数据，从src中读取长度为count*sizeof(dataType)的内存数据，与dst所指向的相同长度的内存数据进行reduceOp操作，并将结果输出到dst中。接口调用方为dst所在节点。</p>
</td>
</tr>
<tr id="row124601318666"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1746011183610"><a name="p1746011183610"></a><a name="p1746011183610"></a><a href="./context/HcommChannelNotifyRecordOnThread.md">HcommChannelNotifyRecordOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p74551789463"><a name="p74551789463"></a><a name="p74551789463"></a>发送同步信号，在Thread上记录一个Notify。该接口为同步接口，主要用于Channe两端同步等待场景。</p>
</td>
</tr>
<tr id="row14607183619"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p124604181664"><a name="p124604181664"></a><a name="p124604181664"></a><a href="./context/HcommChannelNotifyWaitOnThread.md">HcommChannelNotifyWaitOnThread</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p12230134713466"><a name="p12230134713466"></a><a name="p12230134713466"></a>等待同步信号，阻塞等待Thread的运行，直到指定的Notify完成。</p>
</td>
</tr>
<tr id="row146422393297"><td class="cellrowborder" rowspan="4" valign="top" width="10.25102510251025%" headers="mcps1.1.4.1.1 "><p id="p1446010181767"><a name="p1446010181767"></a><a name="p1446010181767"></a>其他</p>
</td>
<td class="cellrowborder" valign="top" width="30.643064306430645%" headers="mcps1.1.4.1.2 "><p id="p864243932911"><a name="p864243932911"></a><a name="p864243932911"></a><a href="./context/HcommBatchModeStart.md">HcommBatchModeStart</a></p>
</td>
<td class="cellrowborder" valign="top" width="59.10591059105911%" headers="mcps1.1.4.1.3 "><p id="p116421539132918"><a name="p116421539132918"></a><a name="p116421539132918"></a>该接口用于开启批量模式，在HcommBatchModeStart和HcommBatchModeEnd之间的所有数据面接口调用（如 HcommLocalCopy、HcommWrite 等）将被缓存，不会立即执行。所有操作将在调用HcommBatchModeEnd时统一提交并执行。</p>
</td>
</tr>
<tr id="row18460181813611"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p1461101814617"><a name="p1461101814617"></a><a name="p1461101814617"></a><a href="./context/HcommBatchModeEnd.md">HcommBatchModeEnd</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p94611187620"><a name="p94611187620"></a><a name="p94611187620"></a>该接口用于提交并触发批量模式下缓存的所有操作的执行。所有在HcommBatchModeStart和HcommBatchModeEnd之间的数据面接口调用操作将在此时统一执行。</p>
</td>
</tr>
<tr id="row5586924966"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p758611241863"><a name="p758611241863"></a><a name="p758611241863"></a><a href="./context/HcommAcquireComm.md">HcommAcquireComm</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p125867241666"><a name="p125867241666"></a><a name="p125867241666"></a>根据传入的commId获取对应通信域，并对该通信域加锁，防止该通信域被重复获取。</p>
</td>
</tr>
<tr id="row45863249620"><td class="cellrowborder" valign="top" headers="mcps1.1.4.1.1 "><p id="p145869241463"><a name="p145869241463"></a><a name="p145869241463"></a><a href="./context/HcommReleaseComm.md">HcommReleaseComm</a></p>
</td>
<td class="cellrowborder" valign="top" headers="mcps1.1.4.1.2 "><p id="p135861624662"><a name="p135861624662"></a><a name="p135861624662"></a>根据传入的commId，查找对应通信域，并释放锁。</p>
</td>
</tr>
</tbody>
</table>

