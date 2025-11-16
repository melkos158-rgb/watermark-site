# dev_scan.py
# Автосканер структури проєкту Proofly для Dev Map.
#
# Робить:
#  - проходить по всіх файлах від root_path
#  - збирає .py, .js, .css, .html, .json, .sql
#  - аналізує імпорти / інклюди:
#       * Python: import / from ... import ...
#       * JS: import ... from "./..." / require("...")
#       * Jinja: {% include "..." %}, {% extends "..." %}
#       * HTML: посилання на static/js/*.js та static/css/*.css
#  - будує дерево з коренем app.py
#  - всі файли, до яких ніхто не підключається, кидає в "orphans"
#
# Повертає дерево у форматі, який чекає dev_bp/dev_map:
#  {
#    "id": "app_py",
#    "label": "app.py",
#    "path": "app.py",
#    "type": "py",
#    "status": "ok",
#    "feature": "",
#    "notes": "",
#    "children": [ ... ]
#  }

from __future__ import annotations

import os
import json
import re
from typing import Dict, List, Set, Tuple, Optional


# ---- утиліти ---------------------------------------------------------------

def _norm_path(path: str) -> str:
  """Нормалізує шлях у вигляді з / (щоб однаково працювало на всіх ОС)."""
  return os.path.normpath(path).replace(os.sep, "/")


def _make_id(path: str) -> str:
  """
  Стабільний id для ноди: шлях з /, де / та . замінені.
  Приклад: 'static/js/dev_map.js' -> 'static_js_dev_map_js'
  """
  p = _norm_path(path)
  return p.replace("/", "_").replace(".", "_")


def _guess_type(path: str) -> str:
  ext = os.path.splitext(path)[1].lower()
  if ext == ".py":
    return "py"
  if ext == ".js":
    return "js"
  if ext == ".css":
    return "css"
  if ext in (".html", ".htm"):
    return "html"
  if ext == ".json":
    return "json"
  if ext in (".sql",):
    return "sql"
  if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
    return "img"
  return "other"


def _read_text(path: str) -> str:
  try:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
      return f.read()
  except Exception:
    return ""


# ---- сканування файлової системи ------------------------------------------

def _collect_files(root_path: str) -> List[str]:
  """
  Збирає всі файли проєкту, які нам цікаві.
  """
  exts = {".py", ".js", ".css", ".html", ".htm", ".json", ".sql"}
  collected: List[str] = []

  for dirpath, dirnames, filenames in os.walk(root_path):
    # пропускаємо приховані папки типу .git, __pycache__ і т.п.
    base = os.path.basename(dirpath)
    if base.startswith(".") or base in ("__pycache__", "venv", ".venv"):
      continue

    for fname in filenames:
      _, ext = os.path.splitext(fname)
      if ext.lower() in exts:
        full = os.path.join(dirpath, fname)
        collected.append(_norm_path(os.path.relpath(full, root_path)))

  return collected


# ---- парсери залежностей ---------------------------------------------------

# прості regex-и, не ідеально, але ок для dev-карти
RE_PY_IMPORT = re.compile(r"^\s*import\s+([a-zA-Z0-9_.,\s]+)", re.MULTILINE)
RE_PY_FROM   = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+([a-zA-Z0-9_.*, \t]+)", re.MULTILINE)

RE_JS_IMPORT = re.compile(r"import\s+.+?\s+from\s+['\"](.+?)['\"]", re.MULTILINE)
RE_JS_REQ    = re.compile(r"require\(\s*['\"](.+?)['\"]\s*\)")

RE_JINJA_INC = re.compile(r"\{%\s*(?:include|extends)\s+\"([^\"]+)\"\s*%}")
RE_HTML_STAT = re.compile(r"(?:href|src)\s*=\s*['\"][^'\"]*static/([^'\"]+)['\"]")


def _resolve_js_relative(base_path: str, import_str: str) -> Optional[str]:
  """
  Перетворює відносний імпорт ('./foo', '../bar/baz') у нормальний шлях
  всередині проєкту (static/js/... або market/js/... і т.п.).
  Повертає відносний шлях від root або None.
  """
  # зовнішні/URL не чіпаємо
  if "://" in import_str or import_str.startswith(("/", "http", "https")):
    return None

  # якщо немає ./ або ../ — скоріше за все це бібліотека, пропускаємо
  if not import_str.startswith("."):
    return None

  base_dir = os.path.dirname(base_path)
  candidate = os.path.normpath(os.path.join(base_dir, import_str))

  # якщо немає розширення — пробуємо .js
  if not os.path.splitext(candidate)[1]:
    candidate_js = candidate + ".js"
  else:
    candidate_js = candidate

  return _norm_path(candidate_js)


