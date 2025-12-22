import io
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request
from werkzeug.datastructures import FileStorage

from models import MarketItem, db  # підлаштуй імпорт під свій проект

printability_api = Blueprint("printability_api", __name__, url_prefix="/api/market")

# Підтримка trimesh (якщо встановлено)
_TRIMESH_READY = False
try:
    import trimesh  # type: ignore

    _TRIMESH_READY = True
except Exception:
    _TRIMESH_READY = False


# ======== УТИЛІТИ ДЛЯ ЗАВАНТАЖЕННЯ МЕШУ ========

def _load_mesh_from_file(file: FileStorage) -> Optional["trimesh.Trimesh"]:
    if not _TRIMESH_READY:
        return None
    try:
        # читаємо в пам'ять
        data = file.read()
        file.seek(0)
        mesh = trimesh.load(io.BytesIO(data), file_type=file.filename.split(".")[-1])
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.dump().sum()
        return mesh
    except Exception as e:
        current_app.logger.exception("Failed to load mesh from file: %s", e)
        return None


def _get_item_mesh(item: MarketItem) -> Optional["trimesh.Trimesh"]:
    """
    Якщо хочеш аналізувати STL, що вже лежить у тебе в Cloudinary/S3/локально —
    тут треба реалізувати завантаження.

    Зараз заглушка: вважаємо, що в item є:
      - item.local_path  (або item.stl_path)
      або
      - item.file_url    (і ти скачаєш через requests.get)

    Я залишаю TODO, щоб ти потім сам доробив.
    """
    if not _TRIMESH_READY:
        return None

    stl_path = getattr(item, "local_path", None) or getattr(item, "stl_path", None)
    if stl_path:
        try:
            mesh = trimesh.load(stl_path)
            if isinstance(mesh, trimesh.Scene):
                mesh = mesh.dump().sum()
            return mesh
        except Exception as e:
            current_app.logger.exception("Failed to load mesh from path: %s", e)
            return None

    # TODO: якщо STL лежить по URL в Cloudinary/S3 — докачати файл
    # file_url = getattr(item, "file_url", None)
    # if file_url:
    #   ...

    return None


# ======== АНАЛІТИКА МЕШУ (ГРУБО, АЛЕ КОРИСНО) ========

