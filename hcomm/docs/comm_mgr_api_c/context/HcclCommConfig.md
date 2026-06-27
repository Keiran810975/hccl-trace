# HcclCommConfig<a name="ZH-CN_TOPIC_0000002486848108"></a>

## 功能说明<a name="zh-cn_topic_0000001894328112_section162709502369"></a>

初始化具有特定配置的通信域时，此数据类型用于定义通信域配置信息，包含缓存区大小、确定性计算开关和通信域名称。

## 定义原型<a name="zh-cn_topic_0000001894328112_section742411329366"></a>

```c
const uint32_t HCCL_COMM_CONFIG_INFO_BYTES = 24;
const uint32_t COMM_NAME_MAX_LENGTH = 128;
const uint32_t UDI_MAX_LENGTH = 128; 
typedef struct HcclCommConfigDef {
    char reserved[HCCL_COMM_CONFIG_INFO_BYTES];    /* 保留字段，不可修改 */
    uint32_t hcclBufferSize;
    uint32_t hcclDeterministic;
    char hcclCommName[COMM_NAME_MAX_LENGTH];
    char hcclUdi[UDI_MAX_LENGTH];
    uint32_t hcclOpExpansionMode;
    uint32_t hcclRdmaTrafficClass;
    uint32_t hcclRdmaServiceLevel;
    uint32_t hcclWorldRankID;
    uint64_t hcclJobID;
    uint8_t aclGraphZeroCopyEnable; 
} HcclCommConfig;
```

## 参数说明<a name="zh-cn_topic_0000001894328112_section1175218321514"></a>

