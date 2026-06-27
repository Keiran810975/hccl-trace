/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#include <unistd.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <errno.h>
#include "tsd.h"
#ifndef CONFIG_HCCP_LLT
#include "dlog_pub.h"
#endif
#include "user_log.h"
#include "param.h"
#include "ra_adp.h"
#include "securec.h"
#include "dl_ibverbs_function.h"
#include "dl_hal_function.h"

#ifdef CONFIG_CGROUP
typedef void (*SighandlerT)(int);

STATIC int HccpAddToCgroup()
{
    int ret;
    pid_t hccpPid;
    SighandlerT oldHandler;
    char cmd[HCCP_CMD_MAX_LEN] = {0};

    hccpPid = getpid();
    CHK_PRT_RETURN(hccpPid < 0, hccp_err("getpid error[%d]", hccpPid), -EINVAL);

    ret = snprintf_s(cmd, HCCP_CMD_MAX_LEN, HCCP_CMD_MAX_LEN - 1,
        "cd /var/  && sudo ./add_to_cgroup_usermemory.sh hccp_service.bin");
    CHK_PRT_RETURN(ret <= 0, hccp_err("snprintf_s for cmd failed, %d", ret), -EINVAL);

    oldHandler = signal(SIGCHLD, SIG_DFL);
    ret = system(cmd);
    (void)signal(SIGCHLD, oldHandler);
    CHK_PRT_RETURN(ret == -1 || ret == HCCP_KEY_EXPIRED, hccp_err("add to cgroup failed, ret[%d], errno[%d]",
        ret, errno), -1);

    return 0;
}
#endif

STATIC int HccpChangeNumOfFile()
{
    struct rlimit limit = {0, 0};
    int ret;

    ret = getrlimit(RLIMIT_NOFILE, &limit);
    CHK_PRT_RETURN(ret, hccp_err("getrlimit failed, ret = %d, errno = %d\n", ret, errno), ret);

    limit.rlim_cur = limit.rlim_max;
    ret = setrlimit(RLIMIT_NOFILE, &limit);
    CHK_PRT_RETURN(ret, hccp_err("setrlimit failed, ret = %d, errno = %d\n", ret, errno), ret);

    return 0;
}

STATIC int HccpSetLogInfo(struct HccpInitParam *param)
{
#define HUNDREDS_DIGIT                 100
    int ret;
    int enableEvent = param->logLevel / HUNDREDS_DIGIT;
    int level = param->logLevel % HUNDREDS_DIGIT;
#ifndef CONFIG_HCCP_LLT
    LogAttr logattr = {0};

    logattr.type = APPLICATION;
    logattr.pid = param->pid;
    logattr.deviceId = param->backupFlag ? param->backupChipId : param->chipId;
    ret = dlog_setlevel(-1, level, enableEvent);
    CHK_PRT_RETURN(ret, hccp_err("hccp set log level failed, ret:%d, log level:%d, enableEvent:%d",
        ret, level, enableEvent), ret);

    ret = DlogSetAttr(logattr);
    CHK_PRT_RETURN(ret, hccp_err("hccp set attr chip_id:%u, backupFlag:%d, backupChipId:%u failed, ret:%d",
        param->chipId, param->backupFlag, param->backupChipId, ret), ret);
#endif
    return 0;
}

#ifndef CONFIG_HCCP_LLT
int main(int argc, char *argv[])
#else
int llt_main(int argc, char *argv[])
#endif
{
    int ret;
    struct HccpInitParam param = {0};
    struct timeval start, end;
    float timeCost = 0.0;

    hccp_run_info("hccp init start!");
    ret = HccpChangeNumOfFile();
    CHK_PRT_RETURN(ret, hccp_err("hccp change limit of nofile failed, ret = %d", ret), ret);

#ifdef CONFIG_CGROUP
    ret = HccpAddToCgroup();
    CHK_PRT_RETURN(ret, hccp_err("hccp_add_to_cgroup error[%d]", ret), ret);
#endif

    ret = DlHalInit();
    CHK_PRT_RETURN(ret, hccp_err("dl_hal_init error[%d]", ret), ret);

    ret = HccpParamParse(argc, argv, &param);
    if (ret != 0) {
        hccp_err("hccp_param_parse error[%d]", ret);
        goto out;
    }

    ret = HccpSetLogInfo(&param);
    if (ret != 0) {
        hccp_err("hccp_set_log_info error[%d]", ret);
        goto out;
    }

    RsGetCurTime(&start);

    ret = RsApiInit();
    if (ret != 0) {
        hccp_err("rs_api_init error[%d]", ret);
        goto out;
    }

    ret = HccpInit(param.chipId, param.pid, param.hdcType, param.whiteListStatus);
    if (ret) {
        ReportProcessStartUpErrorCode((uint32_t)param.logicId, 0, (uint32_t)param.pid, 0, ERR_EJ1, ERR_LEN);
        hccp_err("hccp init error[%d]", ret);
        goto hccp_init_fail;
    }

    RsGetCurTime(&end);
    HccpTimeInterval(&end, &start, &timeCost);
    hccp_run_info("hccp init ok cost [%f] ms logic_id[%d], tgid[%d]", timeCost, param.logicId, param.pid);

    ret = SendStartUpFinishMsg((uint32_t)param.logicId, 0, (uint32_t)param.pid, 0);
    if (ret) {
        hccp_err("SendStartUpFinishMsg error[%d]", ret);
    }

    ret = HccpDeinit(param.chipId);
    if (ret) {
        hccp_err("hccp deinit error[%d]", ret);
        goto hccp_init_fail;
    }

    hccp_run_info("hccp deinit ok! logic_id=%d", param.logicId);

hccp_init_fail:
    RsApiDeinit();
out:
    DlHalDeinit();
    return ret;
}