def _analyze_mesh(
    mesh: "trimesh.Trimesh",
    material: str,
    layer_height_mm: float,
    supports: str,
) -> Dict[str, Any]:
    """
    Проста евристична перевірка:
      - об'єм, bounding box
      - нависання (відсоток граней з кутом > 45°)
      - тонкі стінки (груба оцінка)
      - дрібні деталі (відсоток дуже малих граней)
    """
    issues: List[Dict[str, Any]] = []
    tips: List[str] = []

    # Базові метрики
    bbox = mesh.bounds  # [[minx,miny,minz], [maxx,maxy,maxz]]
    size = bbox[1] - bbox[0]
    size_mm = [float(x) for x in size]  # вже в мм, якщо модель у мм
    volume_cm3 = float(mesh.volume) / 1000.0 if mesh.volume else 0.0

    # ===== Нависання =====
    overhang_ratio = 0.0
    try:
        normals = mesh.face_normals  # (N,3)
        # нормаль з сильно негативним Z -> нависання
        # cos(45°) ≈ 0.707; беремо z < -0.7 як very steep
        overhang_faces = (normals[:, 2] < -0.7).sum()
        total_faces = len(normals)
        if total_faces > 0:
            overhang_ratio = overhang_faces / total_faces
    except Exception:
        overhang_ratio = 0.0

    # ===== Тонкі стінки (дуже грубо) =====
    # Беремо найменший розмір bounding box і порівнюємо з шириною сопла.
    # Це не ідеально, але хоча б натяк.
    nozzle_mm = 0.4  # припускаємо стандартне сопло
    min_dim = float(min(size_mm)) if size_mm else 0.0
    thin_wall_ratio = 0.0
    if min_dim > 0:
        # Якщо min_dim < 1.5 * nozzle — модель має дуже тонкі деталі
        if min_dim < nozzle_mm * 1.5:
            thin_wall_ratio = (nozzle_mm * 1.5 - min_dim) / (nozzle_mm * 1.5)

    # ===== Дрібні деталі =====
    small_detail_ratio = 0.0
    try:
        areas = mesh.area_faces  # площа кожної грані
        if len(areas):
            median_area = float(mesh.area / len(areas))
            small_faces = (areas < median_area * 0.15).sum()
            small_detail_ratio = small_faces / len(areas)
    except Exception:
        small_detail_ratio = 0.0

    # ==== Формуємо issues ====

    # Нависання
    if overhang_ratio > 0.25 and supports == "off":
        issues.append({
            "title": "Сильні нависання без підтримок",
            "description": (
                "Близько {:.0f}% поверхні має кут понад 45°. "
                "Без підтримок можливі провисання, соплі й невдалі шари."
            ).format(overhang_ratio * 100),
            "value": f"{overhang_ratio:.2f}",
            "severity": "error",
        })
        tips.append(
            "Увімкни підтримки для цієї моделі або розділи деталі, щоб зменшити нависання."
        )
    elif overhang_ratio > 0.25 and supports in ("auto", "on"):
        issues.append({
            "title": "Сильні нависання (потрібні підтримки)",
            "description": (
                "Близько {:.0f}% поверхні має кут понад 45°. "
                "З увімкненими підтримками друк має пройти краще."
            ).format(overhang_ratio * 100),
            "value": f"{overhang_ratio:.2f}",
            "severity": "warning",
        })
        tips.append(
            "Розглянь використання дерев'яних / легковідривних підтримок для економії пластика."
        )

    # Тонкі стінки
    if thin_wall_ratio > 0:
        issues.append({
            "title": "Можливі надто тонкі стінки",
            "description": (
                "Мінімальна товщина моделі ({:.2f} мм) близька до ширини сопла ({:.2f} мм). "
                "Деякі лінії можуть не надрукуватися коректно."
            ).format(min_dim, nozzle_mm),
            "value": f"{min_dim:.2f} мм",
            "severity": "warning",
        })
        tips.append(
            "Збільш товщину тонких деталей або надрукуй модель у більшому масштабі (наприклад, 120%)."
        )

    # Дрібні деталі
    if small_detail_ratio > 0.3 and layer_height_mm >= 0.2:
        issues.append({
            "title": "Багато дрібних деталей для великої висоти шару",
            "description": (
                "Приблизно {:.0f}% граней дуже дрібні. "
                "На висоті шару {:.2f} мм дрібні елементи можуть зникнути."
            ).format(small_detail_ratio * 100, layer_height_mm),
            "value": f"{small_detail_ratio:.2f}",
            "severity": "warning",
        })
        tips.append(
            "Зменш висоту шару (0.16 або 0.12 мм), щоб передати дрібні деталі."
        )

    # Матеріал-специфічні поради
    if material.upper() == "ABS":
        tips.append("Для ABS потрібна закрита камера та адгезія до стола, щоб уникнути викривлень.")
    if material.upper() == "TPU":
        tips.append("Для TPU зменш швидкість друку (20–30 mm/s) і перевірь, щоб не було дуже тонких перемичок.")

    # Summary
    if not issues:
        summary = "Модель виглядає друкованою без серйозних проблем 🎉"
    else:
        num_errors = sum(1 for i in issues if i.get("severity") == "error")
        if num_errors == 0:
            summary = "Є декілька попереджень, але модель можна друкувати з обережністю."
        else:
            summary = (
                f"Виявлено {num_errors} критичних проблем. "
                "Рекомендується внести зміни в модель або налаштування друку."
            )

    return {
        "summary": summary,
        "issues": issues,
        "tips": tips,
        "metrics": {
            "volume_cm3": volume_cm3,
            "size_mm": size_mm,
            "overhang_ratio": overhang_ratio,
            "thin_wall_score": thin_wall_ratio,
            "small_detail_ratio": small_detail_ratio,
        },
    }


# ======== FLASK ENDPOINT ========

@printability_api.route("/printability", methods=["POST"])
def printability_check():
    """
    Приймає:
      - form-data:
          item_id (optional)
          file (optional, STL/OBJ)
          material
          layer_height
          supports

    Повертає JSON з метриками та списком проблем.
    """
    material = (request.form.get("material") or "PLA").upper()
    layer_height_str = request.form.get("layer_height") or "0.2"
    supports = request.form.get("supports") or "auto"

    try:
        layer_height_mm = float(layer_height_str)
    except ValueError:
        layer_height_mm = 0.2

    file = request.files.get("file")
    item_id = request.form.get("item_id")

    mesh = None

    # Якщо є файл — пріоритетно аналізуємо його
    if file and file.filename:
        mesh = _load_mesh_from_file(file)

    # Якщо mesh ще немає і передано item_id — пробуємо завантажити зі сховища
    if mesh is None and item_id:
        try:
            item_obj = db.session.get(MarketItem, int(item_id))
        except Exception:
            item_obj = None

        if item_obj is not None:
            mesh = _get_item_mesh(item_obj)

    if not _TRIMESH_READY:
        # Якщо немає trimesh — повертаємо заглушку, щоб UI не ламався
        return jsonify({
            "summary": "Детальний 3D-аналіз недоступний (бракує модуля trimesh на сервері).",
            "issues": [],
            "tips": [
                "Встанови пакет 'trimesh' у своє середовище Python для повноцінного аналізу.",
                "Поки що орієнтуйся на досвід та прев’ю моделі в слайсері."
            ],
            "metrics": {},
        })

    if mesh is None:
        return jsonify({
            "summary": "Не вдалося завантажити модель для аналізу.",
            "issues": [],
            "tips": ["Перевір, що STL/OBJ не пошкоджений, або спробуй інший файл."],
            "metrics": {},
        }), 400

    result = _analyze_mesh(mesh, material, layer_height_mm, supports)
    return jsonify(result)