-   **hcclBufferSize**：共享数据的缓存区大小，取值需大于等于1，单位为MByte。
-   **hcclDeterministic**：确定性计算开关，支持如下型号：

    -   Atlas A3 训练系列产品/Atlas A3 推理系列产品
    -   Atlas A2 训练系列产品/Atlas A2 推理系列产品

    该参数取值及其含义可参见[表1](#zh-cn_topic_0000001894328112_table274181020300)。

    **表 1**  hcclDeterministic参数取值说明

    <a name="zh-cn_topic_0000001894328112_table274181020300"></a>
    <table><thead align="left"><tr id="zh-cn_topic_0000001894328112_row1774111017309"><th class="cellrowborder" valign="top" width="8.76%" id="mcps1.2.3.1.1"><p id="zh-cn_topic_0000001894328112_p57418108304"><a name="zh-cn_topic_0000001894328112_p57418108304"></a><a name="zh-cn_topic_0000001894328112_p57418108304"></a>取值</p>
    </th>
    <th class="cellrowborder" valign="top" width="91.24%" id="mcps1.2.3.1.2"><p id="zh-cn_topic_0000001894328112_p57410102304"><a name="zh-cn_topic_0000001894328112_p57410102304"></a><a name="zh-cn_topic_0000001894328112_p57410102304"></a>含义</p>
    </th>
    </tr>
    </thead>
    <tbody><tr id="zh-cn_topic_0000001894328112_row974111018304"><td class="cellrowborder" valign="top" width="8.76%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p1741110123010"><a name="zh-cn_topic_0000001894328112_p1741110123010"></a><a name="zh-cn_topic_0000001894328112_p1741110123010"></a>0</p>
    </td>
    <td class="cellrowborder" valign="top" width="91.24%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p117491053010"><a name="zh-cn_topic_0000001894328112_p117491053010"></a><a name="zh-cn_topic_0000001894328112_p117491053010"></a>默认值，代表关闭确定性计算。</p>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row197481073016"><td class="cellrowborder" valign="top" width="8.76%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p674171063013"><a name="zh-cn_topic_0000001894328112_p674171063013"></a><a name="zh-cn_topic_0000001894328112_p674171063013"></a>1</p>
    </td>
    <td class="cellrowborder" valign="top" width="91.24%" headers="mcps1.2.3.1.2 "><div class="p" id="zh-cn_topic_0000001894328112_p7992534305"><a name="zh-cn_topic_0000001894328112_p7992534305"></a><a name="zh-cn_topic_0000001894328112_p7992534305"></a>开启归约类通信算子的确定性计算。<a name="zh-cn_topic_0000001894328112_ul1826245103013"></a><a name="zh-cn_topic_0000001894328112_ul1826245103013"></a><ul id="zh-cn_topic_0000001894328112_ul1826245103013"><li> 针对<span id="zh-cn_topic_0000001894328112_ph152621511300"><a name="zh-cn_topic_0000001894328112_ph152621511300"></a><a name="zh-cn_topic_0000001894328112_ph152621511300"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_1"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_1"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_1"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>，支持通信算子AllReduce、ReduceScatter、Reduce、ReduceScatterV。</li><li> 针对<span id="zh-cn_topic_0000001894328112_ph2026210514307"><a name="zh-cn_topic_0000001894328112_ph2026210514307"></a><a name="zh-cn_topic_0000001894328112_ph2026210514307"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_1"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_1"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_1"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>，支持通信算子AllReduce和ReduceScatter。</li></ul>
    </div>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row107431014301"><td class="cellrowborder" valign="top" width="8.76%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p157415106306"><a name="zh-cn_topic_0000001894328112_p157415106306"></a><a name="zh-cn_topic_0000001894328112_p157415106306"></a>2</p>
    </td>
    <td class="cellrowborder" valign="top" width="91.24%" headers="mcps1.2.3.1.2 "><div class="p" id="zh-cn_topic_0000001894328112_p14464200113111"><a name="zh-cn_topic_0000001894328112_p14464200113111"></a><a name="zh-cn_topic_0000001894328112_p14464200113111"></a>开启归约类通信算子的严格确定性计算，即保序功能（在确定性的基础上保证所有bit位的归约顺序均一致），配置为该参数时需满足以下条件：<a name="zh-cn_topic_0000001894328112_ul17794125893013"></a><a name="zh-cn_topic_0000001894328112_ul17794125893013"></a><ul id="zh-cn_topic_0000001894328112_ul17794125893013"><li>仅支持<span id="zh-cn_topic_0000001894328112_ph10794195818304"><a name="zh-cn_topic_0000001894328112_ph10794195818304"></a><a name="zh-cn_topic_0000001894328112_ph10794195818304"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_2"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_2"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_2"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>，且仅支持多机对称分布场景，不支持非对称分布的场景。</li><li> 针对<span id="zh-cn_topic_0000001894328112_ph1917013456276"><a name="zh-cn_topic_0000001894328112_ph1917013456276"></a><a name="zh-cn_topic_0000001894328112_ph1917013456276"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_2"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_2"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_2"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>，配置为<span class="parmvalue" id="zh-cn_topic_0000001894328112_parmvalue46951731172019"><a name="zh-cn_topic_0000001894328112_parmvalue46951731172019"></a><a name="zh-cn_topic_0000001894328112_parmvalue46951731172019"></a>“2”</span>时与配置为<span class="parmvalue" id="zh-cn_topic_0000001894328112_parmvalue2083132117195"><a name="zh-cn_topic_0000001894328112_parmvalue2083132117195"></a><a name="zh-cn_topic_0000001894328112_parmvalue2083132117195"></a>“1”</span>的功能保持一致。</li><li>支持通信算子为AllReduce、ReduceScatter、ReduceScatterV。</li><li>开启保序时，不支持饱和模式，仅支持INF/NaN模式。</li><li>相较于确定性计算，开启保序功能后会产生一定的性能下降，建议在推理场景下使用该功能。</li></ul>
    </div>
    </td>
    </tr>
    </tbody>
    </table>

    > [!NOTE]说明
    > 在不开启确定性计算的场景下，多次执行的结果可能不同。这个差异的来源，一般是因为在算子实现中存在异步的多线程执行，会导致浮点数累加的顺序变化。当开启确定性计算后，算子在相同的硬件和输入下，多次执行将产生相同的输出。
    >默认情况下，无需开启确定性计算或保序功能，但当发现模型执行多次结果不同或者精度调优时，可以开启确定性计算或保序功能辅助进行调测调优，但开启后，算子执行时间会变慢，导致性能下降。

-   **hcclCommName**：通信域名称，最大长度为128。

    指定的通信域名称需确保与其他通信域中的名称不重复；不指定时由HCCL自动生成。

-   **hcclUdi**：用户自定义信息，最大长度为128，默认为空。
-   **hcclOpExpansionMode**：配置通信算法的编排展开位置，为通信域粒度的配置，支持如下型号：

    -   Atlas A3 训练系列产品/Atlas A3 推理系列产品
    -   Atlas A2 训练系列产品/Atlas A2 推理系列产品

    该参数取值及其含义可参见[表2](#zh-cn_topic_0000001894328112_table18151258111419)。

    **表 2**  hcclOpExpansionMode参数取值说明

    <a name="zh-cn_topic_0000001894328112_table18151258111419"></a>
    <table><thead align="left"><tr id="zh-cn_topic_0000001894328112_row118157581141"><th class="cellrowborder" valign="top" width="6.710000000000001%" id="mcps1.2.3.1.1"><p id="zh-cn_topic_0000001894328112_p1815205871411"><a name="zh-cn_topic_0000001894328112_p1815205871411"></a><a name="zh-cn_topic_0000001894328112_p1815205871411"></a>取值</p>
    </th>
    <th class="cellrowborder" valign="top" width="93.28999999999999%" id="mcps1.2.3.1.2"><p id="zh-cn_topic_0000001894328112_p1981518583149"><a name="zh-cn_topic_0000001894328112_p1981518583149"></a><a name="zh-cn_topic_0000001894328112_p1981518583149"></a>含义</p>
    </th>
    </tr>
    </thead>
    <tbody><tr id="zh-cn_topic_0000001894328112_row481535851412"><td class="cellrowborder" valign="top" width="6.710000000000001%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p181565812142"><a name="zh-cn_topic_0000001894328112_p181565812142"></a><a name="zh-cn_topic_0000001894328112_p181565812142"></a>0</p>
    </td>
    <td class="cellrowborder" valign="top" width="93.28999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p68151358111412"><a name="zh-cn_topic_0000001894328112_p68151358111412"></a><a name="zh-cn_topic_0000001894328112_p68151358111412"></a>代表使用默认算法编排展开位置。</p>
    <a name="zh-cn_topic_0000001894328112_ul3555125263211"></a><a name="zh-cn_topic_0000001894328112_ul3555125263211"></a><ul id="zh-cn_topic_0000001894328112_ul3555125263211"><li> 针对<span id="zh-cn_topic_0000001894328112_ph881513589140"><a name="zh-cn_topic_0000001894328112_ph881513589140"></a><a name="zh-cn_topic_0000001894328112_ph881513589140"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_4"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_4"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_4"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>，若不配置此项，取环境变量<span id="zh-cn_topic_0000001894328112_ph481585811142"><a name="zh-cn_topic_0000001894328112_ph481585811142"></a><a name="zh-cn_topic_0000001894328112_ph481585811142"></a>HCCL_OP_EXPANSION_MODE</span>的值（默认为AI CPU）。</li><li> 针对<span id="zh-cn_topic_0000001894328112_ph20815185801415"><a name="zh-cn_topic_0000001894328112_ph20815185801415"></a><a name="zh-cn_topic_0000001894328112_ph20815185801415"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_4"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_4"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_4"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>，若不配置此项，取环境变量<span id="zh-cn_topic_0000001894328112_ph481555814149"><a name="zh-cn_topic_0000001894328112_ph481555814149"></a><a name="zh-cn_topic_0000001894328112_ph481555814149"></a>HCCL_OP_EXPANSION_MODE</span>的值（默认为Host侧CPU）。</li></ul>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row13815758181415"><td class="cellrowborder" valign="top" width="6.710000000000001%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p08151258141410"><a name="zh-cn_topic_0000001894328112_p08151258141410"></a><a name="zh-cn_topic_0000001894328112_p08151258141410"></a>1</p>
    </td>
    <td class="cellrowborder" valign="top" width="93.28999999999999%" headers="mcps1.2.3.1.2 "><div class="p" id="zh-cn_topic_0000001894328112_p3815175811145"><a name="zh-cn_topic_0000001894328112_p3815175811145"></a><a name="zh-cn_topic_0000001894328112_p3815175811145"></a>代表通信算法的编排展开位置为Host侧CPU。<a name="zh-cn_topic_0000001894328112_ul331195915176"></a><a name="zh-cn_topic_0000001894328112_ul331195915176"></a><ul id="zh-cn_topic_0000001894328112_ul331195915176"><li><span id="zh-cn_topic_0000001894328112_ph21314021812"><a name="zh-cn_topic_0000001894328112_ph21314021812"></a><a name="zh-cn_topic_0000001894328112_ph21314021812"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_5"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_5"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_5"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>，不支持此配置。</li><li><span id="zh-cn_topic_0000001894328112_ph1131170121811"><a name="zh-cn_topic_0000001894328112_ph1131170121811"></a><a name="zh-cn_topic_0000001894328112_ph1131170121811"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_5"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_5"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_5"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>，支持此配置。</li></ul>
    </div>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row581555811144"><td class="cellrowborder" valign="top" width="6.710000000000001%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p17815958121417"><a name="zh-cn_topic_0000001894328112_p17815958121417"></a><a name="zh-cn_topic_0000001894328112_p17815958121417"></a>2</p>
    </td>
    <td class="cellrowborder" valign="top" width="93.28999999999999%" headers="mcps1.2.3.1.2 "><div class="p" id="zh-cn_topic_0000001894328112_p48146399145"><a name="zh-cn_topic_0000001894328112_p48146399145"></a><a name="zh-cn_topic_0000001894328112_p48146399145"></a>代表通信算法的编排展开位置在Device侧的AI CPU计算单元。<a name="zh-cn_topic_0000001894328112_ul578052613164"></a><a name="zh-cn_topic_0000001894328112_ul578052613164"></a><ul id="zh-cn_topic_0000001894328112_ul578052613164"><li><span id="zh-cn_topic_0000001894328112_ph6897155917149"><a name="zh-cn_topic_0000001894328112_ph6897155917149"></a><a name="zh-cn_topic_0000001894328112_ph6897155917149"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_6"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_6"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_6"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>，不支持此配置。</li><li><span id="zh-cn_topic_0000001894328112_ph1527118115161"><a name="zh-cn_topic_0000001894328112_ph1527118115161"></a><a name="zh-cn_topic_0000001894328112_ph1527118115161"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_6"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_6"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_6"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>，不支持此配置。</li></ul>
    </div>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row481516589148"><td class="cellrowborder" valign="top" width="6.710000000000001%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p581517586147"><a name="zh-cn_topic_0000001894328112_p581517586147"></a><a name="zh-cn_topic_0000001894328112_p581517586147"></a>3</p>
    </td>
    <td class="cellrowborder" valign="top" width="93.28999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p42481059123210"><a name="zh-cn_topic_0000001894328112_p42481059123210"></a><a name="zh-cn_topic_0000001894328112_p42481059123210"></a>代表通信算法的编排展开位置在Device侧的Vector Core计算单元。仅支持推理特性。</p>
    <div class="p" id="zh-cn_topic_0000001894328112_p13102351269"><a name="zh-cn_topic_0000001894328112_p13102351269"></a><a name="zh-cn_topic_0000001894328112_p13102351269"></a><strong id="zh-cn_topic_0000001894328112_b1081555812142"><a name="zh-cn_topic_0000001894328112_b1081555812142"></a><a name="zh-cn_topic_0000001894328112_b1081555812142"></a>此配置下，若数据量不满足在“Vector Core”上的运行要求，部分算子会自动切换到默认模式。</strong><a name="zh-cn_topic_0000001894328112_ul88151583145"></a><a name="zh-cn_topic_0000001894328112_ul88151583145"></a><ul id="zh-cn_topic_0000001894328112_ul88151583145"><li> 针对<span id="zh-cn_topic_0000001894328112_ph168168585147"><a name="zh-cn_topic_0000001894328112_ph168168585147"></a><a name="zh-cn_topic_0000001894328112_ph168168585147"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_7"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_7"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_7"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>：<a name="zh-cn_topic_0000001894328112_ul1581617589144"></a><a name="zh-cn_topic_0000001894328112_ul1581617589144"></a><ul id="zh-cn_topic_0000001894328112_ul1581617589144"><li>该配置项仅支持Broadcast、AllReduce、ReduceScatter、AllGather、AlltoAll、AlltoAllV、AlltoAllVC算子。<a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6641632326"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6641632326"></a><ul id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6641632326"><li> 针对Broadcast算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16，仅支持单机场景8卡以内的单算子模式。</li><li> 针对AllReduce算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。</li><li> 针对ReduceScatter算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min，仅支持超节点内的单机/多机通信，不支持跨超节点间通信。</li><li> 针对AllGather、AlltoAll、AlltoAllV、AlltoAllVC算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16，仅支持超节点内的单机/多机通信，不支持跨超节点间通信。</li></ul>
    </li><li> 针对AllReduce、ReduceScatter、AllGather、AlltoAll（单机通信场景）算子，当数据量超过一定值时，为防止性能下降，系统会自动切换为“2：AI CPU模式”（该阈值并非固定，会根据算子运行模式、是否启动确定性计算及网络规模等因素有所调整）；针对AlltoAllV、AlltoAllVC、AlltoAll（多机通信场景）算子，系统不会自动切换为“2：AI CPU”模式，为避免性能劣化，当任意两个rank之间的最大通信数据量不超过1MB时，建议配置为“3：AIV模式”，否则请采用“2：AI CPU模式”。</li><li>该配置项对业务编译时分配的Vector Core核数有最低数量要求，若业务编译分配的Vector Core核数无法满足算法编排的要求，HCCL会报错并提示所需要的最低Vector Core核数。<pre class="screen" id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen18362122191520"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen18362122191520"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen18362122191520"></a># 报错示例1：算法编排所需的最少Vector Core数量为8
    [CalBlockDim]aivcore[3] is less than need[8].
    # 报错示例2：算法编排所需的最少Vector Core数量为8
    [CalBlockDim]aivcore[3] is less than ranksize[8].
    # 报错示例3：算法编排所需的最少Vector Core数量为6
    [CalBlockDim]aivCore[3] is invalid, at least need 6.</pre>
    <p id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p15362521191515"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p15362521191515"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p15362521191515"></a>不同框架网络编译时分配Vector Core数量的方法不同，开发者可在对应框架的产品文档中搜索关键词“aicore_num”查询对应的配置方法。</p>
    </li></ul>
    </li><li> 针对<span id="zh-cn_topic_0000001894328112_ph11816658161419"><a name="zh-cn_topic_0000001894328112_ph11816658161419"></a><a name="zh-cn_topic_0000001894328112_ph11816658161419"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_7"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_7"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_7"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>：<a name="zh-cn_topic_0000001894328112_ul1816165810145"></a><a name="zh-cn_topic_0000001894328112_ul1816165810145"></a><ul id="zh-cn_topic_0000001894328112_ul1816165810145"><li>该配置项仅支持Broadcast、AllReduce、AlltoAll、AlltoAllV、AlltoAllVC、AllGather、ReduceScatter、AllGatherV、ReduceScatterV算子。<a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6411103518244"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6411103518244"></a><ul id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ul6411103518244"><li> 针对Broadcast算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16，仅支持单机场景的单算子模式。</li><li> 针对AllReduce算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。</li><li> 针对AlltoAll、AlltoAllV、AlltoAllVC算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16。针对AlltoAllV、AlltoAllVC算子，仅支持单机场景；针对AlltoAll算子的图模式运行方式，仅支持单机场景。</li><li> 针对AllGather算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16。针对该算子的图模式运行方式，仅支持单机场景。</li><li> 针对ReduceScatter算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。针对该算子的图模式运行方式，仅支持单机场景。</li><li> 针对AllGatherV算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16，仅支持单算子模式。</li><li> 针对ReduceScatterV算子，数据类型支持int8、int16、int32、float16、float32、bfp16<span id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph98122518491"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph98122518491"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph98122518491"></a>，</span><span id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph657492516499"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph657492516499"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_ph657492516499"></a>reduce的操作类型仅支持sum、max、min</span>。</li></ul>
    </li><li>该配置项对业务编译时分配的Vector Core核数有最低数量要求，若业务编译分配的Vector Core核数无法满足算法编排的要求，HCCL会报错并提示所需要的最低Vector Core核数。<pre class="screen" id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen54890281496"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen54890281496"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_screen54890281496"></a># 报错示例：算法编排所需的最少Vector Core数量为8
    [CalBlockDim]aivcore[3] is less than need[8].</pre>
    <p id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p4986111913475"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p4986111913475"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001791219658_p4986111913475"></a>不同框架网络编译时分配Vector Core数量的方法不同，开发者可在对应框架的产品文档中搜索关键词“aicore_num”查询对应的配置方法。</p>
    </li></ul>
    </li></ul>
    </div>
    </td>
    </tr>
    <tr id="zh-cn_topic_0000001894328112_row258723223820"><td class="cellrowborder" valign="top" width="6.710000000000001%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p12587203263812"><a name="zh-cn_topic_0000001894328112_p12587203263812"></a><a name="zh-cn_topic_0000001894328112_p12587203263812"></a>4</p>
    </td>
    <td class="cellrowborder" valign="top" width="93.28999999999999%" headers="mcps1.2.3.1.2 "><div class="p" id="zh-cn_topic_0000001894328112_p141611440385"><a name="zh-cn_topic_0000001894328112_p141611440385"></a><a name="zh-cn_topic_0000001894328112_p141611440385"></a>代表通信算法的编排展开位置在Device侧的Vector Core计算单元。仅支持推理特性。<strong id="zh-cn_topic_0000001894328112_b208181458101419"><a name="zh-cn_topic_0000001894328112_b208181458101419"></a><a name="zh-cn_topic_0000001894328112_b208181458101419"></a>此配置下，不会随着数据量的变化进行模式切换，始终使用Vector Core计算，如果不满足Vector Core的运行条件，会报错退出。</strong><a name="zh-cn_topic_0000001894328112_ul1681875851416"></a><a name="zh-cn_topic_0000001894328112_ul1681875851416"></a><ul id="zh-cn_topic_0000001894328112_ul1681875851416"><li>该配置项仅支持AllReduce、ReduceScatter、AllGather、AlltoAll、AlltoAllV、AlltoAllVC算子。</li><li> 针对<span id="zh-cn_topic_0000001894328112_ph616453604613"><a name="zh-cn_topic_0000001894328112_ph616453604613"></a><a name="zh-cn_topic_0000001894328112_ph616453604613"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_8"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_8"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term1253731311225_8"></a>Atlas A3 训练系列产品/Atlas A3 推理系列产品</term></span>：<a name="zh-cn_topic_0000001894328112_ul193608434467"></a><a name="zh-cn_topic_0000001894328112_ul193608434467"></a><ul id="zh-cn_topic_0000001894328112_ul193608434467"><li> 针对AllReduce算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。</li><li> 针对ReduceScatter算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min，仅支持超节点内的单机/多机通信，不支持跨超节点间通信。</li><li> 针对AllGather、AlltoAll、AlltoAllV、AlltoAllVC算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16，仅支持超节点内的单机/多机通信，不支持跨超节点间通信。</li></ul>
    </li><li> 针对<span id="zh-cn_topic_0000001894328112_ph15822875451"><a name="zh-cn_topic_0000001894328112_ph15822875451"></a><a name="zh-cn_topic_0000001894328112_ph15822875451"></a><term id="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_8"><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_8"></a><a name="zh-cn_topic_0000001894328112_zh-cn_topic_0000001312391781_term16184138172215_8"></a>Atlas A2 训练系列产品/Atlas A2 推理系列产品</term></span>：<a name="zh-cn_topic_0000001894328112_ul2781155915423"></a><a name="zh-cn_topic_0000001894328112_ul2781155915423"></a><ul id="zh-cn_topic_0000001894328112_ul2781155915423"><li> 针对AllReduce算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。</li><li> 针对ReduceScatter算子，数据类型支持int8、int16、int32、float16、float32、bfp16，reduce的操作类型仅支持sum、max、min。针对该算子的图模式运行方式，仅支持单机场景。</li><li> 针对AllGather算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16。针对该算子的图模式运行方式，仅支持单机场景。</li><li> 针对AlltoAll、AlltoAllV、AlltoAllVC算子，数据类型支持int8、uint8、int16、uint16、int32、uint32、float16、float32、bfp16。针对AlltoAllV、AlltoAllVC算子，仅支持单机场景；针对AlltoAll算子的图模式运行方式，仅支持单机场景。</li></ul>
    </li></ul>
    </div>
    </td>
    </tr>
    </tbody>
    </table>

    > [!NOTE]说明
    > -   多通信域并行场景下，不支持多个通信域同时配置为“3”或“4”（AIV Only模式）。
    > -   针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，算法编排展开位置设置为“3”或“4”时，同时设置hcclDeterministic配置为“1”（开启确定性计算），在单机的单算子和图模式场景下，当数据量≤8MB时，仅AllReduce和ReduceScatter算子的确定性计算生效，其他场景和算子则以hcclDeterministic配置为准。
    > -   针对Atlas A2 训练系列产品/Atlas A2 推理系列产品，若hcclDeterministic配置为“2”（开启保序功能），hcclOpExpansionMode不支持配置为“3”或“4”，以保序功能为准。
    > -   针对Atlas A3 训练系列产品/Atlas A3 推理系列产品，算法编排展开位置设置为“3”或“4”时，若同时设置hcclDeterministic为“1”（开启确定性计算）或“2”（开启保序功能），当数据量＜8MB时，仅AllReduce和ReduceScatter算子的确定性计算生效，其他场景和算子则以hcclDeterministic配置为准。

-   **hcclRdmaTrafficClass**：配置RDMA网卡的traffic class，取值范围为\[0,255\]，需要配置为4的整数倍。

    在RoCE V2协议中，该值对应IP报文头中ToS（Type of Service）域段。共8个bit，其中，bit\[0,1\]固定为0，bit\[2,7\]为DSCP，因此，该值除以4即为DSCP的值。

    **注意事项：**

    0xFFFFFFFF被用作优先级判断标识，当配置为0xFFFFFFFF时，此通信域配置无效，会按照优先级取环境变量配置或默认值132。

-   **hcclRdmaServiceLevel**：配置RDMA网卡的service level，取值需要和网卡配置的PFC优先级保持一致，若配置不一致可能导致性能劣化。

    需要配置为无符号整数，取值范围\[0,7\]。

    **注意事项：**

    0xFFFFFFFF被用作优先级判断标识，当配置为0xFFFFFFFF时，此通信域配置无效，会按照优先级取环境变量配置或默认值4。

-   **hcclWorldRankID**：NSLB-DP（Network Scale Load Balance-Data Plane：数据面网络级负载均衡）场景使用字段，代表当前进程在AI框架（如Pytorch）中的全局rank ID。
-   **hcclJobID：**NSLB-DP场景使用字段，代表当前分布式业务的唯一标识，由AI框架生成。
-   **aclGraphZeroCopyEnable**：该参数仅在图捕获模式（aclgraph）下对Reduce类算子生效，用于控制其是否开启零拷贝功能。
    -   0（默认值）：关闭零拷贝功能。
    -   1：开启零拷贝功能。

## 配置优先级说明<a name="zh-cn_topic_0000001894328112_section1196611071515"></a>

**表 3**  配置优先级说明

<a name="zh-cn_topic_0000001894328112_table1167162831520"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001894328112_row767162811153"><th class="cellrowborder" valign="top" width="19.02%" id="mcps1.2.3.1.1"><p id="zh-cn_topic_0000001894328112_p146717282156"><a name="zh-cn_topic_0000001894328112_p146717282156"></a><a name="zh-cn_topic_0000001894328112_p146717282156"></a>配置项</p>
</th>
<th class="cellrowborder" valign="top" width="80.97999999999999%" id="mcps1.2.3.1.2"><p id="zh-cn_topic_0000001894328112_p106714288150"><a name="zh-cn_topic_0000001894328112_p106714288150"></a><a name="zh-cn_topic_0000001894328112_p106714288150"></a>配置优先级</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001894328112_row36718288154"><td class="cellrowborder" valign="top" width="19.02%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p467928191516"><a name="zh-cn_topic_0000001894328112_p467928191516"></a><a name="zh-cn_topic_0000001894328112_p467928191516"></a>hcclBufferSize</p>
</td>
<td class="cellrowborder" valign="top" width="80.97999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p166711287156"><a name="zh-cn_topic_0000001894328112_p166711287156"></a><a name="zh-cn_topic_0000001894328112_p166711287156"></a>配置项hcclBufferSize（通信域粒度配置）&gt; 环境变量HCCL_BUFFSIZE（全局配置）&gt; 默认值200。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001894328112_row86732881519"><td class="cellrowborder" valign="top" width="19.02%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p16675288151"><a name="zh-cn_topic_0000001894328112_p16675288151"></a><a name="zh-cn_topic_0000001894328112_p16675288151"></a>hcclDeterministic</p>
</td>
<td class="cellrowborder" valign="top" width="80.97999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p868428121519"><a name="zh-cn_topic_0000001894328112_p868428121519"></a><a name="zh-cn_topic_0000001894328112_p868428121519"></a>配置项hcclDeterministic（通信域粒度配置）&gt; 环境变量HCCL_DETERMINISTIC（全局配置）&gt; 默认值0（关闭确定性计算）。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001894328112_row13681028151515"><td class="cellrowborder" valign="top" width="19.02%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p1768182817159"><a name="zh-cn_topic_0000001894328112_p1768182817159"></a><a name="zh-cn_topic_0000001894328112_p1768182817159"></a>hcclOpExpansionMode</p>
</td>
<td class="cellrowborder" valign="top" width="80.97999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p117032891515"><a name="zh-cn_topic_0000001894328112_p117032891515"></a><a name="zh-cn_topic_0000001894328112_p117032891515"></a>配置项hcclOpExpansionMode（通信域粒度配置）&gt; 环境变量HCCL_OP_EXPANSION_MODE（全局配置）&gt; 默认值0。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001894328112_row770928131513"><td class="cellrowborder" valign="top" width="19.02%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p187022817154"><a name="zh-cn_topic_0000001894328112_p187022817154"></a><a name="zh-cn_topic_0000001894328112_p187022817154"></a>hcclRdmaTrafficClass</p>
</td>
<td class="cellrowborder" valign="top" width="80.97999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p77052831517"><a name="zh-cn_topic_0000001894328112_p77052831517"></a><a name="zh-cn_topic_0000001894328112_p77052831517"></a>配置项hcclRdmaTrafficClass（通信域粒度配置） &gt; 环境变量HCCL_RDMA_TC（全局配置）&gt; 默认值132。</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001894328112_row16701128171519"><td class="cellrowborder" valign="top" width="19.02%" headers="mcps1.2.3.1.1 "><p id="zh-cn_topic_0000001894328112_p270172815156"><a name="zh-cn_topic_0000001894328112_p270172815156"></a><a name="zh-cn_topic_0000001894328112_p270172815156"></a>hcclRdmaServiceLevel</p>
</td>
<td class="cellrowborder" valign="top" width="80.97999999999999%" headers="mcps1.2.3.1.2 "><p id="zh-cn_topic_0000001894328112_p14701728181518"><a name="zh-cn_topic_0000001894328112_p14701728181518"></a><a name="zh-cn_topic_0000001894328112_p14701728181518"></a>配置项hcclRdmaServiceLevel（通信域粒度配置）&gt; 环境变量HCCL_RDMA_SL（全局配置）&gt; 默认值4。</p>
</td>
</tr>
</tbody>
</table>

