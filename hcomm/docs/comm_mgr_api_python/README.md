# 通信域管理接口列表（Python语言）

HCCL提供了Python语言的通信域管理接口与梯度切分接口，用于实现图模式下的框架适配。当前仅用于TensorFlow网络在昇腾AI处理器执行分布式优化。

## Python接口列表<a name="section3399135591812"></a>

<a name="table6773840112311"></a>
<table><thead align="left"><tr id="row107737406237"><th class="cellrowborder" valign="top" width="31.790000000000003%" id="mcps1.1.3.1.1"><p id="p8773340102314"><a name="p8773340102314"></a><a name="p8773340102314"></a>接口</p>
</th>
<th class="cellrowborder" valign="top" width="68.21000000000001%" id="mcps1.1.3.1.2"><p id="p11773640112311"><a name="p11773640112311"></a><a name="p11773640112311"></a>简介</p>
</th>
</tr>
</thead>
<tbody><tr id="row677314052314"><td class="cellrowborder" colspan="2" valign="top" headers="mcps1.1.3.1.1 mcps1.1.3.1.2 "><p id="p9774164042317"><a name="p9774164042317"></a><a name="p9774164042317"></a><strong id="b239632119310"><a name="b239632119310"></a><a name="b239632119310"></a>通信域管理</strong></p>
</td>
</tr>
<tr id="row27741440172318"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p97749408231"><a name="p97749408231"></a><a name="p97749408231"></a><a href="./context/create_group.md">create_group</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p157747404232"><a name="p157747404232"></a><a name="p157747404232"></a>创建集合通信用户自定义group。</p>
</td>
</tr>
<tr id="row977434010230"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p207741408230"><a name="p207741408230"></a><a name="p207741408230"></a><a href="./context/destroy_group.md">destroy_group</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p877414018233"><a name="p877414018233"></a><a name="p877414018233"></a>销毁集合通信用户自定义group。</p>
</td>
</tr>
<tr id="row97747407232"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p19774540102317"><a name="p19774540102317"></a><a name="p19774540102317"></a><a href="./context/get_rank_size.md">get_rank_size</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p17749408232"><a name="p17749408232"></a><a name="p17749408232"></a>获取group内的rank数量（即Device数量）。</p>
</td>
</tr>
<tr id="row117741740142315"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p17774940172312"><a name="p17774940172312"></a><a name="p17774940172312"></a><a href="./context/get_local_rank_size.md">get_local_rank_size</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p2077404072316"><a name="p2077404072316"></a><a name="p2077404072316"></a>获取group内device所在服务器内的local rank数量。</p>
</td>
</tr>
<tr id="row2774174052315"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p1877484015232"><a name="p1877484015232"></a><a name="p1877484015232"></a><a href="./context/get_rank_id.md">get_rank_id</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p1077434092311"><a name="p1077434092311"></a><a name="p1077434092311"></a>获取device在group中对应的rank序号。</p>
</td>
</tr>
<tr id="row1077416402239"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p777404042318"><a name="p777404042318"></a><a name="p777404042318"></a><a href="./context/get_local_rank_id.md">get_local_rank_id</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p1977474062312"><a name="p1977474062312"></a><a name="p1977474062312"></a>获取device在group中对应的local rank序号。</p>
</td>
</tr>
<tr id="row67741040182313"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p17774240172310"><a name="p17774240172310"></a><a name="p17774240172310"></a><a href="./context/get_world_rank_from_group_rank.md">get_world_rank_from_group_rank</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p577417407230"><a name="p577417407230"></a><a name="p577417407230"></a>根据进程在group中的rank id，获取对应的world rank id。</p>
</td>
</tr>
<tr id="row12774124010231"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p19774124019237"><a name="p19774124019237"></a><a name="p19774124019237"></a><a href="./context/get_group_rank_from_world_rank.md">get_group_rank_from_world_rank</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p977418405239"><a name="p977418405239"></a><a name="p977418405239"></a>从world rank id，获取该进程在group中的group rank id。</p>
</td>
</tr>
<tr id="row877417409234"><td class="cellrowborder" colspan="2" valign="top" headers="mcps1.1.3.1.1 mcps1.1.3.1.2 "><p id="p19774154032314"><a name="p19774154032314"></a><a name="p19774154032314"></a><strong id="b67741040102311"><a name="b67741040102311"></a><a name="b67741040102311"></a>梯度切分</strong></p>
</td>
</tr>
<tr id="row8774840122312"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p977434092318"><a name="p977434092318"></a><a name="p977434092318"></a><a href="./context/set_split_strategy_by_idx.md">set_split_strategy_by_idx</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p2077414092312"><a name="p2077414092312"></a><a name="p2077414092312"></a>基于梯度的索引id，在集合通信group内设置反向梯度切分策略，实现allreduce的融合，用于进行集合通信的性能调优。</p>
</td>
</tr>
<tr id="row16774340182312"><td class="cellrowborder" valign="top" width="31.790000000000003%" headers="mcps1.1.3.1.1 "><p id="p67741140132310"><a name="p67741140132310"></a><a name="p67741140132310"></a><a href="./context/set_split_strategy_by_size.md">set_split_strategy_by_size</a></p>
</td>
<td class="cellrowborder" valign="top" width="68.21000000000001%" headers="mcps1.1.3.1.2 "><p id="p1977434020234"><a name="p1977434020234"></a><a name="p1977434020234"></a>基于梯度数据量百分比，在集合通信group内设置反向梯度切分策略，实现allreduce的融合，用于进行集合通信的性能调优。</p>
</td>
</tr>
</tbody>
</table>

