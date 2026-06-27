set(src_list
    op_unfold_cache_entry.cc
    op_unfold_cache.cc
    op_unfold_key.cc
)

target_sources(hccl_plf PRIVATE
    ${src_list}
)

target_sources(hccd PRIVATE
    ${src_list}
)

target_sources(ccl_kernel_plf PRIVATE
    ${src_list}
)

target_sources(ccl_kernel_plf_a  PRIVATE
    ${src_list}
)