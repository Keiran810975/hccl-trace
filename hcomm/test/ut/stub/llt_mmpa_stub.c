#include "mmpa_api.h"
#include <dlfcn.h>
#include "ascend_hal.h"

#define MAP_SIZE 3U
int32_t g_drvHandle = 0;
typedef void* ArgPtr;
typedef struct {
    const char *symbol;
    ArgPtr handle;
} SymbolInfo;

static SymbolInfo g_drvMap[MAP_SIZE] = {
    { "drvGetPlatformInfo", (void *)drvGetPlatformInfo },
    { "drvGetDevNum", (void *)drvGetDevNum },
    { "halGetAPIVersion", (void *)halGetAPIVersion },
};

void * mmDlopen(const char *fileName, int mode)
{
    return NULL;
}

int32_t mmDlclose(void *handle)
{
    return 0;
}

void *mmDlsym(void *handle, const char* funcName)
{
    return NULL;
}

int32_t mmGetErrorCode()
{
    return 0;
}
int32_t mmMutexInit(mmMutex_t *mutex)
{
    return EN_OK;
}
 
int32_t mmMutexDestroy(mmMutex_t *mutex)
{
    return EN_OK;
}
 
int32_t mmMutexLock(mmMutex_t *mutex)
{
    return EN_OK;
}
 
int32_t mmMutexUnLock(mmMutex_t *mutex)
{
    return EN_OK;
}

int32_t mmRmdir(const char *pathName)
{
    return EN_OK;
}

mmTimespec mmGetTickCount(VOID)
{
    mmTimespec rts = {0};
    return rts;
}

INT32 mmGetTimeOfDay(mmTimeval *timeVal, mmTimezone *timeZone)
{
    return EN_OK;
}

INT32 mmLocalTimeR(const time_t *timep, struct tm *result)
{
    return EN_OK;
}

INT32 mmRealPath(const CHAR *path, CHAR *realPath, INT32 realPathLen)
{
    return EN_OK;
}

INT32 mmAccess2(const CHAR *pathName, INT32 mode)
{
    return EN_OK;
}

int mmGetPid()
{
    return 0;
}

static int32_t LocalSetSchedThreadAttr(pthread_attr_t *attr, const mmThreadAttr *threadAttr)
{
    return 0;
}

static int32_t LocalSetToolThreadAttr(pthread_attr_t *attr, const mmThreadAttr *threadAttr)
{
    return 0;
}

int32_t mmCreateTaskWithThreadAttr(mmThread *threadHandle, const mmUserBlock_t *funcBlock,
    const mmThreadAttr *threadAttr)
{
    return 0;
}

int32_t mmJoinTask(mmThread *threadHandle)
{
    return 0;
}

int32_t mmSetCurrentThreadName(const char* name)
{
    return EN_OK;
}

int32_t mmCondInit(mmCond *cond)
{
    return 0;
}

int32_t mmCondNotify(mmCond *cond)
{
    return 0;
}

int32_t mmCondTimedWait(mmCond *cond, mmMutexFC *mutex, uint32_t milliSecond)
{
    return 0;
}

int32_t mmSocket(int32_t sockFamily, int32_t type, int32_t protocol)
{
    return 0;
}

int32_t mmBind(mmSockHandle sockFd, mmSockAddr * addr, mmSocklen_t addrLen)
{
    return EN_OK;
}

int32_t mmConnect(mmSockHandle sockFd, mmSockAddr * addr, mmSocklen_t addrLen)
{
    return EN_OK;
}

int32_t mmCloseSocket(mmSockHandle sockFd)
{
    return EN_OK;
}

int32_t mmDladdr(void *addr, mmDlInfo *info)
{
    return EN_OK;
}

char *mmDlerror(void) {
  return '0';
}

typedef struct {
    mmEnvId id;
    const CHAR *name;
} mmEnvInfo;

static mmEnvInfo s_envList[] = {
    {MM_ENV_DUMP_GRAPH_PATH, "DUMP_GRAPH_PATH"},
    {MM_ENV_ACLNN_CACHE_LIMIT, "ACLNN_CACHE_LIMIT"},
    {MM_ENV_ASCEND_WORK_PATH, "ASCEND_WORK_PATH"},
    {MM_ENV_ASCEND_HOSTPID, "ASCEND_HOSTPID"},
    {MM_ENV_RANK_ID, "RANK_ID"},
    {MM_ENV_ASCEND_RT_VISIBLE_DEVICES, "ASCEND_RT_VISIBLE_DEVICES"},
    {MM_ENV_ASCEND_COREDUMP_SIGNAL, "ASCEND_COREDUMP_SIGNAL"},
    {MM_ENV_ASCEND_CACHE_PATH, "ASCEND_CACHE_PATH"},
    {MM_ENV_ASCEND_OPP_PATH, "ASCEND_OPP_PATH"},
    {MM_ENV_ASCEND_CUSTOM_OPP_PATH, "ASCEND_CUSTOM_OPP_PATH"},
    {MM_ENV_ASCEND_LOG_DEVICE_FLUSH_TIMEOUT, "ASCEND_LOG_DEVICE_FLUSH_TIMEOUT"},
    {MM_ENV_ASCEND_LOG_SAVE_MODE, "ASCEND_LOG_SAVE_MODE"},
    {MM_ENV_ASCEND_SLOG_PRINT_TO_STDOUT, "ASCEND_SLOG_PRINT_TO_STDOUT"},
    {MM_ENV_ASCEND_GLOBAL_EVENT_ENABLE, "ASCEND_GLOBAL_EVENT_ENABLE"},
    {MM_ENV_ASCEND_GLOBAL_LOG_LEVEL, "ASCEND_GLOBAL_LOG_LEVEL"},
    {MM_ENV_ASCEND_MODULE_LOG_LEVEL, "ASCEND_MODULE_LOG_LEVEL"},
    {MM_ENV_ASCEND_HOST_LOG_FILE_NUM, "ASCEND_HOST_LOG_FILE_NUM"},
    {MM_ENV_ASCEND_PROCESS_LOG_PATH, "ASCEND_PROCESS_LOG_PATH"},
    {MM_ENV_ASCEND_LOG_SYNC_SAVE, "ASCEND_LOG_SYNC_SAVE"},
    {MM_ENV_PROFILER_SAMPLECONFIG, "PROFILER_SAMPLECONFIG"},
    {MM_ENV_ACP_PIPE_FD, "ACP_PIPE_FD"},
    {MM_ENV_PROFILING_MODE, "PROFILING_MODE"},
    {MM_ENV_DYNAMIC_PROFILING_KEY_PID, "DYNAMIC_PROFILING_KEY_PID"},
    {MM_ENV_HOME, "HOME"},
    {MM_ENV_AOS_TYPE, "AOS_TYPE"},
    {MM_ENV_LD_LIBRARY_PATH, "LD_LIBRARY_PATH"},
};

static mmEnvInfo *GetEnvInfoById(mmEnvId id)
{
    return NULL;
}

CHAR *mmSysGetEnv(mmEnvId id)
{

    return NULL;
}

INT32 mmSysSetEnv(mmEnvId id, const CHAR *value, INT32 overwrite)
{
    return 0;
}