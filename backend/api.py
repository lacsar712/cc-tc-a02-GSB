import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    GRADE_KEYS,
    Base,
    ConvergenceLog,
    LimitHistory,
    RockLimit,
    SessionLocal,
    engine,
    history_dict,
    limit_dict,
    migrate,
    row_dict,
    seed_limits,
)
from rules import judge

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    migrate(engine)
    db = SessionLocal()
    try:
        seed_limits(db)
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        # 种子单据挂软岩档，闭区间 [0, 3.0]，认领快照随结论一并写入
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            verdict, reason = judge(delta, 0.0, 3.0, "soft")
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    delta_mm=delta,
                    grade="soft",
                    snap_lower_mm=0.0,
                    snap_upper_mm=3.0,
                    status="done",
                    verdict=verdict,
                    reason=reason,
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


def require_writer(action: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"detail": "未登录"}), 401
            if user["role"] != "writer":
                # 巡检员只能翻表和履历：不能改档，也不能报数
                return jsonify({"detail": f"巡检员只读，{action}仅测量员可操作"}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def _as_float(value, field: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是数字")


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


@app.get("/api/limits")
@require_login
def list_limits():
    """围岩分带当前档位：软岩、硬岩各一行闭区间。"""
    db = SessionLocal()
    try:
        rows = {r.grade: r for r in db.query(RockLimit).all()}
        return jsonify([limit_dict(rows[g]) for g in GRADE_KEYS if g in rows])
    finally:
        db.close()


@app.put("/api/limits")
@require_writer("改档")
def update_limit():
    """测量员改某一档的上下限，追加改档履历。区间必须合法。"""
    body = request.get_json(silent=True) or {}
    grade = body.get("grade")
    if grade not in GRADE_KEYS:
        return jsonify({"detail": "围岩等级必须是 soft（软岩）或 hard（硬岩）"}), 400
    try:
        lower = _as_float(body.get("lower_mm"), "下限")
        upper = _as_float(body.get("upper_mm"), "上限")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    if lower < 0:
        return jsonify({"detail": "下限不能为负（按收敛绝对值判定）"}), 400
    if upper < lower:
        return jsonify({"detail": "上限不能小于下限，需构成合格闭区间"}), 400

    db = SessionLocal()
    try:
        row = db.get(RockLimit, grade)
        if row is None:
            return jsonify({"detail": "档位不存在"}), 404
        old_lower, old_upper = float(row.lower_mm), float(row.upper_mm)
        now = datetime.now(timezone.utc)
        db.add(
            LimitHistory(
                grade=grade,
                old_lower_mm=old_lower,
                old_upper_mm=old_upper,
                new_lower_mm=lower,
                new_upper_mm=upper,
                changed_by=g.user["username"],
                changed_at=now,
            )
        )
        row.lower_mm = lower
        row.upper_mm = upper
        row.updated_by = g.user["username"]
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return jsonify(limit_dict(row))
    finally:
        db.close()


@app.get("/api/limits/history")
@require_login
def list_limit_history():
    """改档履历，登录即可翻（巡检员只读也可查）。"""
    grade = request.args.get("grade")
    db = SessionLocal()
    try:
        q = db.query(LimitHistory)
        if grade in GRADE_KEYS:
            q = q.filter(LimitHistory.grade == grade)
        rows = q.order_by(LimitHistory.id.desc()).limit(200).all()
        return jsonify([history_dict(r) for r in rows])
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
@require_writer("报数")
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    # 新单必须点选围岩等级；漏选整份退回，不允许落库待判
    grade = body.get("grade")
    if grade not in GRADE_KEYS:
        return jsonify({"detail": "必须点选围岩等级（软岩/硬岩），漏选整份退回"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            grade=grade,
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
