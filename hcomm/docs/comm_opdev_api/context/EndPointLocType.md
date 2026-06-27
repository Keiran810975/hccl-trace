# EndPointLocType<a name="ZH-CN_TOPIC_0000002539780953"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义通信设备Endpoint的位置。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    ENDPOINT_LOC_TYPE_RESERVED = -1,  /* 保留的Endpoint位置 */
    ENDPOINT_LOC_TYPE_DEVICE = 0,     /* Endpoint在Device上 */
    ENDPOINT_LOC_TYPE_HOST = 1,       /* Endpoint在Host上 */
} EndpointLocType;
```

