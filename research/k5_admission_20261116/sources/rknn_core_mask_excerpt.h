typedef enum _rknn_core_mask {
    RKNN_NPU_CORE_AUTO = 0,                                       /* default, run on NPU core randomly. */
    RKNN_NPU_CORE_0 = 1,                                          /* run on NPU core 0. */
    RKNN_NPU_CORE_1 = 2,                                          /* run on NPU core 1. */
    RKNN_NPU_CORE_2 = 4,                                          /* run on NPU core 2. */
    RKNN_NPU_CORE_0_1 = RKNN_NPU_CORE_0 | RKNN_NPU_CORE_1,        /* run on NPU core 0 and core 1. */
    RKNN_NPU_CORE_0_1_2 = RKNN_NPU_CORE_0_1 | RKNN_NPU_CORE_2,    /* run on NPU core 0 and core 1 and core 2. */
    RKNN_NPU_CORE_ALL = 0xffff,                                   /* auto choice, run on NPU cores depending on platform */

    RKNN_NPU_CORE_UNDEFINED,
} rknn_core_mask;

/*  rknn_set_core_mask

    set the core mask for the model.(only supported on multi-core NPU platform)

    RKNN_NPU_CORE_AUTO: auto mode, default value
    RKNN_NPU_CORE_0: core 0 mode
    RKNN_NPU_CORE_1: core 1 mode
    RKNN_NPU_CORE_2: core 2 mode
    RKNN_NPU_CORE_0_1: combine core 0/1 mode
    RKNN_NPU_CORE_0_1_2: combine core 0/1/2 mode
    RKNN_NPU_CORE_ALL: auto mode, select multiple npu cores to run depending on platform 


    input:
        rknn_context context        the handle of context.
        rknn_core_mask core_mask    the core mask.
    return:
        int                         error code.
*/
int rknn_set_core_mask(rknn_context context, rknn_core_mask core_mask);
