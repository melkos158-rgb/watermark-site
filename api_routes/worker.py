import datetime
import json
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from models import db

# ===================== МОДЕЛЬ AI-JOB =====================

class AIJob(db.Model):
    """
    Черга AI-задач (Printability, AI-превʼю, аналіз STL і т.д.).

    Ідея:
      • коли користувач запускає AI-дію — ми створюємо AIJob зі status="done" або
        з status="queued"/"running", якщо хочеш робити асинхронно;
      • після завершення обробки оновлюємо статус, result_json, finished_at, latency_ms;
      • цей запис використовуємо для аналітики (dashboard_ai_tools.js).
    """
    __tablename__ = "ai_jobs"

    id = db.Column(db.Integer, primary_key=True)

    # Користувач, що запустив інструмент (може бути None, якщо гість)
    user_id = db.Column(db.Integer, index=True, nullable=True)

    # Ключ інструмента (printability, stl_compare, ai_tags, ...)
    tool_key = db.Column(db.String(64), nullable=False, index=True)
    tool_name = db.Column(db.String(255), nullable=True)
    tool_category = db.Column(db.String(32), nullable=True)  # "stl", "image", "text", ...

    # Статус: queued / running / done / error
    status = db.Column(db.String(16), nullable=False, default="done", index=True)

    # Короткий опис інпуту (для таблички)
    input_brief = db.Column(db.String(255), nullable=True)

    # Повний payload у JSON (вхідні параметри інструмента)
    payload_json = db.Column(db.Text, nullable=True)
    # Повний результат у JSON
    result_json = db.Column(db.Text, nullable=True)

    # Помилка, якщо status="error"
    error_msg = db.Column(db.Text, nullable=True)

    # Таймінги
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow, index=True
    )
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    # Обчислена тривалість (мс)
    latency_ms = db.Column(db.Integer, nullable=True)

    # Скільки "кредитів" / PXP / токенів витрачено (як захочеш використовувати)
    credits_spent = db.Column(db.Integer, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Повний словник (для внутрішнього використання/адмінки)."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tool_key": self.tool_key,
            "tool_name": self.tool_name,
            "tool_category": self.tool_category,
            "status": self.status,
            "input_brief": self.input_brief,
            "payload": _safe_json_loads(self.payload_json),
            "result": _safe_json_loads(self.result_json),
            "error_msg": self.error_msg,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "latency_ms": self.latency_ms,
            "credits_spent": self.credits_spent,
        }

    def to_brief_dict(self) -> Dict[str, Any]:
        """Скорочений формат для /api/ai/jobs_recent."""
        return {
            "id": self.id,
            "tool_key": self.tool_key,
            "tool_name": self.tool_name,
            "status": self.status,
            "input_brief": self.input_brief,
            "created_at": _iso(self.created_at),
            "finished_at": _iso(self.finished_at),
            "duration_ms": self.latency_ms,
            "error_msg": self.error_msg,
        }


# ===================== УТИЛІТИ =====================

