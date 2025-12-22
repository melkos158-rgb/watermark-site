import datetime
from typing import Any, Dict, Optional

from flask import (Blueprint, abort, current_app, jsonify, render_template,
                   request)

from models import db

# ІМʼЯ блупринта = "licenses" (щоб працював url_for('licenses.view_license', ...))
licenses_bp = Blueprint("licenses", __name__)


# ===================== МОДЕЛЬ ЛІЦЕНЗІЇ =====================

class License(db.Model):
  __tablename__ = "licenses"

  id = db.Column(db.Integer, primary_key=True)

  # Назва та код (slug)
  name = db.Column(db.String(255), nullable=False)
  code = db.Column(db.String(128), unique=True, nullable=False, index=True)

  # Тип: proofly / cc / custom
  type = db.Column(db.String(32), nullable=False, default="proofly")

  # Короткий підзаголовок (видно у маркеті)
  short_title = db.Column(db.String(255), nullable=True)

  # Короткий опис (summary)
  summary = db.Column(db.Text, nullable=True)

  # Прапори прав/обмежень
  allow_print = db.Column(db.Boolean, nullable=False, default=True)
  allow_commercial = db.Column(db.Boolean, nullable=False, default=False)
  allow_remix = db.Column(db.Boolean, nullable=False, default=False)
  allow_redistribute = db.Column(db.Boolean, nullable=False, default=False)

  require_attribution = db.Column(db.Boolean, nullable=False, default=True)
  require_linkback = db.Column(db.Boolean, nullable=False, default=True)
  share_alike = db.Column(db.Boolean, nullable=False, default=False)

  # Ліміт комерційних друків (0 або NULL = без ліміту)
  max_prints = db.Column(db.Integer, nullable=True)

  # Регіон / юрисдикція
  region = db.Column(db.String(64), nullable=True)

  # Повний текст (legal body)
  body = db.Column(db.Text, nullable=True)

  # Для Creative Commons або зовнішніх ліцензій
  external_url = db.Column(db.String(512), nullable=True)

  # Чи є дефолтною ліцензією для маркету
  is_default = db.Column(db.Boolean, nullable=False, default=False, index=True)

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
      "name": self.name,
      "code": self.code,
      "type": self.type,
      "short_title": self.short_title,
      "summary": self.summary,
      "allow_print": self.allow_print,
      "allow_commercial": self.allow_commercial,
      "allow_remix": self.allow_remix,
      "allow_redistribute": self.allow_redistribute,
      "require_attribution": self.require_attribution,
      "require_linkback": self.require_linkback,
      "share_alike": self.share_alike,
      "max_prints": self.max_prints,
      "region": self.region,
      "body": self.body,
      "external_url": self.external_url,
      "is_default": self.is_default,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


# ===================== УТИЛІТИ =====================

def _parse_str(data: Dict[str, Any], key: str) -> Optional[str]:
  v = data.get(key)
  if v is None:
    return None
  s = str(v).strip()
  return s or None


def _parse_bool(data: Dict[str, Any], key: str, default: bool = False) -> bool:
  if key not in data:
    return default
  v = data.get(key)
  if isinstance(v, bool):
    return v
  if isinstance(v, (int, float)):
    return bool(v)
  if isinstance(v, str):
    vs = v.strip().lower()
    if vs in ("1", "true", "yes", "y", "on"):
      return True
    if vs in ("0", "false", "no", "n", "off", ""):
      return False
  return default


def _parse_int(data: Dict[str, Any], key: str) -> Optional[int]:
  if key not in data:
    return None
  v = data.get(key)
  if v is None or v == "":
    return None
  try:
    return int(v)
  except Exception:
    return None


def _update_license_from_payload(lic: License, payload: Dict[str, Any]):
  # Обовʼязкові поля окремо перевіряються там, де викликається ця функція
  if "name" in payload:
    name = _parse_str(payload, "name")
    if name:
      lic.name = name

  if "code" in payload:
    code = _parse_str(payload, "code")
    if code:
      lic.code = code

  if "type" in payload:
    type_val = _parse_str(payload, "type") or "proofly"
    lic.type = type_val[:32]

  if "short_title" in payload:
    lic.short_title = _parse_str(payload, "short_title")

  if "summary" in payload:
    lic.summary = _parse_str(payload, "summary")

  # Прапори
  for field, default in [
    ("allow_print", True),
    ("allow_commercial", False),
    ("allow_remix", False),
    ("allow_redistribute", False),
    ("require_attribution", True),
    ("require_linkback", True),
    ("share_alike", False),
  ]:
    if field in payload:
      setattr(lic, field, _parse_bool(payload, field, default=getattr(lic, field)))

  # Числа
  if "max_prints" in payload:
    lic.max_prints = _parse_int(payload, "max_prints")

  # Регіон
  if "region" in payload:
    lic.region = _parse_str(payload, "region")

  # Повний текст
  if "body" in payload:
    lic.body = _parse_str(payload, "body")

  # External URL (для CC тощо)
  if "external_url" in payload:
    lic.external_url = _parse_str(payload, "external_url")


def _get_default_license_id() -> Optional[int]:
  q = License.query.filter(License.is_default.is_(True)).order_by(License.id.asc())
  lic = q.first()
  return lic.id if lic else None


# ===================== API: ЛІСТ / CRUD =====================

