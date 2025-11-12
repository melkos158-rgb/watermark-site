import os
import uuid
import math
from typing import Dict, Any

from flask import Blueprint, request, jsonify, current_app, send_from_directory, abort

# Blueprint для API параметричних моделей
parametric_bp = Blueprint("parametric_api", __name__)

# ======================== УТИЛІТИ ========================


def _get_parametric_dir() -> str:
    """
    Папка, де будуть зберігатися тимчасові STL-файли
    (параметричні моделі, згенеровані під користувача).
    """
    base_dir = current_app.config.get(
        "PARAMETRIC_TMP",
        os.path.join(current_app.instance_path, "parametric")
    )
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def _parse_float(data: Dict[str, Any], key: str, default: float) -> float:
    try:
        v = data.get(key, default)
        return float(v)
    except Exception:
        return default


# ======================== ГЕНЕРАЦІЯ STL ========================

def _generate_cube_triangles(width: float, depth: float, height: float):
    """
    Генерує трикутники для звичайного прямокутного паралелепіпеда (куба)
    розміром width x depth x height, центрованого в (0,0,0).

    Повертає список граней:
        [ ((x1,y1,z1),(x2,y2,z2),(x3,y3,z3), normal_xyz), ... ]
    """
    hx = width / 2.0
    hy = depth / 2.0
    hz = height / 2.0

    # Вершини
    # верх
    v000 = (-hx, -hy, -hz)
    v100 = (hx, -hy, -hz)
    v010 = (-hx, hy, -hz)
    v110 = (hx, hy, -hz)
    # низ
    v001 = (-hx, -hy, hz)
    v101 = (hx, -hy, hz)
    v011 = (-hx, hy, hz)
    v111 = (hx, hy, hz)

    faces = []

    def add_face(a, b, c, normal):
        faces.append((a, b, c, normal))

    # НИЗ (z = -hz) – нормаль вниз
    add_face(v000, v100, v110, (0.0, 0.0, -1.0))
    add_face(v000, v110, v010, (0.0, 0.0, -1.0))

    # ВЕРХ (z = +hz) – нормаль вгору
    add_face(v001, v011, v111, (0.0, 0.0, 1.0))
    add_face(v001, v111, v101, (0.0, 0.0, 1.0))

    # ПЕРЕД (y = -hy)
    add_face(v000, v001, v101, (0.0, -1.0, 0.0))
    add_face(v000, v101, v100, (0.0, -1.0, 0.0))

    # ЗАД (y = +hy)
    add_face(v010, v110, v111, (0.0, 1.0, 0.0))
    add_face(v010, v111, v011, (0.0, 1.0, 0.0))

    # ЛІВА (x = -hx)
    add_face(v000, v010, v011, (-1.0, 0.0, 0.0))
    add_face(v000, v011, v001, (-1.0, 0.0, 0.0))

    # ПРАВА (x = +hx)
    add_face(v100, v101, v111, (1.0, 0.0, 0.0))
    add_face(v100, v111, v110, (1.0, 0.0, 0.0))

    return faces


def _write_ascii_stl(path: str, faces, solid_name: str = "proofly_parametric"):
    """
    Записує список трикутників у ASCII STL.
    faces: список з елементів (v1, v2, v3, normal),
           де v1, v2, v3 — (x,y,z), normal — (nx,ny,nz)
    """
    with open(path, "w", encoding="ascii") as f:
        f.write(f"solid {solid_name}\n")
        for v1, v2, v3, n in faces:
            nx, ny, nz = n
            f.write(f"  facet normal {nx:.6e} {ny:.6e} {nz:.6e}\n")
            f.write("    outer loop\n")
            for vx, vy, vz in (v1, v2, v3):
                f.write(f"      vertex {vx:.6e} {vy:.6e} {vz:.6e}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {solid_name}\n")


def _generate_cube_stl(path: str, width: float, depth: float, height: float):
    faces = _generate_cube_triangles(width, depth, height)
    _write_ascii_stl(path, faces, solid_name="proofly_cube")


# ======================== ЛОГІКА ПАРАМЕТРИКИ ========================

