# HcclConfig<a name="ZH-CN_TOPIC_0000002519007963"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义集合通信相关配置。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    HCCL_DETERMINISTIC = 0, /* 0: non-deterministic, 1: deterministic */
    HCCL_CONFIG_RESERVED
} HcclConfig;
```

## 参数说明<a name="zh-cn_topic_0000001802506149_section990734313292"></a>

-   HCCL\_DETERMINISTIC：是否开启确认性计算。

    -   0：不开启确定性计算。
    -   1：开启确定性计算。

    此参数仅在如下型号中支持配置：

    -   Atlas A3 训练系列产品/Atlas A3 推理系列产品
    -   Atlas A2 训练系列产品/Atlas A2 推理系列产品

-   HCCL\_CONFIG\_RESERVED：预留参数。

