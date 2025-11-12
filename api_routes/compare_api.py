from flask import Blueprint, request, jsonify
from sqlalchemy import select
from models import db, MarketItem  # MarketItem у тебе вже є

compare_api = Blueprint("compare_api", __name__, url_prefix="/api/market")


def _serialize_metrics(item) -> dict:
  """
  Дістає метрики моделі.
  Ми нічого не ламаємо, просто через getattr дістаємо,
  щоб ти міг поступово додати ці колонки/таблиці.
  """

  # Час друку
  print_time_seconds = getattr(item, "print_time_seconds", None)
  print_time_human = getattr(item, "print_time_human", None)
  if not print_time_human and isinstance(print_time_seconds, (int, float)):
    # Примітивна конвертація в "год:хв"
    h = int(print_time_seconds // 3600)
    m = int((print_time_seconds % 3600) // 60)
    if h > 0:
      print_time_human = f"{h}h {m}m"
    else:
      print_time_human = f"{m}m"

  # Об'єм / вага
  volume_cm3 = getattr(item, "volume_cm3", None)
  weight_g = getattr(item, "weight_g", None)

  # Габарити
  size_x = getattr(item, "size_x", None)
  size_y = getattr(item, "size_y", None)
  size_z = getattr(item, "size_z", None)

  # Полігони
  polygons = getattr(item, "polygons", None)

  # Сумісність з принтером (якщо колись зробиш таблицю PrinterProfile + матчинг)
  printer_match_score = getattr(item, "printer_match_score", None)
  printer_match_label = getattr(item, "printer_match_label", None)

  return {
    "id": item.id,
    "print_time_seconds": print_time_seconds,
    "print_time_human": print_time_human,
    "volume_cm3": float(volume_cm3) if volume_cm3 is not None else None,
    "weight_g": float(weight_g) if weight_g is not None else None,
    "size_x": float(size_x) if size_x is not None else None,
    "size_y": float(size_y) if size_y is not None else None,
    "size_z": float(size_z) if size_z is not None else None,
    "polygons": int(polygons) if polygons is not None else None,
    "printer_match_score": float(printer_match_score) if printer_match_score is not None else None,
    "printer_match_label": printer_match_label,
  }


@compare_api.route("/compare", methods=["POST"])
def compare_items():
  """
  Приймає JSON:
    { "items": ["1","2","3"] }

  Повертає:
    {
      "1": { ...метрики... },
      "2": { ... },
      ...
    }
  """
  data = request.get_json(silent=True) or {}
  ids = data.get("items") or []

  # нормалізуємо id → список int/str
  norm_ids = []
  for raw in ids:
    if raw is None:
      continue
    try:
      norm_ids.append(int(raw))
    except (ValueError, TypeError):
      # якщо не int — зберігаємо як є (але все одно додамо)
      try:
        norm_ids.append(int(str(raw)))
      except Exception:
        continue

  if not norm_ids:
    return jsonify({"error": "items is required"}), 400

  stmt = select(MarketItem).where(MarketItem.id.in_(norm_ids))
  items = db.session.execute(stmt).scalars().all()

  result = {}
  for item in items:
    result[str(item.id)] = _serialize_metrics(item)

  return jsonify(result)
