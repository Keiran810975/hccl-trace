/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_INC_ADAPTER_ERROR_MANAGER_H
#define HCCL_INC_ADAPTER_ERROR_MANAGER_H

#include <string>
#include "log.h"
#include "adapter_error_manager_pub.h"
#include "base/err_msg.h"
#include "base/err_mgr.h"

using ErrContext = error_message::ErrorManagerContext;

ErrContext hrtErrMGetErrorContext(void);
void hrtErrMSetErrorContext(ErrContext error_context);

#endif  // HCCL_INC_ADAPTER_ERROR_MANAGER_H