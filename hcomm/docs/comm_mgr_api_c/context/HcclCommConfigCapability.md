# HcclCommConfigCapability<a name="ZH-CN_TOPIC_0000002519087959"></a>

## 功能说明<a name="zh-cn_topic_0000002023566761_section12921087719"></a>

定义通信域初始化时支持的相关配置信息。

## 定义原型<a name="zh-cn_topic_0000002023566761_section1272519251070"></a>

```c
typedef enum {
    HCCL_COMM_CONFIG_BUFFER_SIZE = 0,       /* 共享数据的缓存区大小 */
    HCCL_COMM_CONFIG_DETERMINISTIC = 1,    /* 确定性计算开关 */
    HCCL_COMM_CONFIG_COMM_NAME = 2,        /* 通信域名称 */
    HCCL_COMM_CONFIG_OP_EXPANSION = 3,     /* 通信算法的编排展开位置 */
    HCCL_COMM_CONFIG_SUPPORT_INIT_BY_ENV = 4,  /* 是否支持以环境变量配置为初始值 */
    HCCL_COMM_CONFIG_WORLD_RANKID = 5,  /* NSLB-DP场景下指定当前进程在AI框架中的全局rank ID */
    HCCL_COMM_CONFIG_JOBID = 6,  /* NSLB-DP场景下指定当前分布式业务的唯一标识，由AI框架生成*/
    HCCL_COMM_CONFIG_ACLGRAPH_ZEROCOPY_ENABLE = 7,  /* 图捕获模式（aclgraph）下用于控制其是否开启零拷贝功能，仅对Reduce类算子生效 */
    HCCL_COMM_CONFIG_RESERVED              /* 预留字段 */
} HcclCommConfigCapability;
```

