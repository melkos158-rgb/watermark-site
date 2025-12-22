# dev_bp.py
# Blueprint для dev-інструментів:
# - /admin/dev-issues — показує проблемні / сірі / "потрібна правка" фічі (static/dev_graph.json)
# - /admin/dev-map    — глобальна карта файлів зі стрілками (static/dev_tree.json або auto-scan)
#   + /admin/dev-map/positions — збереження позицій вузлів (static/dev_positions.json)

import json
import os

from flask import Blueprint, current_app, jsonify, render_template, request

dev_bp = Blueprint("dev", __name__)

# 🔥 додаємо імпорт автосканера (НЕ міняючи структуру коду)
try:
    from dev_scan import build_dev_tree
except Exception:
    build_dev_tree = None

# файл для збереження позицій
DEV_POSITIONS_FILE = os.path.join("static", "dev_positions.json")


def _load_dev_graph() -> list:
  """
  Читає static/dev_graph.json і повертає список елементів.
  Якщо файл відсутній або битий — повертає пустий список.
  """
  try:
    with current_app.open_resource("static/dev_graph.json") as f:
      data = json.load(f)
      if isinstance(data, list):
        return data
      return []
  except FileNotFoundError:
    current_app.logger.warning("dev_graph.json не знайдено у static/")
    return []
  except Exception as e:
    current_app.logger.error(f"Помилка при читанні dev_graph.json: {e}")
    return []


def _load_dev_tree():
  """
  Читає static/dev_tree.json і повертає дерево вузлів.
  ⛔ Якщо файл відсутній або битий — ПОВНІСТЮ автоматично генерує
     дерево зі всіх файлів проєкту (dev_scan.py).
  """
  # --- 1) пробуємо прочитати static/dev_tree.json ---
  try:
    with current_app.open_resource("static/dev_tree.json") as f:
      data = json.load(f)
      if isinstance(data, dict):
        return data
      current_app.logger.warning("dev_tree.json має неочікуваний формат (очікував dict)")
  except FileNotFoundError:
    current_app.logger.warning("dev_tree.json не знайдено у static/")
  except Exception as e:
    current_app.logger.error(f"Помилка при читанні dev_tree.json: {e}")

  # --- 2) fallback: генеруємо ВСІ файли автоматично ---
  if build_dev_tree:
    try:
      auto_tree = build_dev_tree(current_app.root_path)
      current_app.logger.info("dev_map: використано автоматично згенероване дерево файлів.")
      return auto_tree
    except Exception as err:
      current_app.logger.error(f"Автогенерація dev_tree не вдалася: {err}")

  # --- 3) крайній fallback (мінімальне дерево, щоб не було 500 error) ---
  return {
    "id": "app",
    "label": "app.py",
    "type": "core",
    "status": "ok",
    "children": [],
  }


def _load_positions() -> dict:
  """
  Читає static/dev_positions.json і повертає dict:
  {
    "positions": {
      "node_id": {"x": ..., "y": ...},
      ...
    }
  }
  Якщо файл відсутній або битий — повертає {"positions": {}}.
  """
  try:
    with current_app.open_resource(DEV_POSITIONS_FILE) as f:
      data = json.load(f)
      if isinstance(data, dict) and isinstance(data.get("positions", {}), dict):
        return data
      current_app.logger.warning("dev_positions.json має неочікуваний формат (очікував {positions:{...}})")
      return {"positions": {}}
  except FileNotFoundError:
    current_app.logger.warning("dev_positions.json не знайдено у static/")
    return {"positions": {}}
  except Exception as e:
    current_app.logger.error(f"Помилка при читанні dev_positions.json: {e}")
    return {"positions": {}}


def _save_positions(positions: dict) -> None:
  """
  Зберігає позиції вузлів у static/dev_positions.json у форматі:
  { "positions": { "id": {"x":..., "y":...}, ... } }
  """
  try:
    base = current_app.root_path
    full_path = os.path.join(base, DEV_POSITIONS_FILE)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    payload = {"positions": positions}
    with open(full_path, "w", encoding="utf-8") as f:
      json.dump(payload, f, ensure_ascii=False, indent=2)

    current_app.logger.info("dev_map: позиції збережено у dev_positions.json")
  except Exception as e:
    current_app.logger.error(f"Не вдалося зберегти dev_positions.json: {e}")


def _apply_positions_to_tree(node: dict, pos_map: dict) -> None:
  """
  Рекурсивно проходить дерево й, якщо для node.id є позиція в pos_map,
  додає її в вузол як node['pos'] = {"x":..., "y":...}

  JS зможе використати це, щоб рендерити вузли на збережених координатах.
  """
  if not isinstance(node, dict):
    return

  nid = node.get("id")
  if nid and nid in pos_map:
    node["pos"] = pos_map[nid]

  for child in node.get("children", []) or []:
    _apply_positions_to_tree(child, pos_map)


@dev_bp.route("/admin/dev-issues")
def dev_issues():
  """
  Сторінка з проблемними/сірими/такими, що потребують правки фічами.
  Використовує шаблон templates/dev_issues.html
  """
  items = _load_dev_graph()

  # фільтруємо тільки те, що НЕ зелене:
  # - fix    → потрібна правка
  # - error  → проблема/баг
  # - orphan → не підключений код
  problem_items = [
    it for it in items
    if it.get("status") in ("fix", "error", "orphan")
  ]

  return render_template("dev_issues.html", items=problem_items)


@dev_bp.route("/admin/dev-map")
def dev_map():
  """
  Сторінка з глобальною картою файлів (стрілочки, масштаб, панорамування).
  Використовує шаблон templates/dev_map.html.
  """
  tree = _load_dev_tree()

  # 🔁 Підтягуємо збережені позиції й застосовуємо до дерева
  pos_data = _load_positions()
  pos_map = pos_data.get("positions", {}) or {}
  if isinstance(pos_map, dict) and pos_map:
    _apply_positions_to_tree(tree, pos_map)

  return render_template("dev_map.html", tree=tree)


@dev_bp.route("/admin/dev-map/positions", methods=["POST"])
def dev_map_save_positions():
  """
  API-ендпойнт для збереження позицій вузлів.
  Очікує JSON:
  {
    "positions": {
      "node_id": {"x": <number>, "y": <number>},
      ...
    }
  }
  """
  try:
    data = request.get_json(force=True, silent=True) or {}
    positions = data.get("positions") or {}
    if not isinstance(positions, dict):
      return jsonify({"ok": False, "error": "bad_format"}), 400

    # простий саніті-чек: x,y мають бути числами
    clean_positions = {}
    for nid, pos in positions.items():
      if not isinstance(pos, dict):
        continue
      x = pos.get("x")
      y = pos.get("y")
      try:
        x = float(x)
        y = float(y)
      except Exception:
        continue
      clean_positions[str(nid)] = {"x": x, "y": y}

    _save_positions(clean_positions)
    return jsonify({"ok": True})
  except Exception as e:
    current_app.logger.error(f"dev_map_save_positions error: {e}")
    return jsonify({"ok": False, "error": "internal"}), 500
