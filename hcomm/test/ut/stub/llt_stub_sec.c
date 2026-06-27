#include "securec.h"
#include <stdlib.h>

extern int sec_cpy_ret;
int g_sprintf_s_flag = 0;
int g_sprintf_s_flag1 = 1;

SECUREC_API errno_t strcpy_s(char *strDest, size_t destMax, const char *strSrc)
{
    strcpy(strDest, strSrc);
    return 0;
}

SECUREC_API errno_t strncpy_s(char *strDest, size_t destMax, const char *strSrc, size_t count)
{
	strncpy(strDest, strSrc, count);
	return 0;
}

errno_t memcpy_sOptAsm(void *dest, size_t destMax, const void *src, size_t count)
{
    return memcpy_s(dest, destMax, src, count);
}

SECUREC_API errno_t memmove_s(void *dest, size_t destMax, const void *src, size_t count)
{
	memmove(dest, src, count);
	return 0;
}

int vsnprintf_s(char* strDest, size_t destMax, size_t count, const char* format, va_list arglist)
{
    vsnprintf(strDest, count, format, arglist);
    if(g_sprintf_s_flag1 > 0) {
        return 0;
    }
    else {
        return -1;
    }
}