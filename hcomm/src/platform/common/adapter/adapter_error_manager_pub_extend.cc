#include "adapter_error_manager.h"
#include "adapter_error_manager_pub.h"
#include "base/err_msg.h"
#include "base/err_mgr.h"

void RptInputErr(std::string error_code, std::vector<std::string> key,
    std::vector<std::string> value)
{
    // 将 std::vector<std::string> 转换为 std::vector<const char*>
    std::vector<const char*> key_cstr;
    for (const auto& k : key) {
        key_cstr.push_back(k.c_str());
    }
    
    std::vector<const char*> value_cstr;
    for (const auto& v : value) {
        value_cstr.push_back(v.c_str());
    }
    
    // 调用 REPORT_PREDEFINED_ERR_MSG
    REPORT_PREDEFINED_ERR_MSG(error_code.c_str(), key_cstr, value_cstr);
    return;
}

void RptEnvErr(std::string error_code, std::vector<std::string> key,
    std::vector<std::string> value)
{
    // 将 std::vector<std::string> 转换为 std::vector<const char*>
    std::vector<const char*> key_cstr;
    for (const auto& k : key) {
        key_cstr.push_back(k.c_str());
    }
    
    std::vector<const char*> value_cstr;
    for (const auto& v : value) {
        value_cstr.push_back(v.c_str());
    }
    
    // 调用 REPORT_PREDEFINED_ERR_MSG
    REPORT_PREDEFINED_ERR_MSG(error_code.c_str(), key_cstr, value_cstr);
    return;
}

void RptInnerErrPrt(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    char errorMsgStr[HCCL_LIMIT_PER_MESSAGE] = {};
    int ret = vsnprintf_s(errorMsgStr, HCCL_LIMIT_PER_MESSAGE, HCCL_LIMIT_PER_MESSAGE - 1U, fmt, args);
    va_end(args);
    if (ret == -1) {
        return;
    }
    REPORT_INNER_ERR_MSG(HCCL_RPT_CODE, "%s", errorMsgStr);
}

void RptCallErr(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    char errorMsgStr[HCCL_LIMIT_PER_MESSAGE] = {};
    int ret = vsnprintf_s(errorMsgStr, HCCL_LIMIT_PER_MESSAGE, HCCL_LIMIT_PER_MESSAGE - 1U, fmt, args);
    va_end(args);
    if (ret == -1) {
        return;
    }
    REPORT_INNER_ERR_MSG(HCCL_RPT_CODE, "%s", errorMsgStr);
}

void RptCallErrPrt(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    char errorMsgStr[HCCL_LIMIT_PER_MESSAGE] = {};
    int ret = vsnprintf_s(errorMsgStr, HCCL_LIMIT_PER_MESSAGE, HCCL_LIMIT_PER_MESSAGE - 1U, fmt, args);
    va_end(args);
    if (ret == -1) {
        return;
    }
    REPORT_INNER_ERR_MSG(HCCL_RPT_CODE, "%s", errorMsgStr);
}