以上接口可以配合TF Adapter提供的集合通信操作接口使用，实现集合通信功能。

## 相关概念<a name="section3423827151813"></a>

<a name="table1937319246106"></a>
<table><thead align="left"><tr id="row7375142413109"><th class="cellrowborder" valign="top" width="16.05%" id="mcps1.1.3.1.1"><p id="p937532481015"><a name="p937532481015"></a><a name="p937532481015"></a>概念</p>
</th>
<th class="cellrowborder" valign="top" width="83.95%" id="mcps1.1.3.1.2"><p id="p237511241102"><a name="p237511241102"></a><a name="p237511241102"></a>介绍</p>
</th>
</tr>
</thead>
<tbody><tr id="row2375112451012"><td class="cellrowborder" valign="top" width="16.05%" headers="mcps1.1.3.1.1 "><p id="p11376172415101"><a name="p11376172415101"></a><a name="p11376172415101"></a>group</p>
</td>
<td class="cellrowborder" valign="top" width="83.95%" headers="mcps1.1.3.1.2 "><p id="p230611113718"><a name="p230611113718"></a><a name="p230611113718"></a>指参与集合通信的进程组，包括：</p>
<a name="ul1632665417106"></a><a name="ul1632665417106"></a><ul id="ul1632665417106"><li>hccl_world_group：默认的全局group，包含所有参与集合通信的rank，通过rank table文件创建。</li><li>自定义group：hccl_world_group包含的进程组的子集，可以通过create_group接口将rank table中的rank定义成不同的group，并行执行集合通信算法。</li></ul>
</td>
</tr>
<tr id="row15650468479"><td class="cellrowborder" valign="top" width="16.05%" headers="mcps1.1.3.1.1 "><p id="p1838910613213"><a name="p1838910613213"></a><a name="p1838910613213"></a>rank</p>
</td>
<td class="cellrowborder" valign="top" width="83.95%" headers="mcps1.1.3.1.2 "><p id="p938916683219"><a name="p938916683219"></a><a name="p938916683219"></a>group中的每个通信实体称为一个rank，每个rank都会分配一个介于0~n-1（n为NPU的数量）的唯一标识。</p>
</td>
</tr>
<tr id="row173761624151017"><td class="cellrowborder" valign="top" width="16.05%" headers="mcps1.1.3.1.1 "><p id="p183761524151014"><a name="p183761524151014"></a><a name="p183761524151014"></a>rank size</p>
</td>
<td class="cellrowborder" valign="top" width="83.95%" headers="mcps1.1.3.1.2 "><a name="ul16521161491113"></a><a name="ul16521161491113"></a><ul id="ul16521161491113"><li>rank size，指整个group的rank数量。</li><li>local rank size，指group内进程在其所在Server内的rank数量。</li></ul>
</td>
</tr>
<tr id="row1437612419106"><td class="cellrowborder" valign="top" width="16.05%" headers="mcps1.1.3.1.1 "><p id="p637652418102"><a name="p637652418102"></a><a name="p637652418102"></a>rank id</p>
</td>
<td class="cellrowborder" valign="top" width="83.95%" headers="mcps1.1.3.1.2 "><a name="ul11491332101113"></a><a name="ul11491332101113"></a><ul id="ul11491332101113"><li>rank id，指进程在group中对应的rank标识序号。范围：0~（rank size-1）。对于用户自定义group，rank在本group内从0开始进行重排；对于hccl_world_group，rank id和world rank id相同。</li><li>world rank id，指进程在hccl_world_group中对应的rank标识序号，范围：0~（rank size-1）。</li><li>local rank id，指group内进程在其所在Server内的rank编号，范围：0~（local rank size-1）。</li></ul>
</td>
</tr>
</tbody>
</table>

