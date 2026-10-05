import os
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class RockZone(Base):
    """围岩分带当前档位：软岩/硬岩各一套合格闭区间上下限。"""

    __tablename__ = "rock_zones"

    grade: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    lower_limit_mm: Mapped[float] = mapped_column(Float, nullable=False)
    upper_limit_mm: Mapped[float] = mapped_column(Float, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ZoneChange(Base):
    """改档履历：上下限每改一次留一条，巡检员可翻履历但不能改。"""

    __tablename__ = "zone_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade: Mapped[str] = mapped_column(String, nullable=False, index=True)
    old_lower_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    old_upper_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_lower_mm: Mapped[float] = mapped_column(Float, nullable=False)
    new_upper_mm: Mapped[float] = mapped_column(Float, nullable=False)
    changed_by: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    # 新单必须点选围岩等级，口径必须与 GRADES 字典完全一致
    rock_grade: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # 认领那一刻抄进快照的上下限；已领走的单据永远按快照判定，不随后续改档变
    lower_limit_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_limit_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 旧库（单门槛时代的 convergence_logs）幂等补列，保住已有数据
_ADDED_COLUMNS = {
    "rock_grade": "VARCHAR",
    "lower_limit_mm": "FLOAT",
    "upper_limit_mm": "FLOAT",
}


def ensure_columns():
    inspector = inspect(engine)
    if "convergence_logs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("convergence_logs")}
    with engine.begin() as conn:
        for name, col_type in _ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(
                    text(f"ALTER TABLE convergence_logs ADD COLUMN {name} {col_type}")
                )
        # 单门槛时代的旧行：旧门槛 ±3.0 与软岩初始闭区间同口径，等级回填到软岩
        conn.execute(
            text(
                "UPDATE convergence_logs SET rock_grade = 'soft' "
                "WHERE rock_grade IS NULL"
            )
        )
        # 仅给旧时代已判完的行补快照；pending 行的快照必须留到认领那一刻再抄
        conn.execute(
            text(
                "UPDATE convergence_logs SET lower_limit_mm = -3.0, upper_limit_mm = 3.0 "
                "WHERE lower_limit_mm IS NULL AND upper_limit_mm IS NULL AND status = 'done'"
            )
        )


def zone_dict(row: RockZone) -> dict:
    return {
        "grade": row.grade,
        "label": row.label,
        "lower_limit_mm": row.lower_limit_mm,
        "upper_limit_mm": row.upper_limit_mm,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def change_dict(row: ZoneChange) -> dict:
    return {
        "id": row.id,
        "grade": row.grade,
        "old_lower_mm": row.old_lower_mm,
        "old_upper_mm": row.old_upper_mm,
        "new_lower_mm": row.new_lower_mm,
        "new_upper_mm": row.new_upper_mm,
        "changed_by": row.changed_by,
        "changed_at": row.changed_at.isoformat() if row.changed_at else None,
    }


def row_dict(row: ConvergenceLog) -> dict:
    from rules import GRADES

    grade = row.rock_grade
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "rock_grade": grade,
        "rock_grade_label": GRADES.get(grade, {}).get("label", grade),
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "lower_limit_mm": row.lower_limit_mm,
        "upper_limit_mm": row.upper_limit_mm,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
