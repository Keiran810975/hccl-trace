/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef READ_WRITE_LOCK_H
#define READ_WRITE_LOCK_H

#include <atomic>
#include "read_write_lock_base.h"

class ReadWriteLock {
public:
    ReadWriteLock(ReadWriteLockBase &rwlock) : rwlock_(rwlock), readersNum_(0), writersNum_(0) {}
    ~ReadWriteLock();
    void readLock();
    void readUnlock();
    void writeLock();
    void writeUnlock();

private:
    ReadWriteLockBase &rwlock_;
    std::atomic<int> readersNum_{0};  // num of readers
    std::atomic<int> writersNum_{0};  // num of waiting readers
};

#endif  // READ_WRITE_LOCK_H
