# CommTopo<a name="ZH-CN_TOPIC_0000002507941284"></a>

## 功能说明<a name="zh-cn_topic_0000001802506149_section162709502369"></a>

定义通信拓扑类型。

## 定义原型<a name="zh-cn_topic_0000001802506149_section742411329366"></a>

```
typedef enum {
    COMM_TOPO_RESERVED = -1,  /* 保留拓扑 */
    COMM_TOPO_CLOS = 0,       /* CLOS互联拓扑 */
    COMM_TOPO_1DMESH = 1,     /* 1DMesh互联拓扑 */
    COMM_TOPO_910_93 = 2,     /* Atlas A3 训练系列产品/Atlas A3 推理系列产品的互联拓扑(带SIO) */
    COMM_TOPO_310P = 3,       /* Atlas 推理系列产品的互联拓扑 */
} CommTopo;
```

