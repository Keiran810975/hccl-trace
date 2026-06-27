# HcclRootInfo<a name="ZH-CN_TOPIC_0000002486848106"></a>

## 功能说明<a name="zh-cn_topic_0000001755666484_section162709502369"></a>

root节点的rank信息，主要包含root节点的host ip、host port以及root节点唯一标识（由device id和时间戳等信息拼接获得）。

## 定义原型<a name="zh-cn_topic_0000001755666484_section742411329366"></a>

```c
const uint32_t HCCL_ROOT_INFO_BYTES =  4108; // 4108: root info length
typedef struct HcclRootInfoDef {
    char internal[HCCL_ROOT_INFO_BYTES];
} HcclRootInfo;
```

