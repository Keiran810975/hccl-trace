 /**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * 
 * The code snippet comes from Ascend project.
 * 
 * Copyright 2020 Huawei Technologies Co., Ltd
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef CCE_RUNTIME_CONFIG_H
#define CCE_RUNTIME_CONFIG_H

#include "base.h"

#if defined(__cplusplus)
extern "C" {
#endif

#define PLAT_COMBINE(arch, chip, ver) (((arch) << 16U) | ((chip) << 8U) | (ver))
#define PLAT_GET_ARCH(type)           (((type) >> 16U) & 0xffffU)
#define PLAT_GET_CHIP(type)           (((type) >> 8U) & 0xffU)
#define PLAT_GET_VER(type)            ((type) & 0xffU)

typedef enum tagRtArchType {
    ARCH_BEGIN = 0,
    ARCH_V100 = ARCH_BEGIN,
    ARCH_V200 = 1,
    ARCH_V300 = 2,
    ARCH_C100 = 3, /* Ascend910 */
    ARCH_C220 = 4, /* Ascend910B & Ascend910_93 */
    ARCH_M100 = 5, /* Ascend310 */
    ARCH_M200 = 6, /* Ascend310P & Ascend610 */
    ARCH_M201 = 7, /* BS9SX1A */
    ARCH_T300 = 8, /* Tiny */
    ARCH_N350 = 9, /* Nano */
    ARCH_M300 = 10, /* Ascend310B & AS31XM1X */
    ARCH_M310 = 11, /* Ascend610Lite */
    ARCH_S200 = 12, /* Hi3796CV300ES & TsnsE */
    ARCH_S202 = 13, /* Hi3796CV300CS & OPTG & SD3403 &TsnsC */
    ARCH_M510 = 14, /* MC62CM12A */
    ARCH_END,
} rtArchType_t;

typedef enum tagRtChipType {
    CHIP_BEGIN = 0,
    CHIP_MINI = CHIP_BEGIN,
    CHIP_CLOUD = 1,
    CHIP_MDC = 2,
    CHIP_LHISI = 3,
    CHIP_DC = 4,
    CHIP_CLOUD_V2 = 5,
    CHIP_NO_DEVICE = 6,
    CHIP_MINI_V3 = 7,
    CHIP_5612 = 8, /* 1910b tiny */
    CHIP_NANO = 9,
    CHIP_1636 = 10,
    CHIP_AS31XM1 = 11,
    CHIP_610LITE = 12,
    CHIP_CLOUD_V3 = 13, // drive used, runtime not used
    CHIP_BS9SX1A = 14,  /* BS9SX1A */
    CHIP_DAVID = 15,
    CHIP_CLOUD_V5 = 16,
    CHIP_MC62CM12A = 17,  /* MC62CM12A */
    CHIP_END
} rtChipType_t;

typedef enum tagRtAicpuScheType {
    SCHEDULE_SOFTWARE = 0, /* Software Schedule */
    SCHEDULE_SOFTWARE_OPT,
    SCHEDULE_HARDWARE, /* HWTS Schedule */
} rtAicpuScheType;

typedef enum tagRtDeviceCapabilityType {
    RT_SCHEDULE_SOFTWARE = 0, // Software Schedule
    RT_SCHEDULE_SOFTWARE_OPT,
    RT_SCHEDULE_HARDWARE, // HWTS Schedule
    RT_AICPU_BLOCKING_OP_NOT_SUPPORT,
    RT_AICPU_BLOCKING_OP_SUPPORT, // 1910/1980/51 ts support AICPU blocking operation
    RT_MODE_NO_FFTS, // no ffts
    RT_MODE_FFTS, // 81 get ffts work mode, ffts
    RT_MODE_FFTS_PLUS, // 81 get ffts work mode, ffts plus
    RT_DEV_CAP_SUPPORT, // Capability Support
    RT_DEV_CAP_NOT_SUPPORT, // Capability not support
} rtDeviceCapabilityType;

typedef enum tagRtVersion {
    VER_BEGIN = 0,
    VER_NA = VER_BEGIN,
    VER_ES = 1,
    VER_CS = 2,
    VER_SD3403 = 3,
    VER_LITE = 4,
    VER_310M1 = 5,
    VER_END = 6,
} rtVersion_t;

