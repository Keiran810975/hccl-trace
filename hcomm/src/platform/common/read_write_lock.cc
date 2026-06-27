/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "read_write_lock.h"


ReadWriteLock::~ReadWriteLock()
{
    while (writersNum_ > 0) {
        writeUnlock();
    }

    while (readersNum_ > 0) {
        readUnlock();
    }
}

void ReadWriteLock::readLock()
{
    rwlock_.readLock();
    readersNum_++;
}

void ReadWriteLock::readUnlock()
{
    rwlock_.readUnlock();
    readersNum_--;
}

void ReadWriteLock::writeLock()
{
    rwlock_.writeLock();
    writersNum_++;
}

void ReadWriteLock::writeUnlock()
{
    rwlock_.writeUnlock();
    writersNum_--;
}
