import math
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    Base,
    ConvergenceLog,
    RockZone,
    SessionLocal,
    ZoneChange,
    change_dict,
    ensure_columns,
    engine,
    row_dict,
    zone_dict,
)
from rules import GRADES, is_valid_grade, judge

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    ensure_columns()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # 档位：软岩、硬岩两套闭区间
        if db.query(RockZone).count() == 0:
            for key, spec in GRADES.items():
                db.add(
                    RockZone(
                        grade=key,
                        label=spec["label"],
                        lower_limit_mm=spec["default_lower"],
                        upper_limit_mm=spec["default_upper"],
                        updated_by="system",
                        updated_at=now,
                    )
                )
            db.flush()
        # 种子单据：直接按当时档位快照落结论
        if db.query(ConvergenceLog).count() > 0:
            db.commit()
            return
        for chainage, delta, grade, expect in (
            ("K12+180", 1.2, "soft", "合格"),
            ("K18+040", 5.6, "hard", "超限"),
        ):
            zone = db.query(RockZone).filter(RockZone.grade == grade).one()
            verdict, reason = judge(delta, zone.lower_limit_mm, zone.upper_limit_mm)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    delta_mm=delta,
                    rock_grade=grade,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    lower_limit_mm=zone.lower_limit_mm,
                    upper_limit_mm=zone.upper_limit_mm,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "巡检员只能翻表和履历，不能改档也不能报数"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def parse_limit(body: dict, key: str) -> tuple[float | None, str | None]:
    raw = body.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "上下限必须填写"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "上下限必须是数字"
    if not math.isfinite(value):
        return None, "上下限必须是有限数字"
    return value, None


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/zones")
@require_login
def list_zones():
    """围岩分带专页上块：当前档位（软岩/硬岩两套闭区间）。"""
    db = SessionLocal()
    try:
        rows = db.query(RockZone).order_by(RockZone.grade).all()
        return jsonify([zone_dict(r) for r in rows])
    finally:
        db.close()


@app.put("/api/zones/<grade>")
@require_writer
def update_zone(grade: str):
    """改档：仅测量员。每次改动写一条改档履历。"""
    if not is_valid_grade(grade):
        return jsonify({"detail": "档位口径不存在，可选：" + "、".join(GRADES)}), 400
    body = request.get_json(silent=True) or {}
    lower, err_low = parse_limit(body, "lower_limit_mm")
    upper, err_high = parse_limit(body, "upper_limit_mm")
    if err_low or err_high:
        return jsonify({"detail": err_low or err_high}), 400
    if lower > upper:
        return jsonify({"detail": "下限不能大于上限（闭区间要求 lower <= upper）"}), 400

    db = SessionLocal()
    try:
        zone = db.query(RockZone).filter(RockZone.grade == grade).with_for_update().first()
        if zone is None:
            return jsonify({"detail": "档位尚未初始化"}), 409
        now = datetime.now(timezone.utc)
        db.add(
            ZoneChange(
                grade=grade,
                old_lower_mm=zone.lower_limit_mm,
                old_upper_mm=zone.upper_limit_mm,
                new_lower_mm=lower,
                new_upper_mm=upper,
                changed_by=g.user["username"],
                changed_at=now,
            )
        )
        zone.lower_limit_mm = lower
        zone.upper_limit_mm = upper
        zone.updated_by = g.user["username"]
        zone.updated_at = now
        db.commit()
        return jsonify(zone_dict(zone))
    finally:
        db.close()


@app.get("/api/zones/history")
@require_login
def zone_history():
    """围岩分带专页中块：改档履历。巡检员可翻，不可改。"""
    grade = request.args.get("grade")
    db = SessionLocal()
    try:
        q = db.query(ZoneChange)
        if grade:
            if not is_valid_grade(grade):
                return jsonify({"detail": "档位口径不存在"}), 400
            q = q.filter(ZoneChange.grade == grade)
        rows = q.order_by(ZoneChange.id.desc()).limit(200).all()
        return jsonify([change_dict(r) for r in rows])
    finally:
        db.close()


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400

    # 新单必须点选围岩等级；漏选或口径对不上，整份退回（不落库）
    grade = body.get("rock_grade")
    if grade is None or (isinstance(grade, str) and not grade.strip()):
        return jsonify({"detail": "新单必须点选围岩等级，漏选整份退回"}), 400
    if not isinstance(grade, str) or not is_valid_grade(grade):
        return (
            jsonify(
                {
                    "detail": (
                        "围岩等级口径必须是 "
                        + "、".join(f"{k}（{v['label']}）" for k, v in GRADES.items())
                        + "，点选与入库同一口径，对不上整份退回"
                    )
                }
            ),
            400,
        )

    raw_delta = body.get("delta_mm")
    if raw_delta is None or (isinstance(raw_delta, str) and not raw_delta.strip()):
        return jsonify({"detail": "收敛值不能为空"}), 400
    try:
        delta_mm = float(raw_delta)
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    if not math.isfinite(delta_mm):
        return jsonify({"detail": "收敛值必须是有限数字"}), 400

    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            rock_grade=grade,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()