@licenses_bp.route("/api/licenses", methods=["GET"])
def api_list_licenses():
  """
  Повертає список усіх ліцензій + id дефолтної.
  Відповідь:
    {
      "ok": true,
      "items": [ ... ],
      "default_id": 7 | null
    }
  """
  q = License.query.order_by(License.is_default.desc(), License.created_at.asc())
  items = [lic.to_dict() for lic in q.all()]
  default_id = _get_default_license_id()
  return jsonify({"ok": True, "items": items, "default_id": default_id})


@licenses_bp.route("/api/licenses", methods=["POST"])
def api_create_license():
  """
  Створення нової ліцензії.
  Очікує JSON:
    {
      "name": "Proofly Personal",
      "code": "proofly-personal",
      "type": "proofly|cc|custom",
      ...
    }
  """
  data = request.get_json(silent=True) or {}

  name = _parse_str(data, "name")
  code = _parse_str(data, "code")

  if not name:
    return jsonify({"ok": False, "error": "Поле 'name' є обовʼязковим."}), 400
  if not code:
    return jsonify({"ok": False, "error": "Поле 'code' є обовʼязковим."}), 400

  # Перевірка унікальності code
  if License.query.filter(License.code == code).first() is not None:
    return jsonify({"ok": False, "error": "Цей 'code' вже використовується іншою ліцензією."}), 400

  lic = License(name=name, code=code, type=_parse_str(data, "type") or "proofly")
  _update_license_from_payload(lic, data)

  db.session.add(lic)
  db.session.commit()

  current_app.logger.info("Created license id=%s code=%s", lic.id, lic.code)

  default_id = _get_default_license_id()
  return jsonify({"ok": True, "item": lic.to_dict(), "default_id": default_id})


@licenses_bp.route("/api/licenses/<int:lid>", methods=["PUT"])
def api_update_license(lid: int):
  """
  Оновлення існуючої ліцензії.
  """
  lic = License.query.get(lid)
  if not lic:
    return jsonify({"ok": False, "error": "Ліцензію не знайдено."}), 404

  data = request.get_json(silent=True) or {}

  if "name" in data:
    name = _parse_str(data, "name")
    if not name:
      return jsonify({"ok": False, "error": "Поле 'name' не може бути порожнім."}), 400

  if "code" in data:
    code = _parse_str(data, "code")
    if not code:
      return jsonify({"ok": False, "error": "Поле 'code' не може бути порожнім."}), 400
    # Перевірка унікальності code (інший id)
    exists = (
      License.query
      .filter(License.code == code, License.id != lic.id)
      .first()
    )
    if exists:
      return jsonify({"ok": False, "error": "Цей 'code' вже використовується іншою ліцензією."}), 400

  _update_license_from_payload(lic, data)
  db.session.commit()

  current_app.logger.info("Updated license id=%s code=%s", lic.id, lic.code)

  default_id = _get_default_license_id()
  return jsonify({"ok": True, "item": lic.to_dict(), "default_id": default_id})


@licenses_bp.route("/api/licenses/<int:lid>", methods=["DELETE"])
def api_delete_license(lid: int):
  """
  Видалення ліцензії. Якщо видаляємо дефолтну — спробуємо поставити дефолтною
  найстарішу з тих, що залишилися.
  Відповідь:
    { "ok": true, "next_default_id": <id>|null }
  """
  lic = License.query.get(lid)
  if not lic:
    return jsonify({"ok": False, "error": "Ліцензію не знайдено."}), 404

  was_default = lic.is_default

  db.session.delete(lic)
  db.session.commit()

  next_default_id = None
  if was_default:
    # шукаємо наступну (найстарішу) ліцензію
    nxt = License.query.order_by(License.created_at.asc()).first()
    if nxt:
      nxt.is_default = True
      db.session.commit()
      next_default_id = nxt.id

  current_app.logger.info("Deleted license id=%s (was_default=%s)", lid, was_default)

  return jsonify({"ok": True, "next_default_id": next_default_id})


@licenses_bp.route("/api/licenses/<int:lid>/set_default", methods=["POST"])
def api_set_default_license(lid: int):
  """
  Зробити ліцензію дефолтною (єдина default на весь маркет).
  """
  lic = License.query.get(lid)
  if not lic:
    return jsonify({"ok": False, "error": "Ліцензію не знайдено."}), 404

  # Вимикаємо дефолт у всіх, окрім цієї
  for l in License.query.all():
    l.is_default = (l.id == lic.id)

  db.session.commit()

  current_app.logger.info("Set license id=%s as default", lid)

  return jsonify({"ok": True, "default_id": lic.id})


# ===================== VIEW-РОУТИ ДЛЯ licenses.html =====================

@licenses_bp.route("/licenses", methods=["GET"])
def list_public_licenses():
  """
  Публічна сторінка /licenses — показує список усіх ліцензій.
  """
  q = License.query.order_by(License.is_default.desc(), License.created_at.asc())
  licenses = q.all()
  return render_template("licenses.html", license=None, licenses=licenses)


@licenses_bp.route("/licenses/<code>", methods=["GET"])
def view_license(code: str):
  """
  Публічна сторінка /licenses/<code> — показує конкретну ліцензію.
  """
  lic = License.query.filter(License.code == code).first()
  if not lic:
    abort(404)

  # Інші ліцензії для блоку "Інші ліцензії"
  others = (
    License.query
    .filter(License.id != lic.id)
    .order_by(License.is_default.desc(), License.created_at.asc())
    .limit(10)
    .all()
  )

  return render_template("licenses.html", license=lic, other_licenses=others)
