# CommProtocol<a name="ZH-CN_TOPIC_0000002507941254"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义通信协议类型枚举。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    COMM_PROTOCOL_RESERVED = -1,  /* 保留协议类型 */
    COMM_PROTOCOL_HCCS = 0,       /* HCCS协议 */
    COMM_PROTOCOL_ROCE = 1,       /* RDMA over Converged Ethernet */
    COMM_PROTOCOL_PCIE = 2,       /* PCIE协议 */
    COMM_PROTOCOL_SIO = 3,        /* SIO协议 */
} CommProtocol;
```

