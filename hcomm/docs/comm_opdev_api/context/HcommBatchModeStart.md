# HcommBatchModeStart<a name="ZH-CN_TOPIC_0000002539660987"></a>

## 产品支持情况<a name="section10594071513"></a>

<a name="zh-cn_topic_0000001264921398_table38301303189"></a>
<table><thead align="left"><tr id="zh-cn_topic_0000001264921398_row20831180131817"><th class="cellrowborder" valign="top" width="57.99999999999999%" id="mcps1.1.3.1.1"><p id="p1883113061818"><a name="p1883113061818"></a><a name="p1883113061818"></a><span id="ph20833205312295"><a name="ph20833205312295"></a><a name="ph20833205312295"></a>产品</span></p>
</th>
<th class="cellrowborder" align="center" valign="top" width="42%" id="mcps1.1.3.1.2"><p id="zh-cn_topic_0000001264921398_p783113012187"><a name="zh-cn_topic_0000001264921398_p783113012187"></a><a name="zh-cn_topic_0000001264921398_p783113012187"></a>是否支持</p>
</th>
</tr>
</thead>
<tbody><tr id="zh-cn_topic_0000001264921398_row220181016240"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="p48327011813"><a name="p48327011813"></a><a name="p48327011813"></a><span id="ph583230201815"><a name="ph583230201815"></a><a name="ph583230201815"></a><term id="zh-cn_topic_0000002534508309_term1253731311225"><a name="zh-cn_topic_0000002534508309_term1253731311225"></a><a name="zh-cn_topic_0000002534508309_term1253731311225"></a>Atlas A3 训练系列产品</term>/<term id="zh-cn_topic_0000002534508309_term131434243115"><a name="zh-cn_topic_0000002534508309_term131434243115"></a><a name="zh-cn_topic_0000002534508309_term131434243115"></a>Atlas A3 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001264921398_p7948163910184"><a name="zh-cn_topic_0000001264921398_p7948163910184"></a><a name="zh-cn_topic_0000001264921398_p7948163910184"></a>√</p>
</td>
</tr>
<tr id="zh-cn_topic_0000001264921398_row173226882415"><td class="cellrowborder" valign="top" width="57.99999999999999%" headers="mcps1.1.3.1.1 "><p id="p14832120181815"><a name="p14832120181815"></a><a name="p14832120181815"></a><span id="ph1292674871116"><a name="ph1292674871116"></a><a name="ph1292674871116"></a><term id="zh-cn_topic_0000002534508309_term11962195213215"><a name="zh-cn_topic_0000002534508309_term11962195213215"></a><a name="zh-cn_topic_0000002534508309_term11962195213215"></a>Atlas A2 训练系列产品</term>/<term id="zh-cn_topic_0000002534508309_term184716139811"><a name="zh-cn_topic_0000002534508309_term184716139811"></a><a name="zh-cn_topic_0000002534508309_term184716139811"></a>Atlas A2 推理系列产品</term></span></p>
</td>
<td class="cellrowborder" align="center" valign="top" width="42%" headers="mcps1.1.3.1.2 "><p id="zh-cn_topic_0000001264921398_p19948143911820"><a name="zh-cn_topic_0000001264921398_p19948143911820"></a><a name="zh-cn_topic_0000001264921398_p19948143911820"></a>√</p>
</td>
</tr>
</tbody>
</table>

## 功能说明<a name="section30123063"></a>

该接口用于开启批量模式，在HcommBatchModeStart和HcommBatchModeEnd之间的所有数据面接口调用（如 HcommLocalCopy、HcommWrite 等）将被缓存，不会立即执行。所有操作将在调用HcommBatchModeEnd时统一提交并执行。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommBatchModeStart(const char *batchTag)
```

## 参数说明<a name="section2672115"></a>

<a name="table66471715"></a>
<table><thead align="left"><tr id="row24725298"><th class="cellrowborder" valign="top" width="20.200000000000003%" id="mcps1.1.4.1.1"><p id="p56592155"><a name="p56592155"></a><a name="p56592155"></a>参数名</p>
</th>
<th class="cellrowborder" valign="top" width="17.169999999999998%" id="mcps1.1.4.1.2"><p id="p20561848"><a name="p20561848"></a><a name="p20561848"></a>输入/输出</p>
</th>
<th class="cellrowborder" valign="top" width="62.629999999999995%" id="mcps1.1.4.1.3"><p id="p54897010"><a name="p54897010"></a><a name="p54897010"></a>描述</p>
</th>
</tr>
</thead>
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p980071372011"><a name="p980071372011"></a><a name="p980071372011"></a>batchTag</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1465934910384"><a name="p1465934910384"></a><a name="p1465934910384"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p157212112212"><a name="p157212112212"></a><a name="p157212112212"></a>批量任务标识符（可选）。若传入 NULL 或空字符串，表示该任务为临时批量任务，执行后不会被缓存；若传入非空字符串，则用于后续批量任务的标识与管理。</p>
<p id="p1647145432614"><a name="p1647145432614"></a><a name="p1647145432614"></a>需要注意，在通信引擎为AI CPU+TS的场景下，当前暂未完全支持基于非空标识符的任务缓存管理功能。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

int32\_t：接口成功返回0，其他失败。

## 约束说明<a name="section15114764"></a>

1.  HcommBatchModeStart和HcommBatchModeEnd必须成对调用，且需在同一线程中执行。
2.  批量模式下缓存的操作需在HcommBatchModeEnd调用后才会实际执行。

## 调用示例<a name="section204039211474"></a>

```
#include "hcomm_primitives.h"
#include <stdio.h>

int main() {
    // 假设已初始化线程句柄 thread 和内存地址 src/dst
    ThreadHandle thread = ...;  // 有效线程句柄
    void *dst = ...;            // 有效目标地址
    const void *src = ...;      // 有效源地址
    uint64_t len = 1024;        // 数据长度
	
    char *tag = "";
    // 启动批量模式（临时批量任务）
    int32_t ret = HcommBatchModeStart(tag);
    if (ret != 0) {
        printf("HcommBatchModeStart failed, ret: %d\n", ret);
        return ret;
    }

    // 在批量模式中调用 HcommLocalCopy（不会立即执行）
    ret = HcommLocalCopyOnThread(thread, dst, src, len);
    if (ret != 0) {
        printf("HcommLocalCopyOnThread failed, ret: %d\n", ret);
        HcommBatchModeEnd(tag);  // 即使失败也需结束批量模式
        return ret;
    }

    // 结束批量模式并触发执行
    ret = HcommBatchModeEnd(tag);
    if (ret != 0) {
        printf("HcommBatchModeEnd failed, ret: %d\n", ret);
        return ret;
    }

    printf("Batch operations executed successfully.\n");
    return 0;
}
```

