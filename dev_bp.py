# dev_bp.py
# Blueprint для dev-інструментів:
# - /admin/dev-issues — показує проблемні / сірі / "потрібна правка" фічі (static/dev_graph.json)
# - /admin/dev-map    — глобальна карта файлів зі стрілками (static/dev_tree.json або auto-scan)

import json
from flask import Blueprint, current_app, render_template

dev_bp = Blueprint("dev", __name__)

# 🔥 додаємо імпорт автосканера (НЕ міняючи структуру коду)
try:
    from dev_scan import build_dev_tree
except Exception:
    build_dev_tree = None


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
  return render_template("dev_map.html", tree=tree)
