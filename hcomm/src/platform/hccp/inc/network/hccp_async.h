/**
 * @file hccp_async.h
 * @brief This module provides APIs async operations for HCCL
 * @version Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * @date 2025-02-17
 */
#ifndef HCCP_ASYNC_H
#define HCCP_ASYNC_H

#include "hccp_common.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @ingroup libcommon
 * @brief check if async request is done, will free req_handle if it done
 * @param req_handle [IN] async request handle
 * @param req_result [OUT] async request return value
 * @retval #zero Success
 * @retval #OTHERS_EAGAIN try again
 * @retval #non-zero Failure(exclude OTHERS_EAGAIN)
*/
HCCP_ATTRI_VISI_DEF int RaGetAsyncReqResult(void *reqHandle, int *reqResult);

/**
 * @ingroup libsocket
 * @brief Client sockets batch connect to server sockets(async)
 * @param conn [IN] client sockets array
 * @param num [IN] num of conn
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @retval #zero Success
 * @retval #non-zero Failure
*/
HCCP_ATTRI_VISI_DEF int RaSocketBatchConnectAsync(struct SocketConnectInfoT conn[], unsigned int num,
    void **reqHandle);

/**
 * @ingroup libsocket
 * @brief Sockets batch listen
 * @param conn [IN] server info array
 * @param num [IN] num of conn
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @see ra_socket_listen_stop_async
 * @retval #zero Success
 * @retval #non-zero Failure
*/
HCCP_ATTRI_VISI_DEF int RaSocketListenStartAsync(struct SocketListenInfoT conn[], unsigned int num,
    void **reqHandle);

/**
 * @ingroup libsocket
 * @brief Sockets batch stop
 * @param conn [IN sockets info array
 * @param num [IN] num of conn
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @see ra_socket_listen_start_async
 * @retval #zero Success
 * @retval #non-zero Failure
*/
HCCP_ATTRI_VISI_DEF int RaSocketListenStopAsync(struct SocketListenInfoT conn[], unsigned int num,
    void **reqHandle);

/**
 * @ingroup libsocket
 * @brief Sockets batch close
 * @param conn [IN] sockets array, use disuse_linger of the fist conn as the common attr for all
 * @param num [IN] num of conn
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @retval #zero Success
 * @retval #non-zero Failure
*/
HCCP_ATTRI_VISI_DEF int RaSocketBatchCloseAsync(struct SocketCloseInfoT conn[], unsigned int num,
    void **reqHandle);

/**
 * @ingroup libsocket
 * @brief Send data async by fd handle
 * @param fd_handle [IN] fd handle
 * @param data [IN] send storage buff
 * @param size [IN] size of data you want to send unit(Byte)
 * @param sent_size [IN/OUT] number of sent bytes
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @see ra_socket_recv_async
 * @retval #zero Success
 * @retval #non-zero Failure
*/
HCCP_ATTRI_VISI_DEF int RaSocketSendAsync(const void *fdHandle, const void *data, unsigned long long size,
    unsigned long long *sentSize, void **reqHandle);

/**
 * @ingroup libsocket
 * @brief Receive data async by fd handle
 * @param fd_handle [IN] fd handle
 * @param data [IN/OUT] receive storage buff
 * @param size [IN] size of data you want to receive unit(Byte)
 * @param received_size [IN/OUT] number of received bytes
 * @param req_handle [OUT] async request handle
 * @see ra_get_async_req_result
 * @see ra_socket_send_async
 * @retval #zero Success
 * @retval #SOCK_EAGAIN Success(no data received by socket)
 * @retval #non-zero Failure(exclude SOCK_EAGAIN)
*/
HCCP_ATTRI_VISI_DEF int RaSocketRecvAsync(const void *fdHandle, void *data, unsigned long long size,
    unsigned long long *receivedSize, void **reqHandle);
#ifdef __cplusplus
}
#endif

#endif // HCCP_ASYNC_H
