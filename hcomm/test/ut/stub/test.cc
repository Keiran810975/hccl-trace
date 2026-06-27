#include <stdio.h>
#include <stdlib.h>
#include <cstring>

int memcpy_s(void *dest, size_t destMax, const void *src, size_t count)
{
	memcpy(dest, src, count);
	return 0;
}