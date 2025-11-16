"""
dev_scan.py
===========

Утиліта для побудови дерева файлів для Dev Map.

Функції:
- build_dev_tree(base_dir: str, overrides_path: str | None = None) -> dict
    Повертає дерево у форматі, сумісному з dev_map.js:
    {
      "id": "app",
      "label": "app.py",
      "type": "core",
      "status": "ok",
      "children": [ ... ]
    }

- load_overrides(path) -> dict
    Читає static/dev_overrides.json (якщо є) і повертає
    словник: rel_path -> {status, feature, notes, ...}
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional


IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
}


def load_overrides(path: str) -> Dict[str, Dict[str, Any]]:
    """
    Читає JSON з перевизначеннями статусів/фіч/нотаток.
    Формат файлу (static/dev_overrides.json):

    {
      "templates/market/item.html": {
        "status": "fix",
        "feature": "STL Market — сторінка моделі",
        "notes": "viewer лагає на мобілці"
      },
      "ai/ai_api.py": {
        "status": "error",
        "feature": "AI Tools",
        "notes": "500 error при завантаженні"
      }
    }

    :param path: абсолютний шлях до JSON
    :return: dict { rel_path: overrides_dict }
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # ключі — це шляхи від кореня проєкту (relpath)
            return {str(k): (v or {}) for k, v in data.items()}
        return {}
    except FileNotFoundError:
        return {}
    except Exception:
        # при помилці читаємо пустий словник, щоб не ламати dev map
        return {}


def guess_type(rel_path: str) -> str:
    """
    Визначає тип вузла за шляхом.
    """
    rel = rel_path.replace("\\", "/")

    if rel.startswith("templates/"):
        return "template"

    if rel.startswith("static/"):
        if "/js/" in rel or rel.endswith(".js"):
            return "js"
        if "/css/" in rel or rel.endswith(".css"):
            return "css"
        return "static"

    if rel.endswith(".py"):
        return "module"

    return "file"


def guess_feature(rel_path: str) -> Optional[str]:
    """
    Груба спроба віднести файл до якоїсь фічі.
    Це тільки для зручності у правій панелі, нічого критичного.
    """
    rel = rel_path.replace("\\", "/").lower()

    if "market" in rel:
        return "STL Market"
    if "/ai_" in rel or "/ai/" in rel:
        return "AI Tools"
    if "parametric" in rel:
        return "Parametric Generator"
    if "gcode" in rel:
        return "G-code Viewer"
    if "printer" in rel:
        return "Printer Profiles"
    if "license" in rel:
        return "License Manager"
    if "notify" in rel or "notification" in rel:
        return "Notifications"
    if "stats" in rel or "analytics" in rel:
        return "Stats / Analytics"
    if "profile" in rel:
        return "User Profile"
    if "auth" in rel or "login" in rel or "register" in rel:
        return "Auth / Login"
    if "core_pages" in rel or "index.html" in rel:
        return "Core pages"

    return None


def default_status_for(rel_path: str) -> str:
    """
    Базовий статус, якщо немає оверрайдів.
    Можна додати прості хардкод-правила.
    """
    name = os.path.basename(rel_path).lower()
    if "old_" in name or "test" in name:
        return "orphan"
    return "ok"


def build_dev_tree(base_dir: str, overrides_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Складає дерево файлів проекту.

    :param base_dir: корінь проєкту (current_app.root_path)
    :param overrides_path: шлях до static/dev_overrides.json (або None)
    :return: dict — кореневий вузол дерева
    """
    base_dir = os.path.abspath(base_dir)

    if overrides_path is None:
        overrides_path = os.path.join(base_dir, "static", "dev_overrides.json")

    overrides = load_overrides(overrides_path)

    # Кореневий вузол — app.py, якщо існує, інакше "Project root"
    app_py = os.path.join(base_dir, "app.py")
    root_label = "app.py" if os.path.exists(app_py) else "Project root"

    root: Dict[str, Any] = {
        "id": "app",
        "label": root_label,
        "type": "core",
        "status": "ok",
        "children": []
    }

    # Групи: python / templates / js / css / static / other
    groups: Dict[str, Dict[str, Any]] = {}

    def get_group(key: str, label: str, status: str = "ok") -> Dict[str, Any]:
        if key not in groups:
            groups[key] = {
                "id": f"group_{key}",
                "label": label,
                "type": "group",
                "status": status,
                "children": []
            }
        return groups[key]

    # Проходимо по всіх файлах
    for dirpath, dirnames, filenames in os.walk(base_dir):
        # фільтруємо службові папки
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".")
        ]

        for name in filenames:
            full_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")

            # ігноруємо сам dev_tree.json / dev_graph.json / overrides
            if rel_path.startswith("static/dev_tree.json") or rel_path.startswith("static/dev_graph.json") \
               or rel_path.startswith("static/dev_overrides.json"):
                continue

            # ігноруємо приховані файли
            if os.path.basename(rel_path).startswith("."):
                continue

            # тип
            node_type = guess_type(rel_path)

            # оверрайди
            ov = overrides.get(rel_path, {})
            status = ov.get("status") or default_status_for(rel_path)
            feature = ov.get("feature") or guess_feature(rel_path)
            notes = ov.get("notes")

            node: Dict[str, Any] = {
                "id": rel_path.replace("/", "_"),
                "label": rel_path,
                "type": node_type,
                "status": status
            }

            if feature:
                node["feature"] = feature
            if notes:
                node["notes"] = notes

            # Визначаємо групу
            if node_type == "template":
                grp = get_group("templates", "Templates")
            elif node_type == "js":
                grp = get_group("js", "JavaScript")
            elif node_type == "css":
                grp = get_group("css", "CSS")
            elif node_type == "module":
                grp = get_group("python", "Python modules")
            elif node_type == "static":
                grp = get_group("static", "Static files")
            else:
                grp = get_group("other", "Other files")

            grp["children"].append(node)

    # додаємо всі групи кореню
    root["children"] = list(groups.values())
    return root


# Для ручного запуску з терміналу:
if __name__ == "__main__":
    here = os.path.abspath(os.path.dirname(__file__))
    tree = build_dev_tree(here)
    print(json.dumps(tree, ensure_ascii=False, indent=2))

