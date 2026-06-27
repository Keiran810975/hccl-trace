/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_THREAD_H
#define HCCL_THREAD_H

#include "stream_pub.h"
#include "local_notify.h"
#include "hccl_common.h"

namespace hccl {
class HcclThread {
public:
    HcclThread(rtStream_t rtStream, u32 notifyNum, const NotifyLoadType notifyLoadType);
    HcclThread(StreamType streamType, u32 notifyNum, const NotifyLoadType notifyLoadType);
    HcclThread(const std::string& uniqueIdStr);

    ~HcclThread();

    HcclResult Init();
    HcclResult DeInit();

    // Init成功后调用GetUniqueId和获取属性接口
    std::string &GetUniqueId();

    inline Stream* GetStream() const {
        return stream_.get();
    }

    inline LocalNotify* GetNotify(u32 index) const {
        if (index > notifyNum_) {
            HCCL_ERROR("[HcclThread][GetNotify]notifyNum[%u], notifyIdx[%u] out of range[0, %u]", \
                notifyNum_, index, (notifyNum_ == 0 ? 0 : notifyNum_ - 1));
            return nullptr;
        }
        return notifys_[index].get();
    }

    inline u32 GetNotifyNum()
    {
        return notifyNum_;
    }

private:
    struct HcclStreamInfo {
        s32 streamIds;
        u32 sqIds;
        u32 cqIds;   // 记录物理cqId
        u32 logicCqids; // 记录逻辑cqId
    };

    // 记录aicpu-custom共享的stream信息
    struct HcclStreamParam {
        HcclStreamInfo streamInfo;
        u64 sqCqContextAddr = 0; // 记录sqeContext地址
        u64 sqCqContextSize = 0; // 记录sqeContext大小
    };
    HcclResult InitStream(HcclStreamParam &streamParam);

    bool isDeviceSide_ = false;
    rtStream_t rtStream_ = nullptr;
    StreamType streamType_ = StreamType::STREAM_TYPE_RESERVED;
    u32 notifyNum_ = 0;
    NotifyLoadType notifyLoadType_ = NotifyLoadType::HOST_NOTIFY;
    u32 devId_ = INVALID_UINT;
    std::unique_ptr<Stream> stream_ = nullptr;
    std::vector<std::unique_ptr<LocalNotify>> notifys_;
    std::string uniqueIdStr_;
    DeviceMem sqCqeContext_;
};

inline Stream* GetStream(uint64_t thread) {
    HcclThread *threadPtr = reinterpret_cast<HcclThread*>(thread);
    if (UNLIKELY(threadPtr == nullptr)) {
        HCCL_ERROR("[HcclThread][GetStream]thread is nullptr");
        return nullptr;
    }
    return threadPtr->GetStream();
}


inline LocalNotify* GetNotify(uint64_t thread, u32 index) {
    HcclThread *threadPtr = reinterpret_cast<HcclThread*>(thread);
    if (UNLIKELY(threadPtr == nullptr)) {
        HCCL_ERROR("[HcclThread][GetStream]thread is nullptr");
        return nullptr;
    }
    return threadPtr->GetNotify(index);
}

}  // namespace hccl

#endif /* * HCCL_THREAD_H */
