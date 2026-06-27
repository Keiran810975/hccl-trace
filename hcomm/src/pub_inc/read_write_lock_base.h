/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef READ_WRITE_LOCK_BASE_H
#define READ_WRITE_LOCK_BASE_H

#include <mutex>
#include <climits>
#include <atomic>
#include <thread>
#include <condition_variable>

class ReadWriteLockBase {
public:
    ReadWriteLockBase() {}
    void readLock();
    void readUnlock();
    void writeLock();
    void writeUnlock();
    bool tryReadLock();
    void fastReadUnlock();

private:
    // 使用复合状态变量优化新年
    std::atomic<uint64_t> state_{0};

    // 状态位定义
    static constexpr uint64_t WRITING_BIT = 1ULL << 63;                 // 写入标志位
    static constexpr uint64_t WAITING_BIT = 1ULL << 62;                 // 等待写者标志位
    static constexpr uint64_t READER_MASK = 0x3FFFFFFFFFFFFFFFULL;      // 读者计数掩码（62位）
    
    // 最大读者数和写者数限制
    static constexpr uint64_t MAX_READERS = 0x3FFFFFFFFFFFFFFFULL;      // 最大读者（62位）
    static constexpr uint64_t MAX_WRITERS = 0xFFFFFFFFULL;              // 限制写者等待数（2^32）
};

#endif  // READ_WRITE_LOCK_BASE_H
