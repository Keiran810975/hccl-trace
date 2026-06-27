/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <climits>
#include "read_write_lock_base.h"
#include "log.h"

// CPU 暂停指令定义
#if defined(__i386__) || defined(__x86_64__)
    #define CPU_PAUSE() __asm__ __volatile__("pause")
#else
    #define CPU_PAUSE() std::this_thread::yield()
#endif

void ReadWriteLockBase::readLock()
{
    uint64_t s = state_.load(std::memory_order_relaxed);

    while (true) {
        // 检查是否有写者正在写或者有写者在等待
        if (!(s & (WRITING_BIT | WAITING_BIT))) {
            // 尝试原子增加读者计数
            uint64_t newS = s + 1;
            if (state_.compare_exchange_weak(s, newS, std::memory_order_acquire, std::memory_order_relaxed)) {
                return;     // 成功增加读者计数
            }
        } else {
            CPU_PAUSE();    // 避免过度占用CPU资源
            s = state_.load(std::memory_order_relaxed);
        }
    }
}

void ReadWriteLockBase::readUnlock()
{
    // 原子减少读者计数
    state_.fetch_sub(1, std::memory_order_release);
}

void ReadWriteLockBase::writeLock()
{
    uint64_t s;

    // 第一步：标记有写者在等待，阻断后续读者进入
    s = state_.fetch_or(WAITING_BIT, std::memory_order_relaxed);

    // 第二步：循环尝试获取真正的写入权限
    while (true) {
        s = state_.load(std::memory_order_relaxed);

        // 只有当没有其他写者并且没有读者时，才写入
        if (!(s & WRITING_BIT) && (s & READER_MASK) == 0) {
            // 尝试原子设置写入标志位 WRITING_BIT 并清除 WAITING_BIT
            uint64_t nextS = (s | WRITING_BIT) & ~WAITING_BIT;
            if (state_.compare_exchange_weak(s, nextS, 
                    std::memory_order_acquire,
                    std::memory_order_relaxed)) {
                return;     // 成功获取写入权限
            }
        }
    
        CPU_PAUSE();    // 避免过度占用CPU资源 
    }
}

void ReadWriteLockBase::writeUnlock()
{
    // 原子清除写入标志位
    state_.fetch_and(~WRITING_BIT, std::memory_order_release);
}

bool ReadWriteLockBase::tryReadLock()
{
    uint64_t s = state_.load(std::memory_order_relaxed);

    // 检查是否有写者正在写或者有写者在等待
    if (s & (WRITING_BIT | WAITING_BIT)) {
        return false;     // 有写者正在写或者有写者在等待，无法获取读者锁
    }

    // 尝试原子增加读者计数
    uint64_t newS = s + 1;
    if (state_.compare_exchange_weak(s, newS, 
            std::memory_order_acquire,
            std::memory_order_relaxed)) {
        return true;     // 成功增加读者计数
    }

    return false;     // 无法获取读者锁
}

// 用于背景线程轮询的优化方法
void ReadWriteLockBase::fastReadUnlock()
{
    // 快速释放读锁，不进行复杂检查
    state_.fetch_sub(1, std::memory_order_release);
}