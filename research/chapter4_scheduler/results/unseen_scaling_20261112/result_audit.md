# 预实验结果只读核查

已检查 8/8 个返回槽；169 项条件，发现 0 项不一致。未导入科学模块、未执行新调度或热评价。

核查范围：输入身份、独立300秒根、journal与非缓存评价逐项对应、完整/未决计数、预算内SAFE、全窗口覆盖、同条件初始化候选序列与快照、同核post身份及能量区间相交。

```json
{
  "failed_case_construction": [
    {
      "opp_rank": null,
      "status": "CONSTRUCTION_UNRESOLVED",
      "reason": "NO_LEGAL_EFT_INSERTION",
      "thermal_status": "NOT_EVALUATED",
      "failed_shared_stage": "S1.s0002"
    },
    {
      "opp_rank": 0,
      "status": "CONSTRUCTION_UNRESOLVED",
      "reason": "NO_LEGAL_EFT_INSERTION",
      "thermal_status": "NOT_EVALUATED",
      "failed_shared_stage": "S1.s0002"
    },
    {
      "opp_rank": 1,
      "status": "CONSTRUCTION_UNRESOLVED",
      "reason": "NO_LEGAL_EFT_INSERTION",
      "thermal_status": "NOT_EVALUATED",
      "failed_shared_stage": "S1.s0002"
    },
    {
      "opp_rank": 2,
      "status": "CONSTRUCTION_UNRESOLVED",
      "reason": "NO_LEGAL_EFT_INSERTION",
      "thermal_status": "NOT_EVALUATED",
      "failed_shared_stage": "S1.s0003"
    }
  ],
  "reference_state": "SCHEDULE_VALID_THERMAL_UNCHECKED",
  "completed_slots": 8,
  "planned_slots": 8,
  "checks": 169,
  "errors": [],
  "rows": [
    {
      "slot": "01_U01__n6_HEFT",
      "terminal": "SEARCH_COMPLETED",
      "E": 0.5736450201721928,
      "method_s": 32.59399999999914,
      "init_s": 32.20299999999952,
      "search_s": 0.0,
      "attempts": 28,
      "complete": 28,
      "safe": 28,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "02_U01__n6_ON",
      "terminal": "SEARCH_COMPLETED",
      "E": 0.5031810534014154,
      "method_s": 34.64100000000144,
      "init_s": 27.281999999999243,
      "search_s": 7.016000000001441,
      "attempts": 30,
      "complete": 30,
      "safe": 30,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "03_U01__n12_ON",
      "terminal": "SEARCH_COMPLETED",
      "E": 1.0599290870777942,
      "method_s": 167.90600000000086,
      "init_s": 156.85900000000038,
      "search_s": 10.70299999999952,
      "attempts": 87,
      "complete": 87,
      "safe": 87,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "04_U01__n12_HEFT",
      "terminal": "SEARCH_COMPLETED",
      "E": 1.2102759302673047,
      "method_s": 206.29699999999866,
      "init_s": 205.92200000000048,
      "search_s": 0.0,
      "attempts": 83,
      "complete": 83,
      "safe": 83,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "05_U02__n6_ON",
      "terminal": "SEARCH_COMPLETED",
      "E": 1.201505301574721,
      "method_s": 54.73400000000038,
      "init_s": 29.98400000000038,
      "search_s": 24.375,
      "attempts": 38,
      "complete": 38,
      "safe": 38,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "06_U02__n6_HEFT",
      "terminal": "SEARCH_COMPLETED",
      "E": 1.201603273044706,
      "method_s": 29.17200000000048,
      "init_s": 28.781999999999243,
      "search_s": 0.0,
      "attempts": 24,
      "complete": 24,
      "safe": 24,
      "unresolved": 0,
      "cache": 0,
      "post": true
    },
    {
      "slot": "07_U02__n12_HEFT",
      "terminal": "NORMAL_NO_SAFE",
      "E": null,
      "method_s": 0.4220000000004802,
      "init_s": 0.04700000000048021,
      "search_s": 0.0,
      "attempts": 0,
      "complete": 0,
      "safe": 0,
      "unresolved": 0,
      "cache": 0,
      "post": false
    },
    {
      "slot": "08_U02__n12_ON",
      "terminal": "NORMAL_NO_SAFE",
      "E": null,
      "method_s": 0.3899999999994179,
      "init_s": 0.030999999999039574,
      "search_s": 0.0,
      "attempts": 0,
      "complete": 0,
      "safe": 0,
      "unresolved": 0,
      "cache": 0,
      "post": false
    }
  ],
  "pairs": [
    {
      "case": "U01__n6",
      "same_complete_init": true,
      "same_init_energy_interval": true,
      "same_init_physical_sequence": true,
      "init_evaluations": [
        28,
        28
      ]
    },
    {
      "case": "U01__n12",
      "same_complete_init": true,
      "same_init_energy_interval": true,
      "same_init_physical_sequence": true,
      "init_evaluations": [
        83,
        83
      ]
    },
    {
      "case": "U02__n6",
      "same_complete_init": true,
      "same_init_energy_interval": true,
      "same_init_physical_sequence": true,
      "init_evaluations": [
        24,
        24
      ]
    },
    {
      "case": "U02__n12",
      "same_complete_init": false,
      "same_init_energy_interval": true,
      "same_init_physical_sequence": true,
      "init_evaluations": [
        0,
        0
      ]
    }
  ]
}
```

说明：同核post不是独立数值实现；未决/部分返回不计完整评价，缓存命中不计新物理评价。U02/12两方法均为原HEFT有限构造失败，四次尝试（首个EFT+三个频档rank后备）内容一致；0完整候选/0热评价/0热违例/未到预算，ON未进入改进。不是全局不可行证明、超温或超时。其全H参考只有时间结构合法回执且未热评，不能视为安全可行证明。

全部三组成功配对的独立初始化候选序列、最终初始化快照与精确能量区间一致。U01/12两次同样83次初始化评价耗时不同（ON 156.859s，HEFT 205.922s），说明单次墙钟存在时变开销；不能把ON此组总时更短解释为更少初始化工作或稳定加速。
