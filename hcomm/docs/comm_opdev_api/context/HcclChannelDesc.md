# HcclChannelDesc<a name="ZH-CN_TOPIC_0000002507941272"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义通道参数。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    CommAbiHeader header;
    uint32_t remoteRank;              /* 远端rankId */
    CommProtocol channelProtocol;     /* 通信协议 */
    EndpointDesc localEndpoint;       /* 本地网络设备端侧描述 */
    EndpointDesc remoteEndpoint;      /* 远端网络设备端侧描述 */
    uint32_t notifyNum;               /* channel上使用的同步信号数量 */
    void *memHandles;                 /* 注册到通信域的待交换内存句柄 */
    uint32_t memHandleNum;            /* 注册到通信域的待交换内存句柄数量 */
    union {
        uint8_t raws[128];            /* 通用缓存 */
        struct {
            uint32_t queueNum;        /* QP数量 */
            uint32_t retryCnt;        /* 最大重传次数 */
            uint32_t retryInterval;   /* 重传间隔(ms) */
            uint8_t tc;               /* 流量类别(QoS) */
            uint8_t sl;               /* 服务等级(QoS) */
        } roceAttr;
    };
} HcclChannelDesc;
```

