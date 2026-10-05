"""进程内认领：同一 Flask 进程后台线程抢 pending，不另起容器。

认领那一刻把当前档位闭区间抄进单据快照（lower_limit_mm/upper_limit_mm），
判定只吃快照；事后阈值再怎么改，已领走的单据结论不变。
"""
import threading
import time
from datetime import datetime, timezone

from models import ConvergenceLog, RockZone, SessionLocal
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

        # 认领先锁档位行，保证抄进快照的就是这一刻生效的闭区间
        zone = (
            db.query(RockZone)
            .filter(RockZone.grade == row.rock_grade)
            .with_for_update()
            .first()
        )
        if zone is None:
            # 档位被删/字典对不上：不动它，等口径修复后再领，绝不按全线门槛乱判
            db.rollback()
            return False

        lower, upper = float(zone.lower_limit_mm), float(zone.upper_limit_mm)
        verdict, reason = judge(float(row.delta_mm), lower, upper)
        row.lower_limit_mm = lower
        row.upper_limit_mm = upper
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