def _parse_dependencies_for_file(root_path: str,
                                 rel_path: str,
                                 all_files: Set[str]) -> Set[str]:
  """
  Повертає множину відносних шляхів файлів, від яких залежить rel_path.
  """
  full_path = os.path.join(root_path, rel_path)
  content = _read_text(full_path)
  deps: Set[str] = set()

  ext = os.path.splitext(rel_path)[1].lower()

  # --- Python імпорти ------------------------------------------------------
  if ext == ".py":
    # мапа за basename (без .py)
    by_name: Dict[str, List[str]] = {}
    for f in all_files:
      if f.endswith(".py"):
        name = os.path.splitext(os.path.basename(f))[0]
        by_name.setdefault(name, []).append(f)

    def _add_module(mod: str) -> None:
      short = mod.split(".")[-1]
      for cand in by_name.get(short, []):
        deps.add(cand)

    for match in RE_PY_IMPORT.findall(content):
      parts = [p.strip() for p in match.split(",") if p.strip()]
      for p in parts:
        # import a.b.c -> беремо останню частину
        _add_module(p.split()[-1])

    for mod, _names in RE_PY_FROM.findall(content):
      _add_module(mod)

  # --- JS імпорти ----------------------------------------------------------
  elif ext == ".js":
    all_files_set = set(all_files)
    for imp in RE_JS_IMPORT.findall(content):
      resolved = _resolve_js_relative(rel_path, imp)
      if resolved and resolved in all_files_set:
        deps.add(resolved)
    for imp in RE_JS_REQ.findall(content):
      resolved = _resolve_js_relative(rel_path, imp)
      if resolved and resolved in all_files_set:
        deps.add(resolved)

  # --- Jinja шаблони / HTML ------------------------------------------------
  if ext in (".html", ".htm"):
    # {% include "market/item.html" %}
    for tpl in RE_JINJA_INC.findall(content):
      tpl_path = _norm_path(os.path.join("templates", tpl))
      if tpl_path in all_files:
        deps.add(tpl_path)

    # static/js/... або static/css/...
    for static_rel in RE_HTML_STAT.findall(content):
      candidate = _norm_path(os.path.join("static", static_rel))
      if candidate in all_files:
        deps.add(candidate)

  return deps


# ---- побудова дерева -------------------------------------------------------

def _make_node_dict(path: str) -> Dict:
  return {
    "id": _make_id(path),
    "label": os.path.basename(path),
    "path": path,
    "type": _guess_type(path),
    "status": "ok",
    "feature": "",
    "notes": "",
    "children": []
  }


def _apply_overrides(root_path: str,
                     nodes_by_path: Dict[str, Dict]) -> None:
  """
  Підтягуємо налаштування з static/dev_overrides.json, якщо він є.
  Ключі у overrides можуть бути або повним шляхом, або basename.
  """
  overrides_path = os.path.join(root_path, "static", "dev_overrides.json")
  try:
    with open(overrides_path, "r", encoding="utf-8") as f:
      overrides = json.load(f)
  except Exception:
    overrides = {}

  if not isinstance(overrides, dict):
    return

  for path, node in nodes_by_path.items():
    norm = _norm_path(path)
    base = os.path.basename(path)
    for key, cfg in overrides.items():
      if key == norm or key == base:
        if not isinstance(cfg, dict):
          continue
        for field in ("type", "status", "feature", "notes", "label"):
          if field in cfg:
            node[field] = cfg[field]


def build_dev_tree(root_path: str) -> Dict:
  """
  Головна функція, яку викликає dev_bp.
  root_path — корінь проєкту (де лежить app.py).

  Повертає дерево для Dev Map.
  """
  root_path = os.path.abspath(root_path)

  # 1) збираємо всі файли
  files = _collect_files(root_path)
  all_files_set = set(files)

  if not files:
    # fallback — мінімальне дерево
    return {
      "id": "app",
      "label": "app.py",
      "path": "app.py",
      "type": "py",
      "status": "ok",
      "feature": "",
      "notes": "dev_scan: файлів не знайдено",
      "children": []
    }

  # 2) створюємо ноди
  nodes_by_path: Dict[str, Dict] = {f: _make_node_dict(f) for f in files}

  # 3) парсимо залежності
  deps: Dict[str, Set[str]] = {}
  for path in files:
    deps[path] = _parse_dependencies_for_file(root_path, path, all_files_set)

  # 4) підтягуємо overrides
  _apply_overrides(root_path, nodes_by_path)

  # 5) визначаємо корінь (app.py), якщо нема — створюємо штучний root
  app_rel = "app.py"
  app_rel_norm = _norm_path(app_rel)

  if app_rel_norm in nodes_by_path:
    root_path_key = app_rel_norm
    root_node = nodes_by_path[root_path_key]
  else:
    root_path_key = "__root__"
    root_node = {
      "id": "root",
      "label": "Project root",
      "path": "",
      "type": "group",
      "status": "ok",
      "feature": "Root",
      "notes": "",
      "children": []
    }

  # 6) будуємо дерево: DFS від root, інші — в 'orphans'
  visited: Set[str] = set()

  def attach_children(path: str, node: Dict):
    if path in visited:
      return
    visited.add(path)
    for dep in sorted(deps.get(path, [])):
      child_node = nodes_by_path.get(dep)
      if not child_node:
        continue
      node.setdefault("children", []).append(child_node)
      attach_children(dep, child_node)

  if root_path_key in nodes_by_path:
    attach_children(root_path_key, root_node)

  # 7) додаємо "orphans" (файли, до яких ніхто не підключається)
  orphan_children: List[Dict] = []
  for path, node in nodes_by_path.items():
    if path == root_path_key:
      continue
    if path not in visited:
      # позначаємо як сиріт
      if node.get("status") == "ok":
        node["status"] = "orphan"
      orphan_children.append(node)

  if orphan_children:
    orphans_node = {
      "id": "orphans",
      "label": "Orphans (не підключені файли)",
      "path": "",
      "type": "group",
      "status": "orphan",
      "feature": "Код, який ніхто не імпортує",
      "notes": "Перевір, чи ці файли потрібні, чи можна видалити / підключити.",
      "children": orphan_children
    }
    root_node.setdefault("children", []).append(orphans_node)

  return root_node
