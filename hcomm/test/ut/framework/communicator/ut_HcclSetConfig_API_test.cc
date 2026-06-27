/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "hccl_api_base_test.h"

class HcclSetConfigTest : public BaseInit {
public:
    void SetUp() override {
        BaseInit::SetUp();
    }
    void TearDown() override {
        BaseInit::TearDown();
        GlobalMockObject::verify();
    }
};

TEST_F(HcclSetConfigTest, Ut_HcclSetConfig_When_ConfigValueIsNotInDeterministicEnableLevel_Expect_ReturnIsHCCL_E_PARA)
{
    HcclConfigValue value;
    value.value = 3;

    HcclResult ret = HcclSetConfig(HCCL_DETERMINISTIC, value);
    EXPECT_EQ(ret, HCCL_E_PARA);
}

TEST_F(HcclSetConfigTest, Ut_HcclSetConfig_When_ConfigValueIsSTRICTButDevTypeIsNot910B_Expect_ReturnIsHCCL_E_NOT_SUPPORT)
{
    HcclConfigValue value;
    value.value = DETERMINISTIC_STRICT;
    DevType deviceType = DevType::DEV_TYPE_910_93;
    MOCKER(hrtGetDeviceType)
        .stubs()
        .with(outBound(deviceType))
        .will(returnValue(HCCL_SUCCESS));
    
    HcclResult ret = HcclSetConfig(HCCL_DETERMINISTIC, value);
    EXPECT_EQ(ret, HCCL_E_NOT_SUPPORT);
}

TEST_F(HcclSetConfigTest, Ut_HcclSetConfigTest_When_Normal_Expect_ReturnIsHCCL_SUCCESS)
{
    union HcclConfigValue hcclConfigValue;
    hcclConfigValue.value = 1;

    HcclResult ret = HcclSetConfig(HCCL_DETERMINISTIC, hcclConfigValue);
    EXPECT_EQ(ret, HCCL_SUCCESS);

    hcclConfigValue.value = 0;

    ret = HcclSetConfig(HCCL_DETERMINISTIC, hcclConfigValue);
    EXPECT_EQ(ret, HCCL_SUCCESS);
}

TEST_F(HcclSetConfigTest, Ut_HcclSetConfig_When_SetEnvHCCL_DETERMINISTIC_Expect_ReturnIsHCCL_SUCCESS)
{
    setenv("HCCL_DETERMINISTIC", "true", 1);
    HcclConfigValue value;
    value.value = 3;

    HcclResult ret = HcclSetConfig(HCCL_DETERMINISTIC, value);
    EXPECT_EQ(ret, HCCL_SUCCESS);
    
    unsetenv("HCCL_DETERMINISTIC");
}
