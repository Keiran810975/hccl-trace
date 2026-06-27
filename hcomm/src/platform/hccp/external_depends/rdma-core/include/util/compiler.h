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

#ifndef UTIL_COMPILER_H
#define UTIL_COMPILER_H

/* Use to tag a variable that causes compiler warnings. Use as:
    int uninitialized_var(sz)

   This is only enabled for old compilers. gcc 6.x and beyond have excellent
   static flow analysis. If code solicits a warning from 6.x it is almost
   certainly too complex for a human to understand. For some reason powerpc
   uses a different scheme than gcc for flow analysis.
*/
#if (__GNUC__ >= 6 && !defined(__powerpc__)) || defined(__clang__)
#define uninitialized_var(x) x
#else
#define uninitialized_var(x) x = x
#endif

#ifndef likely
#ifdef __GNUC__
#define likely(x)       __builtin_expect(!!(x), 1)
#else
#define likely(x)      (x)
#endif
#endif

#ifndef unlikely
#ifdef __GNUC__
#define unlikely(x)      __builtin_expect(!!(x), 0)
#else
#define unlikely(x)    (x)
#endif
#endif

#ifdef HAVE_FUNC_ATTRIBUTE_ALWAYS_INLINE
#define ALWAYS_INLINE __attribute__((always_inline))
#else
#define ALWAYS_INLINE
#endif

/* Use to mark fall through on switch statements as desired. */
#if __GNUC__ >= 7
#define SWITCH_FALLTHROUGH __attribute__ ((fallthrough))
#else
#define SWITCH_FALLTHROUGH
#endif

#ifdef __CHECKER__
# define __force __attribute__((force))
#else
# define __force
#endif

#endif
