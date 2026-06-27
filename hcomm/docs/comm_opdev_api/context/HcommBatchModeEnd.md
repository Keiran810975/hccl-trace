# HcommBatchModeEnd<a name="ZH-CN_TOPIC_0000002539661001"></a>

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

该接口用于提交并触发批量模式下缓存的所有操作的执行。所有在HcommBatchModeStart和HcommBatchModeEnd之间的数据面接口调用操作将在此时统一执行。

## 函数原型<a name="section62999330"></a>

```
int32_t HcommBatchModeEnd(const char *batchTag)
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
<tbody><tr id="row17472816"><td class="cellrowborder" valign="top" width="20.200000000000003%" headers="mcps1.1.4.1.1 "><p id="p1541652713226"><a name="p1541652713226"></a><a name="p1541652713226"></a>batchTag</p>
</td>
<td class="cellrowborder" valign="top" width="17.169999999999998%" headers="mcps1.1.4.1.2 "><p id="p1465934910384"><a name="p1465934910384"></a><a name="p1465934910384"></a>输入</p>
</td>
<td class="cellrowborder" valign="top" width="62.629999999999995%" headers="mcps1.1.4.1.3 "><p id="p4329334226"><a name="p4329334226"></a><a name="p4329334226"></a>批量任务标识符，需要与HcommBatchModeStart中传入的batchTag保持一致。</p>
</td>
</tr>
</tbody>
</table>

## 返回值<a name="section24049039"></a>

int32\_t：接口成功返回0，其他失败。

## 约束说明<a name="section15114764"></a>

HcommBatchModeStart和HcommBatchModeEnd必须成对调用，且需要在同一线程中执行。

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

