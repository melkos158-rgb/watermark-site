import datetime
from typing import Any, Dict, Optional

from flask import Blueprint, current_app, g, jsonify, request, session

from models import db  # беремо той самий db, що й для MarketItem та ін.

# Blueprint для API профілів принтерів
printer_profiles_bp = Blueprint("printer_profiles", __name__)


# ===================== МОДЕЛЬ =====================

class PrinterProfile(db.Model):
    __tablename__ = "printer_profiles"

    id = db.Column(db.Integer, primary_key=True)
    # простий owner_id без FK, щоб не ламати існуючу схему
    owner_id = db.Column(db.Integer, index=True, nullable=True)

    name = db.Column(db.String(255), nullable=False)
    model = db.Column(db.String(255), nullable=True)
    type = db.Column(db.String(64), nullable=True)
    firmware = db.Column(db.String(128), nullable=True)

    bed_x = db.Column(db.Float, nullable=True)
    bed_y = db.Column(db.Float, nullable=True)
    bed_z = db.Column(db.Float, nullable=True)

    filament_diameter = db.Column(db.Float, nullable=True)
    nozzle_diameter = db.Column(db.Float, nullable=True)

    temp_nozzle = db.Column(db.Float, nullable=True)
    temp_bed = db.Column(db.Float, nullable=True)

    max_print_speed = db.Column(db.Float, nullable=True)   # мм/с
    max_travel_speed = db.Column(db.Float, nullable=True)  # мм/с

    materials = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "model": self.model,
            "type": self.type,
            "firmware": self.firmware,
            "bed_x": self.bed_x,
            "bed_y": self.bed_y,
            "bed_z": self.bed_z,
            "filament_diameter": self.filament_diameter,
            "nozzle_diameter": self.nozzle_diameter,
            "temp_nozzle": self.temp_nozzle,
            "temp_bed": self.temp_bed,
            "max_print_speed": self.max_print_speed,
            "max_travel_speed": self.max_travel_speed,
            "materials": self.materials,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ===================== УТИЛІТИ =====================

def _get_current_user_id() -> Optional[int]:
    """
    Пробуємо витягнути id юзера:
    - з g.user.id (якщо в тебе є такий механізм)
    - з session["user_id"]
    Якщо немає — працюємо як "глобальні" профілі (owner_id = None).
    """
    try:
        if hasattr(g, "user") and getattr(g.user, "id", None) is not None:
            return int(g.user.id)
    except Exception:
        pass
    try:
        uid = session.get("user_id")
        if uid is not None:
            return int(uid)
    except Exception:
        pass
    return None


def _owner_filter(query):
    """
    Фільтрує профілі по owner_id. Якщо користувач не залогінений,
    показуємо лише записи без owner_id.
    """
    uid = _get_current_user_id()
    if uid is None:
        return query.filter(PrinterProfile.owner_id.is_(None))
    return query.filter(PrinterProfile.owner_id == uid)


def _parse_float(data: Dict[str, Any], key: str):
    v = data.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _parse_str(data: Dict[str, Any], key: str):
    v = data.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _update_profile_from_payload(p: PrinterProfile, payload: Dict[str, Any]):
    p.name = (_parse_str(payload, "name") or p.name or "Unnamed printer")

    # прості текстові
    if "model" in payload:
        p.model = _parse_str(payload, "model")
    if "type" in payload:
        p.type = _parse_str(payload, "type")
    if "firmware" in payload:
        p.firmware = _parse_str(payload, "firmware")

    # числові
    for field in [
        "bed_x",
        "bed_y",
        "bed_z",
        "filament_diameter",
        "nozzle_diameter",
        "temp_nozzle",
        "temp_bed",
        "max_print_speed",
        "max_travel_speed",
    ]:
        if field in payload:
            setattr(p, field, _parse_float(payload, field))

    # текстові поля
    if "materials" in payload:
        p.materials = _parse_str(payload, "materials")
    if "notes" in payload:
        p.notes = _parse_str(payload, "notes")


def _get_profile_or_404(pid: int) -> Optional[PrinterProfile]:
    q = _owner_filter(PrinterProfile.query).filter(PrinterProfile.id == pid)
    profile = q.first()
    return profile


