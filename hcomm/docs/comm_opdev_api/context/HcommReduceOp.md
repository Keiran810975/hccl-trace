# HcommReduceOp<a name="ZH-CN_TOPIC_0000002539780947"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义规约操作类型。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    HCOMM_REDUCE_SUM = 0,    /* sum */
    HCOMM_REDUCE_PROD = 1,   /* prod */
    HCOMM_REDUCE_MAX = 2,    /* max */
    HCOMM_REDUCE_MIN = 3,    /* min */
    HCOMM_REDUCE_RESERVED = 255  /* reserved */
} HcommReduceOp;
```

