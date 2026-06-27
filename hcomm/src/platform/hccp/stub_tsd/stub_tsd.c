#include <sys/types.h>
#include <unistd.h>
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    TSD_HCCP = 0,    /**< HCCP*/
    TSD_COMPUTE, /**< Compute_process*/
    TSD_CUSTOM_COMPUTE, /**< Custom Compute_process*/
    TSD_QS,
    TSD_WAITTYPE_MAX /**< Max*/
} TsdWaitType;

/**
* @ingroup SendStartUpFinishMsg
* @brief sub process start finisn and Wait for the TSD process to issue the shutdown command
*
* @par Function
* Wait for the TSD process to issue the shutdown command
*
* @param NA
* @param deviceId [IN] type #unsigned int. Physical device ID
* @param waitType [IN] type #TsdWaitType. HCCP or CP
* @param hostPid [IN] type #unsigned int. Host pid
* @param vfId [IN] type #unsigned int. Virtual force Id
* @retval 0 Success
* @retval OtherValues 0 Fail
*
* @par Dependency
* @li libtsdppc.so: Library to which the interface belongs.
* @li tsd.h: Header file where the interface declaration is located.
*/
int32_t SendStartUpFinishMsg(const uint32_t deviceId, const TsdWaitType waitType,
                             const uint32_t hostPid, const uint32_t vfId)
{
    return 0;
}

/**
* @ingroup tsd_event_client
* @brief sub process send error code while start/stop period
* @param [in] deviceId : device id
* @param [in] waitType : process type
* @param [in] hostPid :  host pid
* @param [in] vfId : vf id
* @param [in] errCode : errCode: errMsg code produced by host
* @param [in] errLen : errLen: errMsg code length
* @return TSD_OK: sucess, other: error code
*/
int32_t ReportProcessStartUpErrorCode(const uint32_t deviceId, const TsdWaitType waitType,
                                      const uint32_t hostPid, const uint32_t vfId,
                                      const char *errCode, const uint32_t errLen)
{
    return 0;
}