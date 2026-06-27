/**
 * Copyright (c) Huawei Technologies Co., Ltd. 2024. All rights reserved.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 *
 * Description:interface.
 * Create: 2024-04-01
 */
 
#ifndef AICPU_MC2_MAINTENANCE_THREAD_H
#define AICPU_MC2_MAINTENANCE_THREAD_H
// error code for mc2
constexpr int32_t AICPU_SCHEDULE_PARAMETER_IS_NULL = 21600;
constexpr int32_t AICPU_SCHEDULE_THREAD_ALREADY_EXISTS = 21601;
constexpr int32_t AICPU_SCHEDULE_NOT_SUPPORT = 21602;

using AicpuCtrlThreadFuncPtr = void(*)(void *);

enum AicpuCtrlThreadType : uint32_t {
    THREAD_TYPE_HCOM = 0,
    THREAD_TYPE_ASCPP_PROF = 1,
};
#ifdef __cplusplus
extern "C" {
#endif // __cplusplus
__attribute__((weak)) __attribute__((visibility("default"))) int32_t AicpuCreateCtrlThread(uint32_t type, AicpuCtrlThreadFuncPtr loopFun,
    void *paramLoopFun, AicpuCtrlThreadFuncPtr stopNotifyFun, void *paramStopFun);

#ifdef __cplusplus
}
#endif
#endif // AICPU_MC2_MAINTENANCE_THREAD_H