# ===================== ROUTES =====================

@printer_profiles_bp.route("/api/printers", methods=["GET"])
def list_printers():
    """
    Отримати список профілів поточного користувача (або глобальних, якщо юзер не залогінений).

    Відповідь:
      {
        "ok": true,
        "items": [ {...}, ... ]
      }
    """
    q = _owner_filter(PrinterProfile.query).order_by(
        PrinterProfile.is_active.desc(),
        PrinterProfile.created_at.desc(),
    )
    items = [p.to_dict() for p in q.all()]
    return jsonify({"ok": True, "items": items})


@printer_profiles_bp.route("/api/printers", methods=["POST"])
def create_printer():
    """
    Створення нового профілю.
    POST JSON:
      {
        "name": "...",  // обовʼязково
        "model": "...",
        "type": "cartesian|corexy|delta|bambu|resin|...",
        ...
      }
    """
    data = request.get_json(silent=True) or {}
    name = _parse_str(data, "name")
    if not name:
        return jsonify({"ok": False, "error": "Поле 'name' є обовʼязковим."}), 400

    uid = _get_current_user_id()

    p = PrinterProfile()
    p.owner_id = uid
    p.name = name
    _update_profile_from_payload(p, data)

    db.session.add(p)
    db.session.commit()

    current_app.logger.info("Created printer profile id=%s for user=%s", p.id, uid)

    return jsonify({"ok": True, "item": p.to_dict()})


@printer_profiles_bp.route("/api/printers/<int:pid>", methods=["PUT"])
def update_printer(pid: int):
    """
    Оновлення існуючого профілю.
    """
    profile = _get_profile_or_404(pid)
    if not profile:
        return jsonify({"ok": False, "error": "Профіль не знайдено."}), 404

    data = request.get_json(silent=True) or {}

    # Якщо name не прийшов взагалі — не чіпаємо; якщо прийшов пустий -> помилка
    if "name" in data:
        name = _parse_str(data, "name")
        if not name:
            return jsonify({"ok": False, "error": "Поле 'name' не може бути порожнім."}), 400

    _update_profile_from_payload(profile, data)
    db.session.commit()

    current_app.logger.info("Updated printer profile id=%s", profile.id)

    return jsonify({"ok": True, "item": profile.to_dict()})


@printer_profiles_bp.route("/api/printers/<int:pid>", methods=["DELETE"])
def delete_printer(pid: int):
    """
    Видалення профілю.
    """
    profile = _get_profile_or_404(pid)
    if not profile:
        return jsonify({"ok": False, "error": "Профіль не знайдено."}), 404

    was_active = profile.is_active

    db.session.delete(profile)
    db.session.commit()

    current_app.logger.info("Deleted printer profile id=%s", pid)

    # Якщо видалили активний профіль — просто нічого не робимо, активний стає "нічого".
    return jsonify({"ok": True, "was_active": bool(was_active)})


@printer_profiles_bp.route("/api/printers/active", methods=["GET"])
def get_active_printer():
    """
    Повертає активний профіль для поточного користувача.

    Відповідь:
      {
        "ok": true,
        "item": {...} | null
      }
    """
    q = _owner_filter(PrinterProfile.query).filter(PrinterProfile.is_active.is_(True))
    profile = q.first()
    return jsonify({"ok": True, "item": profile.to_dict() if profile else None})


@printer_profiles_bp.route("/api/printers/<int:pid>/activate", methods=["POST"])
def activate_printer(pid: int):
    """
    Зробити профіль активним (один активний на користувача / owner_id).

    POST /api/printers/<id>/activate
    """
    profile = _get_profile_or_404(pid)
    if not profile:
        return jsonify({"ok": False, "error": "Профіль не знайдено."}), 404

    uid = _get_current_user_id()

    # Скидаємо всі інші is_active для цього owner_id
    q = _owner_filter(PrinterProfile.query)
    for p in q.all():
        p.is_active = (p.id == profile.id)

    db.session.commit()

    current_app.logger.info("Activated printer profile id=%s for user=%s", pid, uid)

    return jsonify({"ok": True, "item": profile.to_dict()})
