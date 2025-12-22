import math
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

# Blueprint для аналізу G-code
gcode_metrics_bp = Blueprint("gcode_metrics", __name__)


# ======================== УТИЛІТИ ========================

def _sec_to_hms(seconds: float) -> str:
    """Форматування секунд у вигляді H:MM:SS."""
    seconds = max(0, int(round(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


class GCodeStats:
    """
    Дуже спрощений аналізатор G-code на Python:
    - розуміє G0/G1 (X/Y/Z/E/F)
    - вважає координати абсолютними
    - рахує:
        * довжину друкуючих переміщень
        * довжину холостих переміщень
        * сумарну екструзію
        * оцінку часу друку
        * bbox
        * статистику по шарам
    """

    def __init__(self):
        # Поточні стани
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.e = 0.0
        self.f = 0.0

        # Прапори
        self.inited_xy = False

        # Лічильники
        self.lines_total = 0
        self.moves_total = 0
        self.print_moves = 0
        self.travel_moves = 0

        self.length_print = 0.0
        self.length_travel = 0.0
        self.extrusion_total = 0.0

        # bbox тільки по XY для друкуючих сегментів
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf
        self.min_z = math.inf
        self.max_z = -math.inf

        # Час
        self.time_print_sec = 0.0
        self.time_travel_sec = 0.0

        # Шари: {z: {"length": .., "extrusion": .., "print_moves": ..}}
        self.layers: Dict[float, Dict[str, Any]] = {}

        # Max/min швидкість
        self.min_f = math.inf
        self.max_f = 0.0

        # Налаштування дефолтних швидкостей, якщо F == 0:
        # (мм/хв)
        self.default_print_speed = 2400.0  # 40 мм/с
        self.default_travel_speed = 4800.0  # 80 мм/с

    def _update_bbox(self, x: float, y: float, z: float):
        if x < self.min_x:
            self.min_x = x
        if x > self.max_x:
            self.max_x = x
        if y < self.min_y:
            self.min_y = y
        if y > self.max_y:
            self.max_y = y
        if z < self.min_z:
            self.min_z = z
        if z > self.max_z:
            self.max_z = z

    def _get_or_create_layer(self, z: float) -> Dict[str, Any]:
        # Округлюємо Z до 3 знаків для групування
        z_key = round(z, 3)
        if z_key not in self.layers:
            self.layers[z_key] = {
                "z": z_key,
                "length": 0.0,
                "extrusion": 0.0,
                "print_moves": 0,
            }
        return self.layers[z_key]

    def _handle_move(self, tokens: List[str]):
        x = self.x
        y = self.y
        z = self.z
        e = self.e
        f = self.f

        for token in tokens:
            token = token.strip()
            if not token:
                continue
            code = token[0].upper()
            val_str = token[1:]
            val = _safe_float(val_str, None)
            if val is None:
                continue
            if code == "X":
                x = val
            elif code == "Y":
                y = val
            elif code == "Z":
                z = val
            elif code == "E":
                e = val
            elif code == "F":
                f = val

        # Переміщення
        dx = x - self.x
        dy = y - self.y
        z - self.z
        distance_xy = math.sqrt(dx * dx + dy * dy)

        # Якщо це перші координати X/Y — просто оновлюємо, без метрик
        if not self.inited_xy:
            self.x, self.y, self.z, self.e, self.f = x, y, z, e, f
            self.inited_xy = True
            return

        self.moves_total += 1

        # Екструзія збільшилась?
        delta_e = e - self.e
        extruding = delta_e > 1e-6

        # Швидкість
        # Якщо F не оновили — лишається попередній.
        if f > 0:
            self.f = f

        # Вибір швидкості для часу
        if extruding:
            self.print_moves += 1
            self.length_print += distance_xy
            self.extrusion_total += max(0.0, delta_e)
            self._update_bbox(x, y, z)

            if self.f > 0:
                speed = self.f
            else:
                speed = self.default_print_speed

            # час у секундах: 60 * довжина / (мм/хв)
            self.time_print_sec += 60.0 * distance_xy / max(speed, 1.0)

            # По шарам
            layer = self._get_or_create_layer(z)
            layer["length"] += distance_xy
            layer["extrusion"] += max(0.0, delta_e)
            layer["print_moves"] += 1
        else:
            # Холостий рух
            self.travel_moves += 1
            self.length_travel += distance_xy

            if self.f > 0:
                speed = self.f
            else:
                speed = self.default_travel_speed

            self.time_travel_sec += 60.0 * distance_xy / max(speed, 1.0)

        if self.f > 0:
            if self.f < self.min_f:
                self.min_f = self.f
            if self.f > self.max_f:
                self.max_f = self.f

        # Оновлюємо поточні координати
        self.x, self.y, self.z, self.e = x, y, z, e

    def parse(self, gcode: str):
        """
        Основний метод парсингу.
        """
        for raw in gcode.splitlines():
            self.lines_total += 1
            # Прибираємо коментарі після ;
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].upper()

            if cmd in ("G0", "G1"):
                self._handle_move(parts[1:])
            else:
                # інші G-коди нам не критично обробляти
                continue

    # ======================== РЕЗУЛЬТАТИ ========================

    def build_result(self) -> Dict[str, Any]:
        # bbox
        if self.min_x is math.inf:
            bbox = None
        else:
            bbox = {
                "min_x": self.min_x,
                "min_y": self.min_y,
                "min_z": self.min_z,
                "max_x": self.max_x,
                "max_y": self.max_y,
                "max_z": self.max_z,
                "size_x": self.max_x - self.min_x,
                "size_y": self.max_y - self.min_y,
                "size_z": self.max_z - self.min_z,
            }

        # часи
        total_time_sec = self.time_print_sec + self.time_travel_sec

        # шари
        layers_list = sorted(self.layers.values(), key=lambda l: l["z"])
        layers_stats = {
            "count": len(layers_list),
            "layers": layers_list,
        }

        # філамент: умовна оцінка обʼєму з екструзії (E у мм)
        # Припустимо, що E — довжина філамента (як у класичному Marlin).
        # Обʼєм (мм^3) = довжина (мм) * площа перерізу (π * (d/2)^2).
        filament_diameter = 1.75  # мм
        filament_radius = filament_diameter / 2.0
        filament_area = math.pi * filament_radius * filament_radius
        filament_volume_mm3 = self.extrusion_total * filament_area
        filament_volume_cm3 = filament_volume_mm3 / 1000.0

        # Попередження
        warnings: List[str] = []
        if bbox:
            if bbox["size_z"] < 0.05:
                warnings.append(
                    "Дуже мала висота по Z — можливо, це один шар або лазерний/пен-проєкт."
                )
        if total_time_sec <= 60:
            warnings.append("Орієнтовний час друку менше 1 хвилини — можливо, це тестовий G-code.")
        if self.moves_total == 0:
            warnings.append("Не знайдено рухів G0/G1 у G-code.")

        if not math.isfinite(self.min_f):
            self.min_f = 0.0

        return {
            "summary": {
                "lines_total": self.lines_total,
                "moves_total": self.moves_total,
                "print_moves": self.print_moves,
                "travel_moves": self.travel_moves,
                "length_print_mm": self.length_print,
                "length_travel_mm": self.length_travel,
                "extrusion_total_mm": self.extrusion_total,
                "filament_volume_mm3": filament_volume_mm3,
                "filament_volume_cm3": filament_volume_cm3,
                "time_print_sec": self.time_print_sec,
                "time_travel_sec": self.time_travel_sec,
                "time_total_sec": total_time_sec,
                "time_print_hms": _sec_to_hms(self.time_print_sec),
                "time_travel_hms": _sec_to_hms(self.time_travel_sec),
                "time_total_hms": _sec_to_hms(total_time_sec),
                "min_feed_mm_per_min": self.min_f,
                "max_feed_mm_per_min": self.max_f,
            },
            "bbox": bbox,
            "layers": layers_stats,
            "warnings": warnings,
        }


# ======================== ENDPOINT ========================

@gcode_metrics_bp.route("/api/gcode/metrics", methods=["POST"])
def gcode_metrics():
    """
    Аналіз G-code файлу або сирого тексту.

    Варіант 1: multipart/form-data (файл)
      file: *.gcode

    Варіант 2: JSON:
      {
        "gcode": "G1 X10 Y10 E0.5 ...",
      }

    Відповідь:
      {
        "ok": true,
        "metrics": { ... }
      }
    """
    gcode_text: Optional[str] = None

    # 1) Файл
    if "file" in request.files:
        file = request.files["file"]
        if file and file.filename:
            try:
                gcode_text = file.read().decode("utf-8", errors="ignore")
            except Exception as e:
                current_app.logger.exception("G-code file decode error")
                return jsonify({"ok": False, "error": f"Помилка читання файлу: {e}"}), 400

    # 2) JSON з сирим текстом
    if gcode_text is None:
        data = request.get_json(silent=True) or {}
        gcode_text = data.get("gcode") or ""

    if not gcode_text or not gcode_text.strip():
        return jsonify({
            "ok": False,
            "error": "Не передано G-code. Завантаж файл або надішли поле 'gcode' у JSON."
        }), 400

    try:
        stats = GCodeStats()
        stats.parse(gcode_text)
        result = stats.build_result()
    except Exception as e:
        current_app.logger.exception("G-code metrics parsing failed")
        return jsonify({
            "ok": False,
            "error": f"Помилка аналізу G-code: {e}",
        }), 500

    return jsonify({
        "ok": True,
        "metrics": result,
    })
