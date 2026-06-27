/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 *
 * The code snippet comes from linux-rdma project
 * 
 * Copyright (c) 2018, Mellanox Technologies inc.  All rights reserved.
 * 
 *           OpenIB.org BSD license (MIT variant)
 * 
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 
 *   - Redistributions of source code must retain the above copyright notice,
 *     this list of conditions and the following disclaimer.
 * 
 *   - Redistributions in binary form must reproduce the above copyright notice,
 *     this list of conditions and the following disclaimer in the documentation
 *     and/or other materials provided with the distribution.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#ifndef RDMA_USER_IOCTL_CMDS_H
#define RDMA_USER_IOCTL_CMDS_H

#include <linux/types.h>
#include <linux/ioctl.h>

/* Documentation/userspace-api/ioctl/ioctl-number.rst */
#define RDMA_IOCTL_MAGIC	0x1b
#define RDMA_VERBS_IOCTL \
	_IOWR(RDMA_IOCTL_MAGIC, 1, struct ib_uverbs_ioctl_hdr)

enum {
	/* User input */
	UVERBS_ATTR_F_MANDATORY = 1U << 0,
	/*
	 * Valid output bit should be ignored and considered set in
	 * mandatory fields. This bit is kernel output.
	 */
	UVERBS_ATTR_F_VALID_OUTPUT = 1U << 1,
};

struct ib_uverbs_attr {
	__u16 attr_id;		/* command specific type attribute */
	__u16 len;		/* only for pointers and IDRs array */
	__u16 flags;		/* combination of UVERBS_ATTR_F_XXXX */
	union {
		struct {
			__u8 elem_id;
			__u8 reserved;
		} enum_data;
		__u16 reserved;
	} attr_data;
	union {
		/*
		 * ptr to command, inline data, idr/fd or
		 * ptr to __u32 array of IDRs
		 */
		__aligned_u64 data;
		/* Used by FD_IN and FD_OUT */
		__s64 data_s64;
	};
};

struct ib_uverbs_ioctl_hdr {
	__u16 length;
	__u16 object_id;
	__u16 method_id;
	__u16 num_attrs;
	__aligned_u64 reserved1;
	__u32 driver_id;
	__u32 reserved2;
	struct ib_uverbs_attr  attrs[0];
};

#endif
