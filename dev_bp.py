# dev_bp.py
# Blueprint для dev-інструментів:
# - /admin/dev-issues — показує проблемні / сірі / "потрібна правка" фічі (static/dev_graph.json)
# - /admin/dev-map    — глобальна карта файлів зі стрілками (static/dev_tree.json)

import json
from flask import Blueprint, current_app, render_template

dev_bp = Blueprint("dev", __name__)


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
  Якщо файл відсутній або битий — повертає простий кореневий вузол.
  """
  try:
    with current_app.open_resource("static/dev_tree.json") as f:
      data = json.load(f)
      if isinstance(data, dict):
        return data
      current_app.logger.warning("dev_tree.json має неочікуваний формат (очікував dict)")
      return {
        "id": "app",
        "label": "app.py",
        "type": "core",
        "status": "ok",
        "children": [],
      }
  except FileNotFoundError:
    current_app.logger.warning("dev_tree.json не знайдено у static/")
    return {
      "id": "app",
      "label": "app.py",
      "type": "core",
      "status": "ok",
      "children": [],
    }
  except Exception as e:
    current_app.logger.error(f"Помилка при читанні dev_tree.json: {e}")
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
  Використовує шаблон templates/dev_map.html і static/dev_tree.json.
  """
  tree = _load_dev_tree()
  return render_template("dev_map.html", tree=tree)
