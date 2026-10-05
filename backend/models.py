import os
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# 软岩 / 硬岩两套合格闭区间（毫米）。判定按绝对值落入 [lower, upper]。
GRADE_KEYS = ("soft", "hard")
GRADE_LABELS = {"soft": "软岩", "hard": "硬岩"}
DEFAULT_LIMITS = {
    "soft": {"lower_mm": 0.0, "upper_mm": 3.0},
    "hard": {"lower_mm": 0.0, "upper_mm": 1.5},
}


class Base(DeclarativeBase):
    pass


class RockLimit(Base):
    """围岩分带档位：每个等级一行当前闭区间。"""

    __tablename__ = "rock_limits"

    grade: Mapped[str] = mapped_column(String, primary_key=True)
    lower_mm: Mapped[float] = mapped_column(Float, nullable=False)
    upper_mm: Mapped[float] = mapped_column(Float, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LimitHistory(Base):
    """改档履历：每次改上下限追加一行，只增不改。"""

    __tablename__ = "limit_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade: Mapped[str] = mapped_column(String, nullable=False, index=True)
    old_lower_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    old_upper_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_lower_mm: Mapped[float] = mapped_column(Float, nullable=False)
    new_upper_mm: Mapped[float] = mapped_column(Float, nullable=False)
    changed_by: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str | None] = mapped_column(String, nullable=True)
    # 认领那一刻抄进单据的档位快照；此后改档不影响已认领单据
    snap_lower_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    snap_upper_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def migrate(engine_) -> None:
    """旧库（A02 基线，单门槛）补列，幂等。"""
    cols = {c["name"] for c in inspect(engine_).get_columns("convergence_logs")}
    add = {
        "grade": "ADD COLUMN grade VARCHAR",
        "snap_lower_mm": "ADD COLUMN snap_lower_mm DOUBLE PRECISION",
        "snap_upper_mm": "ADD COLUMN snap_upper_mm DOUBLE PRECISION",
    }
    with engine_.begin() as conn:
        for col, ddl in add.items():
            if col not in cols:
                conn.execute(text(f"ALTER TABLE convergence_logs {ddl}"))


def seed_limits(db) -> None:
    now = datetime.now(timezone.utc)
    for grade in GRADE_KEYS:
        existing = db.get(RockLimit, grade)
        if existing is None:
            d = DEFAULT_LIMITS[grade]
            db.add(
                RockLimit(
                    grade=grade,
                    lower_mm=d["lower_mm"],
                    upper_mm=d["upper_mm"],
                    updated_by="system",
                    updated_at=now,
                )
            )
    db.commit()


def limit_dict(row: RockLimit) -> dict:
    return {
        "grade": row.grade,
        "grade_label": GRADE_LABELS.get(row.grade, row.grade),
        "lower_mm": row.lower_mm,
        "upper_mm": row.upper_mm,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def history_dict(row: LimitHistory) -> dict:
    return {
        "id": row.id,
        "grade": row.grade,
        "grade_label": GRADE_LABELS.get(row.grade, row.grade),
        "old_lower_mm": row.old_lower_mm,
        "old_upper_mm": row.old_upper_mm,
        "new_lower_mm": row.new_lower_mm,
        "new_upper_mm": row.new_upper_mm,
        "changed_by": row.changed_by,
        "changed_at": row.changed_at.isoformat() if row.changed_at else None,
    }


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "grade": row.grade,
        "grade_label": GRADE_LABELS.get(row.grade, row.grade) if row.grade else None,
        "snap_lower_mm": row.snap_lower_mm,
        "snap_upper_mm": row.snap_upper_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
