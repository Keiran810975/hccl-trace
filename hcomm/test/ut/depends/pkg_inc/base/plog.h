/**
 * @plog.h
 *
 * Copyright (c) Huawei Technologies Co., Ltd. 2019-2024. All rights reserved.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 */

#ifndef PLOG_H_
#define PLOG_H_

#ifdef __cplusplus
#ifndef LOG_CPP
extern "C" {
#endif
#endif // __cplusplus

#if defined(_MSC_VER)
#define LOG_FUNC_VISIBILITY _declspec(dllexport)
#else
#define LOG_FUNC_VISIBILITY __attribute__((visibility("default")))
#endif

/**
 * @ingroup plog
 * @brief DlogReportInitialize: init log in service process before all device setting.
 * @return: 0: SUCCEED, others: FAILED
 */
LOG_FUNC_VISIBILITY int DlogReportInitialize(void) __attribute((weak));

/**
 * @ingroup plog
 * @brief DlogReportFinalize: release log resource in service process after all device reset.
 * @return: 0: SUCCEED, others: FAILED
 */
LOG_FUNC_VISIBILITY int DlogReportFinalize(void) __attribute((weak));

/**
 * @ingroup     : plog
 * @brief       : create thread to recv log from device
 * @param[in]   : devId         device id
 * @param[in]   : mode          use macro LOG_SAVE_MODE_XXX in slog.h
 * @return      : 0: SUCCEED, others: FAILED
 */
LOG_FUNC_VISIBILITY int DlogReportStart(int devId, int mode) __attribute((weak));

/**
 * @ingroup     : plog
 * @brief       : stop recv thread
 * @param[in]   : devId         device id
 */
LOG_FUNC_VISIBILITY void DlogReportStop(int devId) __attribute((weak));


#ifdef __cplusplus
#ifndef LOG_CPP
}
#endif // LOG_CPP
#endif // __cplusplus
#endif // PLOG_H_
