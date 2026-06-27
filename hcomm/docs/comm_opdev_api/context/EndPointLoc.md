# EndPointLoc<a name="ZH-CN_TOPIC_0000002539660979"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义Endpoint位置类型结构体。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef struct {
    EndpointLocType locType;        /* Endpoint的位置类别 */
    union {
        uint8_t raws[60];           /* 通用数据 */
        struct {
            uint32_t devPhyId;      /* 设备物理ID */
            uint32_t superDevId;    /* 超节点Device Id */
            uint32_t serverIdx;     /* Server的索引 */
            uint32_t superPodIdx;   /* 超节点位置索引 */
        } device;                   /* 当locType为DEVICE时使用 */
        struct {
            uint32_t id;            /* 普通ID，当locType为HOST等时使用 */
        } host;
    };
} EndpointLoc;
```

