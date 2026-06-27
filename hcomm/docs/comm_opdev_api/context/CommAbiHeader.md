# CommAbiHeader<a name="ZH-CN_TOPIC_0000002507941270"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

兼容Abi字段结构体。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    uint32_t version;
    uint32_t magicWord;
    uint32_t size;
    uint32_t reserved;
} CommAbiHeader;
```

