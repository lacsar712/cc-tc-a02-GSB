"""收敛判定：软岩、硬岩各用一套合格闭区间，不能全线一个门槛。

闭区间语义：lower_limit <= delta <= upper_limit 为合格，端点算合格。
档位（围岩等级）与上下限口径必须全系统同一套字典（见 GRADES），
点选档位与入库档位对不上即整份退回。
"""

# 档位字典：key 是入库口径，label 是页面点选显示，二者必须一一对应
GRADES = {
    "soft": {"label": "软岩", "default_lower": -3.0, "default_upper": 3.0},
    "hard": {"label": "硬岩", "default_lower": -2.0, "default_upper": 2.0},
}

GRADE_KEYS = tuple(GRADES.keys())


def is_valid_grade(grade: str) -> bool:
    return grade in GRADES


def grade_label(grade: str) -> str:
    return GRADES[grade]["label"]


def judge(delta_mm: float, lower_limit: float, upper_limit: float) -> tuple[str, str]:
    """按给定闭区间判定。调用方一律传入认领那一刻抄进单据快照的上下限。"""
    if lower_limit <= delta_mm <= upper_limit:
        return (
            "合格",
            f"收敛 {delta_mm} mm 在闭区间 [{lower_limit}, {upper_limit}] mm 内",
        )
    return (
        "超限",
        f"收敛 {delta_mm} mm 超出闭区间 [{lower_limit}, {upper_limit}] mm",
    )