def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _safe_json_dumps(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None


def _safe_json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _calc_latency_ms(started_at: Optional[datetime.datetime],
                     finished_at: Optional[datetime.datetime]) -> Optional[int]:
    if not started_at or not finished_at:
        return None
    delta = finished_at - started_at
    return int(delta.total_seconds() * 1000)


def _aggregate_tools_stats(jobs: List[AIJob]) -> List[Dict[str, Any]]:
    """
    Агрегуємо stats по інструментах для /api/ai/tools_stats.

    Повертає список:
      [
        {
          "key": "...",
          "name": "...",
          "category": "...",
          "used_count": N,
          "last_used_at": "...",
          "avg_latency_ms": ...,
          "error_rate": 0.0..1.0,
          "credits_spent": ...,
        },
        ...
      ]
    """
    by_key: Dict[str, Dict[str, Any]] = {}

    for j in jobs:
        key = j.tool_key or "unknown"
        bucket = by_key.get(key)
        if not bucket:
            bucket = {
                "key": key,
                "name": j.tool_name or key,
                "category": j.tool_category or None,
                "used_count": 0,
                "credits_spent": 0,
                "last_used_at": None,
                "_latency_sum": 0,
                "_latency_count": 0,
                "_errors": 0,
            }
            by_key[key] = bucket

        bucket["used_count"] += 1
        if j.credits_spent:
            bucket["credits_spent"] += j.credits_spent

        # last_used_at = max(finished_at or created_at)
        last_dt = j.finished_at or j.created_at
        if last_dt:
            cur_last = bucket["last_used_at"]
            if cur_last is None or last_dt > cur_last:
                bucket["last_used_at"] = last_dt

        # latency
        if j.latency_ms is not None and j.latency_ms >= 0:
            bucket["_latency_sum"] += j.latency_ms
            bucket["_latency_count"] += 1

        # errors
        if (j.status or "").lower() == "error":
            bucket["_errors"] += 1

    # Пост-обробка
    out: List[Dict[str, Any]] = []
    for key, b in by_key.items():
        used = b["used_count"] or 1  # щоб не ділити на 0
        lat_count = b["_latency_count"] or 1
        avg_latency = int(b["_latency_sum"] / lat_count) if b["_latency_sum"] else 0
        error_rate = float(b["_errors"] / used) if used > 0 else 0.0

        out.append({
            "key": key,
            "name": b["name"],
            "category": b["category"],
            "used_count": b["used_count"],
            "last_used_at": _iso(b["last_used_at"]),
            "avg_latency_ms": avg_latency,
            "error_rate": error_rate,
            "credits_spent": b["credits_spent"],
        })

    # Сортуємо за used_count (спадаючий)
    out.sort(key=lambda x: x["used_count"], reverse=True)
    return out


def enqueue_ai_job(
    *,
    user_id: Optional[int],
    tool_key: str,
    tool_name: Optional[str] = None,
    tool_category: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    input_brief: Optional[str] = None,
    credits_spent: Optional[int] = None,
    status: str = "done",
) -> AIJob:
    """
    Хелпер, щоб із будь-якого місця (ai_api, printability, worker-процес) створити запис:

        from worker import enqueue_ai_job

        job = enqueue_ai_job(
            user_id=user.id,
            tool_key="printability",
            tool_name="Printability Check",
            tool_category="stl",
            payload={"item_id": item.id},
            input_brief=f"{item.title} (#{item.id})",
            credits_spent=3,
            status="done",  # або "queued"/"running"
        )

    Якщо хочеш саме "чергу" — можеш ставити status="queued", а worker-процес буде
    змінювати на running/done/error.
    """
    now = datetime.datetime.utcnow()
    job = AIJob(
        user_id=user_id,
        tool_key=(tool_key or "unknown")[:64],
        tool_name=tool_name,
        tool_category=tool_category,
        status=status or "done",
        input_brief=(input_brief or "")[:255],
        payload_json=_safe_json_dumps(payload),
        credits_spent=credits_spent,
        created_at=now,
    )
    db.session.add(job)
    db.session.commit()
    current_app.logger.info(
        "AIJob created id=%s tool_key=%s status=%s", job.id, job.tool_key, job.status
    )
    return job


def mark_job_started(job: AIJob) -> None:
    """Позначити job як running."""
    job.started_at = datetime.datetime.utcnow()
    job.status = "running"
    db.session.commit()


def mark_job_finished(job: AIJob, result: Any, *, credits_spent: Optional[int] = None) -> None:
    """Позначити job як done, з результатом."""
    job.finished_at = datetime.datetime.utcnow()
    job.status = "done"
    job.result_json = _safe_json_dumps(result)
    job.latency_ms = _calc_latency_ms(job.started_at or job.created_at, job.finished_at)
    if credits_spent is not None:
        job.credits_spent = credits_spent
    db.session.commit()


def mark_job_error(job: AIJob, error_msg: str) -> None:
    """Позначити job як error."""
    job.finished_at = datetime.datetime.utcnow()
    job.status = "error"
    job.error_msg = error_msg[:1000]
    job.latency_ms = _calc_latency_ms(job.started_at or job.created_at, job.finished_at)
    db.session.commit()


# ===================== BLUPRINT ДЛЯ AI-АНАЛІТИКИ =====================

ai_jobs_bp = Blueprint("ai_jobs", __name__)


@ai_jobs_bp.route("/api/ai/tools_stats", methods=["GET"])
def api_ai_tools_stats():
    """
    GET /api/ai/tools_stats

    Віддає aggregated stats по всіх AIJob (для dashboard_ai_tools.js):

      {
        "ok": true,
        "items": [ ... ],
        "totals": {
          "used_count": ...,
          "credits_spent": ...,
          "jobs_running": ...
        }
      }
    """
    # Можна обмежити наприклад останні 90 днів:
    days_limit = 90
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days_limit)

    jobs_query = (
        AIJob.query
        .filter(AIJob.created_at >= since)
        .order_by(AIJob.created_at.desc())
    )
    jobs = jobs_query.all()

    items = _aggregate_tools_stats(jobs)

    total_used = sum(j.used_count for j in items) if items else 0
    total_credits = sum(j["credits_spent"] or 0 for j in items) if items else 0

    jobs_running = (
        AIJob.query.filter(AIJob.status == "running").count()
    )

    return jsonify({
        "ok": True,
        "items": items,
        "totals": {
            "used_count": int(total_used),
            "credits_spent": int(total_credits),
            "jobs_running": int(jobs_running),
        },
    })


@ai_jobs_bp.route("/api/ai/jobs_recent", methods=["GET"])
def api_ai_jobs_recent():
    """
    GET /api/ai/jobs_recent?limit=30

    Повертає останні AI-задачі для таблички на дашборді:

      {
        "ok": true,
        "items": [ {id, tool_key, tool_name, status, ...}, ... ]
      }
    """
    try:
        limit = int(request.args.get("limit", "30"))
    except Exception:
        limit = 30
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    jobs = (
        AIJob.query
        .order_by(AIJob.created_at.desc())
        .limit(limit)
        .all()
    )

    items = [j.to_brief_dict() for j in jobs]
    return jsonify({"ok": True, "items": items})


@ai_jobs_bp.route("/api/ai/jobs/stop_running", methods=["POST"])
def api_ai_jobs_stop_running():
    """
    POST /api/ai/jobs/stop_running

    Адмінська дія: позначити всі running-задачі як error із повідомленням
    "Stopped by admin". dashboard_ai_tools.js викликає це, якщо ти натиснеш
    кнопку "Зупинити всі завислі".

    Відповідь:
      { "ok": true, "affected": N }
    """
    now = datetime.datetime.utcnow()
    q = AIJob.query.filter(AIJob.status == "running")
    running_jobs = q.all()

    affected = 0
    for j in running_jobs:
        j.status = "error"
        j.error_msg = (j.error_msg or "") + "\nStopped by admin."
        j.finished_at = now
        j.latency_ms = _calc_latency_ms(j.started_at or j.created_at, j.finished_at)
        affected += 1

    if affected:
        db.session.commit()

    current_app.logger.info("AI jobs stop_running: affected=%s", affected)

    return jsonify({"ok": True, "affected": affected})
