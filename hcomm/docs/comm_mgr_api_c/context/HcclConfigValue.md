# HcclConfigValue<a name="ZH-CN_TOPIC_0000002487008066"></a>

## 功能说明<a name="zh-cn_topic_0000001755507564_section162709502369"></a>

定义[HcclConfig](HcclConfig.md#ZH-CN_TOPIC_0000002519007963)中可配置的参数的值。

## 定义原型<a name="zh-cn_topic_0000001755507564_section742411329366"></a>

```
union HcclConfigValue {
    int32_t value;
};
```

value为[HcclConfig](HcclConfig.md#ZH-CN_TOPIC_0000002519007963)中“HCCL\_DETERMINISTIC”参数的值。

此参数仅在如下型号中支持配置：

-   Atlas A3 训练系列产品/Atlas A3 推理系列产品
-   Atlas A2 训练系列产品/Atlas A2 推理系列产品