/* match rtChipType_t */
typedef enum tagRtPlatformType {
    PLATFORM_BEGIN = 0,
    PLATFORM_MINI_V1 = PLATFORM_BEGIN,
    PLATFORM_CLOUD_V1 = 1,
    PLATFORM_MINI_V2 = 2,
    PLATFORM_LHISI_ES = 3,
    PLATFORM_LHISI_CS = 4,
    PLATFORM_DC = 5,
    PLATFORM_CLOUD_V2 = 6,
    PLATFORM_LHISI_SD3403 = 7,
    PLATFORM_MINI_V3 = 8,
    PLATFORM_MINI_5612 = 9,
    PLATFORM_CLOUD_V2_910B1 = 10,
    PLATFORM_CLOUD_V2_910B2 = 11,
    PLATFORM_CLOUD_V2_910B3 = 12,
    PLATFORM_MDC_BS9SX1A = 16,
    PLATFORM_MDC_AS31XM1X = 17,
    PLATFORM_MDC_LITE = 18,
    PLATFORM_MINI_V3_B1 = 19,
    PLATFORM_MINI_V3_B2 = 20,
    PLATFORM_MINI_V3_B3 = 21,
    PLATFORM_MINI_V3_B4 = 22,
    PLATFORM_1636 = 23,
    PLATFORM_CLOUD_V2_910B2C = 24,
    PLATFORM_DAVID_910_9599 = 26,
    PLATFORM_CLOUD_V2_910B4_1 = 27,
    PLATFORM_SOLOMON = 28,
    PLATFORM_DAVID_910_9589 = 29,
    PLATFORM_DAVID_910_958A = 30,
    PLATFORM_DAVID_910_958B = 31,
    PLATFORM_DAVID_910_957B = 32,
    PLATFORM_DAVID_910_957D = 33,
    PLATFORM_DAVID_910_950Z = 34,
    PLATFORM_MDC_MC62CM12A = 35,
    PLATFORM_DAVID_910_9579 = 36,
    PLATFORM_DAVID_910_9591 = 37,
    PLATFORM_DAVID_910_9592 = 38,
    PLATFORM_DAVID_910_9581 = 39,
    PLATFORM_DAVID_910_9582 = 40,
    PLATFORM_DAVID_910_9584 = 41,
    PLATFORM_DAVID_910_9587 = 42,
    PLATFORM_DAVID_910_9588 = 43,
    PLATFORM_DAVID_910_9572 = 44,
    PLATFORM_DAVID_910_9575 = 45,
    PLATFORM_DAVID_910_9576 = 46,
    PLATFORM_DAVID_910_9574 = 47,
    PLATFORM_DAVID_910_9577 = 48,
    PLATFORM_DAVID_910_9578 = 49,
    PLATFORM_END
} rtPlatformType_t;

typedef enum tagRtCubeFracMKNFp16 {
    RT_CUBE_MKN_FP16_2_16_16 = 0,
    RT_CUBE_MKN_FP16_4_16_16,
    RT_CUBE_MKN_FP16_16_16_16,
    RT_CUBE_MKN_FP16_Default,
} rtCubeFracMKNFp16_t;

typedef enum tagRtCubeFracMKNInt8 {
    RT_CUBE_MKN_INT8_2_32_16 = 0,
    RT_CUBE_MKN_INT8_4_32_4,
    RT_CUBE_MKN_INT8_4_32_16,
    RT_CUBE_MKN_INT8_16_32_16,
    RT_CUBE_MKN_INT8_Default,
} rtCubeFracMKNInt8_t;

typedef enum tagRtVecFracVmulMKNFp16 {
    RT_VEC_VMUL_MKN_FP16_1_16_16 = 0,
    RT_VEC_VMUL_MKN_FP16_Default,
} rtVecFracVmulMKNFp16_t;

typedef enum tagRtVecFracVmulMKNInt8 {
    RT_VEC_VMUL_MKN_INT8_1_32_16 = 0,
    RT_VEC_VMUL_MKN_INT8_Default,
} rtVecFracVmulMKNInt8_t;

typedef struct tagRtAiCoreSpec {
    uint32_t cubeFreq;
    uint32_t cubeMSize;
    uint32_t cubeKSize;
    uint32_t cubeNSize;
    rtCubeFracMKNFp16_t cubeFracMKNFp16;
    rtCubeFracMKNInt8_t cubeFracMKNInt8;
    rtVecFracVmulMKNFp16_t vecFracVmulMKNFp16;
    rtVecFracVmulMKNInt8_t vecFracVmulMKNInt8;
} rtAiCoreSpec_t;

typedef struct tagRtAiCoreRatesPara {
    uint32_t ddrRate;
    uint32_t l2Rate;
    uint32_t l2ReadRate;
    uint32_t l2WriteRate;
    uint32_t l1ToL0ARate;
    uint32_t l1ToL0BRate;
    uint32_t l0CToUBRate;
    uint32_t ubToL2;
    uint32_t ubToDDR;
    uint32_t ubToL1;
} rtAiCoreMemoryRates_t;

typedef struct tagRtMemoryConfig {
    uint32_t flowtableSize;
    uint32_t compilerSize;
} rtMemoryConfig_t;

typedef struct tagRtPlatformConfig {
    uint32_t platformConfig;
} rtPlatformConfig_t;

typedef enum tagRTTaskTimeoutType {
    RT_TIMEOUT_TYPE_OP_WAIT = 0,
    RT_TIMEOUT_TYPE_OP_EXECUTE,
} rtTaskTimeoutType_t;

