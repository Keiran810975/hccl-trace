# EndPointDesc<a name="ZH-CN_TOPIC_0000002539780931"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义Endpoint描述类型结构体。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    CommProtocol protocol;  /* 通信协议 */
    CommAddr commAddr;      /* 通信地址 */
    EndpointLoc loc;        /* Endpoint的位置信息 */
    union {
        uint8_t raws[52];   /* 通用数据 */
    };
} EndpointDesc;
```

