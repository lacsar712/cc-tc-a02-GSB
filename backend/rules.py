"""收敛判定：按围岩等级各自的合格闭区间 [lower_mm, upper_mm] 判定绝对值。

软岩、硬岩两套区间，不再全线共用一个门槛。判定一律吃单据认领那一刻
抄进快照的上下限（见 claimer.py），本模块只做纯函数判定。
"""

from models import GRADE_LABELS


def judge(delta_mm: float, lower_mm: float, upper_mm: float, grade: str) -> tuple[str, str]:
    label = GRADE_LABELS.get(grade, grade)
    mag = abs(delta_mm)
    # 闭区间：上下限本身算合格（<= 而非 <）
    if lower_mm <= mag <= upper_mm:
        return (
            "合格",
            f"{label}：收敛 {delta_mm} mm，绝对值 {mag:g} mm 落在闭区间 "
            f"[{lower_mm:g}, {upper_mm:g}] mm 内",
        )
    return (
        "超限",
        f"{label}：收敛 {delta_mm} mm，绝对值 {mag:g} mm 超出闭区间 "
        f"[{lower_mm:g}, {upper_mm:g}] mm",
    )