def _compute_cube_stats(width: float, depth: float, height: float, unit: str = "mm") -> Dict[str, Any]:
    """
    Дуже проста оцінка обʼєму та площі поверхні для паралелепіпеда.
    Все в одиницях, які прийшли з UI (unit).
    """
    volume = width * depth * height  # кубічні одиниці
    surface = 2.0 * (width * depth + width * height + depth * height)
    return {
        "shape": "cube",
        "unit": unit,
        "width": width,
        "depth": depth,
        "height": height,
        "volume": volume,
        "surface_area": surface,
        "bbox": {
            "min": [-width / 2.0, -depth / 2.0, -height / 2.0],
            "max": [width / 2.0, depth / 2.0, height / 2.0],
        },
    }


# ======================== ENDPOINTS ========================

@parametric_bp.route("/api/parametric/preview", methods=["POST"])
def parametric_preview():
    """
    Швидкий попередній розрахунок параметричної моделі.
    Наразі підтримується shape='cube'.

    Вхід (JSON):
      {
        "shape": "cube",
        "width": 20,
        "depth": 10,
        "height": 5,
        "unit": "mm"
      }

    Вихід (JSON):
      {
        "ok": true,
        "shape": "cube",
        "stats": {...}
      }
    """
    data = request.get_json(silent=True) or {}
    shape = (data.get("shape") or "cube").lower()
    unit = (data.get("unit") or "mm").lower()

    if shape != "cube":
        return jsonify({
            "ok": False,
            "error": "Наразі підтримується тільки shape='cube'.",
            "supported_shapes": ["cube"]
        }), 400

    width = _parse_float(data, "width", 20.0)
    depth = _parse_float(data, "depth", width)
    height = _parse_float(data, "height", width)

    # Захист від нульових/некоректних значень
    width = max(width, 0.01)
    depth = max(depth, 0.01)
    height = max(height, 0.01)

    stats = _compute_cube_stats(width, depth, height, unit=unit)

    return jsonify({
        "ok": True,
        "shape": shape,
        "stats": stats,
    })


@parametric_bp.route("/api/parametric/export", methods=["POST"])
def parametric_export():
    """
    Генерація STL-файлу для параметричної моделі.
    Наразі – тільки прямокутний паралелепіпед (shape='cube').

    Вхід (JSON):
      {
        "shape": "cube",
        "width": 20,
        "depth": 10,
        "height": 5,
        "unit": "mm"
      }

    Вихід (JSON):
      {
        "ok": true,
        "download_url": "/api/parametric/download/<job_id>",
        "job_id": "<job_id>",
        "stats": {...}
      }
    """
    data = request.get_json(silent=True) or {}
    shape = (data.get("shape") or "cube").lower()
    unit = (data.get("unit") or "mm").lower()

    if shape != "cube":
        return jsonify({
            "ok": False,
            "error": "Наразі підтримується тільки shape='cube'.",
            "supported_shapes": ["cube"]
        }), 400

    width = _parse_float(data, "width", 20.0)
    depth = _parse_float(data, "depth", width)
    height = _parse_float(data, "height", width)

    width = max(width, 0.01)
    depth = max(depth, 0.01)
    height = max(height, 0.01)

    job_id = uuid.uuid4().hex
    base_dir = _get_parametric_dir()
    filename = f"{job_id}.stl"
    path = os.path.join(base_dir, filename)

    try:
        _generate_cube_stl(path, width, depth, height)
    except Exception as e:
        current_app.logger.exception("parametric_export generation failed")
        return jsonify({"ok": False, "error": f"Помилка генерації STL: {e}"}), 500

    stats = _compute_cube_stats(width, depth, height, unit=unit)

    download_url = f"/api/parametric/download/{job_id}"

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "download_url": download_url,
        "shape": shape,
        "stats": stats,
    })


@parametric_bp.route("/api/parametric/download/<job_id>", methods=["GET"])
def parametric_download(job_id: str):
    """
    Видає згенерований STL-файл по job_id.
    """
    base_dir = _get_parametric_dir()
    filename = f"{job_id}.stl"
    path = os.path.join(base_dir, filename)

    if not os.path.isfile(path):
        abort(404, description="Файл не знайдено")

    # send_from_directory сам проставить потрібні заголовки для завантаження
    return send_from_directory(
        base_dir,
        filename,
        as_attachment=True,
        download_name=f"proofly_parametric_{job_id}.stl"
    )
