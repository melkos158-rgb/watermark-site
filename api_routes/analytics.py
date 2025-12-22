import datetime
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, render_template, request

from models import db

# ===================== МОДЕЛЬ =====================

class AnalyticsDaily(db.Model):
    """
    Проста й гнучка таблиця для зберігання денних метрик:
      - visitors  — унікальні відвідувачі
      - signups   — нові реєстрації
      - models    — нові моделі / STL
      - будь-що інше (metric = custom string)

    Кожен запис: одна метрика за один день.
    """
    __tablename__ = "analytics_daily"

    id = db.Column(db.Integer, primary_key=True)
    metric = db.Column(db.String(64), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    value = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint("metric", "day", name="uq_metric_day"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "metric": self.metric,
            "day": self.day.isoformat() if self.day else None,
            "value": self.value,
        }


# ===================== BLUPRINT =====================

analytics_bp = Blueprint("analytics", __name__)


# ===================== УТИЛІТИ =====================

def _clamp_days(raw: str, default: int = 30) -> int:
    try:
        n = int(raw)
    except Exception:
        return default
    if n < 1:
        return 1
    if n > 365:
        return 365
    return n


def _make_date_range(days: int) -> List[datetime.date]:
    """
    Створює список дат (date), наприклад останні 30 днів включно з сьогодні.
    Від найстарішої до найновішої.
    """
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    out = []
    cur = start
    while cur <= today:
        out.append(cur)
        cur += datetime.timedelta(days=1)
    return out


def _get_series_from_db(metric: str, days: int) -> List[Dict[str, Any]]:
    """
    Повертає масив точок виду:
      [ { "date": "2025-11-01", "value": 123 }, ... ]
    використовуючи таблицю analytics_daily.
    Якщо для якоїсь дати немає запису — value = 0.
    """
    date_range = _make_date_range(days)
    if not date_range:
        return []

    start = date_range[0]
    end = date_range[-1]

    rows = (
        AnalyticsDaily.query
        .filter(AnalyticsDaily.metric == metric)
        .filter(AnalyticsDaily.day >= start)
        .filter(AnalyticsDaily.day <= end)
        .all()
    )

    by_day = {row.day: row.value for row in rows}

    result = []
    for d in date_range:
        result.append({
            "date": d.isoformat(),
            "value": int(by_day.get(d, 0) or 0),
        })
    return result


# ===================== API: СЕРІЇ ДЛЯ ГРАФІКІВ =====================

@analytics_bp.route("/api/analytics/series", methods=["GET"])
def api_analytics_series():
    """
    GET /api/analytics/series?metric=visitors&days=30

    Повертає часовий ряд для графіків в адмінці:

      {
        "ok": true,
        "metric": "visitors",
        "days": 30,
        "points": [
          { "date": "2025-11-01", "value": 123 },
          ...
        ]
      }

    Підтримувані metric (на старті):
      - visitors
      - signups
      - models
      - будь-які інші рядки (можна буде використовувати пізніше)
    """
    metric = request.args.get("metric", "visitors").strip().lower()
    days = _clamp_days(request.args.get("days", "30"), default=30)

    # Нормалізуємо метрики: поки що просто приймаємо будь-що,
    # але для "левелів" можна робити alias.
    if metric not in ("visitors", "signups", "models"):
        # Невідомі метрики теж підтримуємо — можливо ти захочеш додати щось своє
        current_app.logger.info("analytics: requesting custom metric=%s days=%s", metric, days)

    points = _get_series_from_db(metric, days)

    return jsonify({
        "ok": True,
        "metric": metric,
        "days": days,
        "points": points,
    })


# ===================== VIEW ДЛЯ СТОРІНКИ АНАЛІТИКИ =====================

@analytics_bp.route("/analytics", methods=["GET"])
def analytics_page():
    """
    Сторінка /analytics з адмін-графіками.
    Шаблон analytics.html використовує stats_charts.js для рендеру.
    """
    # Можна передати базові діапазони, якщо захочеш використати в шаблоні.
    ranges = [7, 14, 30, 60, 90]
    return render_template("analytics.html", ranges=ranges)
