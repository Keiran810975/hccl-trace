# CommLink<a name="ZH-CN_TOPIC_0000002508101142"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

通信连接信息，包含用于创建通信Channel的协议、地址等信息。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    CommAbiHeader header; /* 兼容Abi字段 */
    EndpointDesc srcEndpointDesc; /* 源Endpoint描述类型 */
    EndpointDesc dstEndpointDesc; /* 目的Endpoint描述类型 */
    union {
        uint8_t raws[128];
        struct {
            CommProtocol linkProtocol; /* 通信协议类型 */
        };
    } linkAttr;
} CommLink;
```

