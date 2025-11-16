# dev_bp.py
# Blueprint для dev-інструментів:
# - сторінка /admin/dev-issues показує всі проблемні / сірі / "потрібна правка" фічі
#   на основі static/dev_graph.json

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
