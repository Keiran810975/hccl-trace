# CommAddr<a name="ZH-CN_TOPIC_0000002508101106"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

通信设备地址描述结构体。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    CommAddrType type;         /* 通信地址类别 */
    union {
        uint8_t raws[36];      /* 通用数据 */
        struct in_addr addr;   /* IPv4地址结构 */
        struct in6_addr addr6; /* IPv6地址结构 */
        uint32_t id;           /* 标识 */
    };
} CommAddr;
```

