# CommAddrType<a name="ZH-CN_TOPIC_0000002539780961"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

通信设备地址类别。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    COMM_ADDR_TYPE_RESERVED = -1, /* 保留地址类型 */
    COMM_ADDR_TYPE_IP_V4 = 0,     /* IPv4地址类型 */
    COMM_ADDR_TYPE_IP_V6 = 1,     /* IPv6地址类型 */
    COMM_ADDR_TYPE_ID = 2,        /* ID地址类型 *、
} CommAddrType;
```

