#ifndef INFINIBAND_VERBS_DIF_H
#define INFINIBAND_VERBS_DIF_H

#include <stdint.h>

enum ibv_sector_size {
	IBV_SECTOR_512B = 0,
	IBV_SECTOR_4KB,
	IBV_SECTOR_NUM
};

enum ibv_sgl_mode {
	IBV_SGL_SINGLE = 0,
	IBV_SGL_DOUBLE,
	IBV_SGL_MODE_NUM
};

enum ibv_dif_type {
	IBV_DIF_TYPE_T10 = 1,
	IBV_DIF_TYPE_OTHER,
};

enum ibv_dif_verify {
    IBV_DIF_NO_VERIFY = 0,
	IBV_DIF_VERIFY = 1,
};

enum ibv_dif_escape {
    IBV_DIF_NO_ESCAPE = 0,
	IBV_DIF_ESCAPE = 1,
};

enum ibv_dif_ctrl {
	IBV_DIF_INSERT = 0,
	IBV_DIF_STRIP,
	IBV_DIF_FORWARD,
	IBV_DIF_REPLACE,
};

enum ibv_ref_tag_mode {
	IBV_REF_TAG_FIXED = 0,
    IBV_REF_TAG_BOTH_INC,
	IBV_REF_TAG_RECV_INC,
	IBV_REF_TAG_SEND_INC,
};

enum ibv_grd_algorithm {
	IBV_GRD_AGM_CRC16 = 0,
	IBV_GRD_AGM_IP_CSUM
};

enum ibv_dif_enable {
    IBV_DIF_DISABLE = 0,
    IBV_DIF_ENABLE = 1
};

struct ibv_dif_domain {
	uint16_t app_tag;
	uint16_t app_tag_mask;
	
	uint32_t ref_tag; // start lba
	
	uint8_t ref_tag_mode; // 自增还是fixed 4种
	uint8_t ref_tag_ctrl; // 插入、删除、forward、replace
	uint8_t ref_tag_verify; // 是否校验
	uint8_t ref_tag_esc; // 是否跳过
	
	uint8_t app_tag_ctrl; // 插入、删除、forward、replace
	uint8_t app_tag_verify; // 是否校验
	uint8_t app_tag_esc; // 是否跳过
	
	uint8_t grd_ctrl;    // 插入、删除、forward、replace
	uint8_t grd_verify;   // 是否校验
	uint8_t grd_agm;      // CRC还是IP CheckSUM
	uint8_t grd_agm_seed; // CRC初始值，1822要求固定值
	
	uint8_t dif_type;  // T10 other
	
	uint8_t sector_size; // 512B 4K 
	uint8_t sgl_mode;  // SINGLE DOUBLE，DOUBLE不支持
};

struct ibv_dif_info {
	struct ibv_dif_domain mem;
	struct ibv_dif_domain wire;
};

#endif
