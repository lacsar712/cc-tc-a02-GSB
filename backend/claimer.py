"""进程内认领：同一 Flask 进程后台线程抢 pending，不另起容器。

判定吃单据认领那一刻的闭区间：领走时把该围岩等级当前上下限抄进行内
快照（snap_lower_mm / snap_upper_mm），之后测量员再改档，已领走的
单据仍按快照判定，不翻案。
"""
import threading
import time
from datetime import datetime, timezone

from models import ConvergenceLog, RockLimit, SessionLocal
from rules import judge

_stop = threading.Event()


def claim_once() -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(ConvergenceLog)
            .filter(ConvergenceLog.status == "pending")
            .order_by(ConvergenceLog.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            db.commit()
            return False
        # 新单强制点选等级；档位行随服务启动播种，正常必能取到。
        # 兜底：历史脏单缺等级或档位缺失时判“退回”，避免堵住后续队列。
        limit = db.get(RockLimit, row.grade) if row.grade else None
        if limit is None:
            row.status = "done"
            row.verdict = "退回"
            row.reason = "缺少合法围岩等级，未抄录闭区间快照，不予判定"
            row.processed_at = datetime.now(timezone.utc)
            db.commit()
            return True
        lower = float(limit.lower_mm)
        upper = float(limit.upper_mm)
        verdict, reason = judge(float(row.delta_mm), lower, upper, row.grade)
        row.snap_lower_mm = lower
        row.snap_upper_mm = upper
        row.status = "done"
        row.verdict = verdict
        row.reason = reason
        row.processed_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def loop():
    while not _stop.is_set():
        try:
            if claim_once():
                time.sleep(0.4)
            else:
                time.sleep(1.0)
        except Exception as exc:
            print(f"claimer error: {exc}", flush=True)
            time.sleep(1.0)


def start():
    t = threading.Thread(target=loop, name="convergence-claimer", daemon=True)
    t.start()