typedef enum tagRTLastErrLevel {
    RT_THREAD_LEVEL = 0,
    RT_CONTEXT_LEVEL,
} rtLastErrLevel_t;
/**
 * @ingroup
 * @brief get AI core count
 * @param [in] aiCoreCnt
 * @return aiCoreCnt
 */
RTS_API rtError_t rtGetAiCoreCount(uint32_t *aiCoreCnt);

/**
 * @ingroup
 * @brief get AI cpu count
 * @param [in] aiCpuCnt
 * @return aiCpuCnt
 */
RTS_API rtError_t rtGetAiCpuCount(uint32_t *aiCpuCnt);

/**
 * @ingroup
 * @brief get AI core frequency
 * @param [in] aiCoreSpec
 * @return aiCoreSpec
 */
RTS_API rtError_t rtGetAiCoreSpec(rtAiCoreSpec_t *aiCoreSpec);

/**
 * @ingroup
 * @brief AI get core band Info
 * @param [in] aiCoreMemoryRates
 * @return aiCoreMemoryRates
 */
RTS_API rtError_t rtGetAiCoreMemoryRates(rtAiCoreMemoryRates_t *aiCoreMemoryRates);

/**
 * @ingroup
 * @brief AI get core buffer Info,FlowTable Size,Compiler Size
 * @param [in] memoryConfig
 * @return memoryConfig
 */
RTS_API rtError_t rtGetMemoryConfig(rtMemoryConfig_t *memoryConfig);

/**
 * @ingroup
 * @brief get l2 buffer Info,virtual baseaddr,Size
 * @param [in] stm
 * @return RT_ERROR_NONE for ok, errno for failed
 */
RTS_API rtError_t rtMemGetL2Info(rtStream_t stm, void **ptr, uint32_t *size);

/**
 * @ingroup
 * @brief get runtime version. The version is returned as (1000 major + 10 minor). For example, RUNTIME 9.2 would be
 *        represented by 9020.
 * @param [out] runtimeVersion
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtGetRuntimeVersion(uint32_t *runtimeVersion);


/**
 * @ingroup
 * @brief get device feature ability by device id, such as task schedule ability.
 * @param [in] deviceId
 * @param [in] moduleType
 * @param [in] featureType
 * @param [out] val
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtGetDeviceCapability(int32_t deviceId, int32_t moduleType, int32_t featureType, int32_t *val);

/**
 * @ingroup
 * @brief set event wait task timeout time.
 * @param [in] timeout
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtSetOpWaitTimeOut(uint32_t timeout);

/**
 * @ingroup
 * @brief set op execute task timeout time.
 * @param [in] timeout
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtSetOpExecuteTimeOut(uint32_t timeout);

/**
 * @ingroup
 * @brief set op execute task timeout time with ms.
 * @param [in] timeout/ms
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */

RTS_API rtError_t rtSetOpExecuteTimeOutWithMs(uint32_t timeout);
/**
 * @ingroup
 * @brief get op execute task timeout time.
 * @param [out] timeout
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtGetOpExecuteTimeOut(uint32_t * const timeout);

/**
 * @ingroup
 * @brief get op execute task timeout interval.
 * @param [out] interval op execute task timeout interval, unit:us
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtGetOpTimeOutInterval(uint64_t *interval);
 
/**
 * @ingroup
 * @brief set op execute task timeout.
 * @param [in] timeout  op execute task timeout, unit:us
 * @param [out] actualTimeout actual op execute task timeout, unit:us
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtSetOpExecuteTimeOutV2(uint64_t timeout, uint64_t *actualTimeout);

/**
 * @ingroup
 * @brief get the timeout duration for operator execution.
 * @param [out] timeout(ms)
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtGetOpExecuteTimeoutV2(uint32_t *const timeout);

/**
 * @ingroup
 * @brief get is Heterogenous.
 * @param [out] heterogenous=1 Heterogenous Mode: read isHeterogenous=1 in ini file.
 * @param [out] heterogenous=0 NOT Heterogenous Mode:
 *      1:not found ini file, 2:error when reading ini, 3:Heterogenous value is not 1
 * @return RT_ERROR_NONE for ok
 */
RTS_API rtError_t rtGetIsHeterogenous(int32_t *heterogenous);

/**
 * @ingroup
 * @brief get latest errcode and clear it.
 * @param [in] level error level for this api.
 * @return return for error code
 */
RTS_API rtError_t rtGetLastError(rtLastErrLevel_t level);

/**
 * @ingroup
 * @brief get latest errcode.
 * @param [in] level error level for this api.
 * @return return for error code
 */
RTS_API rtError_t rtPeekAtLastError(rtLastErrLevel_t level);
#if defined(__cplusplus)
}
#endif

#endif // CCE_RUNTIME_CONFIG_H
