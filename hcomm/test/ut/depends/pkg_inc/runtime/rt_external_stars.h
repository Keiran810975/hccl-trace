/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2021. All rights reserved.
 * Description: the definition of stars
 */

#ifndef CCE_RUNTIME_RT_EXTERNAL_STARS_H
#define CCE_RUNTIME_RT_EXTERNAL_STARS_H

#include "rt_external_base.h"
#include "rt_external_stars_define.h"

#if defined(__cplusplus)
extern "C" {
#endif

// general ctrl type
typedef enum tagGeneralCtrlType {
    RT_GNL_CTRL_TYPE_MEMCPY_ASYNC_CFG = 0,
    RT_GNL_CTRL_TYPE_REDUCE_ASYNC_CFG = 1,
    RT_GNL_CTRL_TYPE_FFTS_PLUS_FLAG = 2,
    RT_GNL_CTRL_TYPE_FFTS_PLUS = 3,
    RT_GNL_CTRL_TYPE_NPU_GET_FLOAT_STATUS = 4,
    RT_GNL_CTRL_TYPE_NPU_CLEAR_FLOAT_STATUS = 5,
    RT_GNL_CTRL_TYPE_STARS_TSK = 6,
    RT_GNL_CTRL_TYPE_CDQ_EN_QU = 7,
    RT_GNL_CTRL_TYPE_CDQ_EN_QU_PTR = 8,
    RT_GNL_CTRL_TYPE_CMO_TSK = 9,
    RT_GNL_CTRL_TYPE_BARRIER_TSK = 10,
    RT_GNL_CTRL_TYPE_STARS_TSK_FLAG = 11,
    RT_GNL_CTRL_TYPE_SET_STREAM_TAG = 12,
    RT_GNL_CTRL_TYPE_MULTIPLE_TSK = 13,
    RT_GNL_CTRL_TYPE_NPU_GET_FLOAT_DEBUG_STATUS = 14,
    RT_GNL_CTRL_TYPE_NPU_CLEAR_FLOAT_DEBUG_STATUS = 15,
    RT_GNL_CTRL_TYPE_MULTIPLE_TSK_FLAG = 16, // invoke rtMultipleTaskInfoLaunchWithFlag
    RT_GNL_CTRL_TYPE_MAX
} rtGeneralCtrlType_t;

/**
 * @ingroup rt_stars
 * @brief 5612(tiny) need translate addr
 * @param [out] needTranslate
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtNeedDevVA2PA(bool *need);

/**
 * @ingroup rt_stars
 * @brief translate addr from va to pa
 * @param [in] devAddr translate addr
 * @param [in] len addr len
 * @param [in] stm stream
* @param [in] isAsync async or sync
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtDevVA2PA(uint64_t devAddr, uint64_t len, rtStream_t stm, bool isAsync);

/**
 * @ingroup rt_stars
 * @brief dvpp group handle.
 */
typedef void *rtDvppGrp_t;

/**
 * @ingroup rt_stars
 * @brief create stream with grp handle
 * @param [in|out] stm   created stream
 * @param [in] priority   stream priority
 * @param [in] flags  stream op flags
 * @param [in] grp    grp handle
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtStreamCreateByGrp(rtStream_t *stm, int32_t priority, uint32_t flags, rtDvppGrp_t grp);

/**
 * @ingroup rt_stars
 * @brief create dvpp group.
 * @param [in] flags     group flag, reserved parameter
 * @param [out] grp      group handle
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtDvppGroupCreate(rtDvppGrp_t *grp, uint32_t flags);

/**
 * @ingroup rt_stars
 * @brief destroy dvpp group.
 * @param [in] grp      group handle
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtDvppGroupDestory(rtDvppGrp_t grp);

typedef struct tagDvppGrpRptInfo {
    uint32_t deviceId;
    uint32_t streamId;
    uint32_t taskId;
    uint8_t sqeType;
    uint8_t cqeErrorCode;
    uint8_t reserve[2];
    uint32_t accErrorCode;
} rtDvppGrpRptInfo_t;

typedef void (*rtDvppGrpCallback)(rtDvppGrpRptInfo_t *rptInfo);

/**
 * @ingroup rt_stars
 * @brief wait report by grp
 * @param [in] grp              group handle
 * @param [in] callBackFunc     callback
 * @param [in] timeout          wait timeout config, ms, -1: wait forever
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtDvppWaitGroupReport(rtDvppGrp_t grp, rtDvppGrpCallback callBackFunc, int32_t timeout);

/*
 * @ingroup rt_stars
 * @brief build multiple task
 * @param [in] taskInfo(rtMultipleTaskInfo_t)
 * @param [in] stm: stream handle
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtMultipleTaskInfoLaunch(const void *taskInfo, rtStream_t stm);

#pragma pack(push)
#pragma pack(1)
typedef enum {
    RT_DVPP_CMDLIST_NOT_FREE = 1U,
    RT_DVPP_MAX
} rtDvppAttrId;

typedef union {
    bool isCmdListNotFree;
    uint32_t rsv[4];
} rtDvppAttrVal_t;

typedef struct {
    rtDvppAttrId id;
    rtDvppAttrVal_t value;
} rtDvppAttr_t;

typedef struct {
    rtDvppAttr_t *attrs;
    size_t numAttrs;
} rtDvppCfg_t;
#pragma pack(pop)

/**
 * @ingroup rts_stars
 * @brief launch DVPP task
 * @param [in] sqe dvpp sqe
 * @param [in] sqeLen dvpp sqe length
 * @param [in] stm stream
 * @param [in] cfg dvpp option cfg
 * @return RT_ERROR_NONE for ok, others failed
 */
RTS_API rtError_t rtLaunchDvppTask(const void *sqe, uint32_t sqeLen, rtStream_t stm, rtDvppCfg_t *cfg);

#if defined(__cplusplus)
}
#endif
#endif  // CCE_RUNTIME_RT_EXTERNAL_STARS_H