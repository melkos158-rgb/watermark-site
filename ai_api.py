import os

from flask import Blueprint, current_app, jsonify, request

ai_api = Blueprint("ai_api", __name__, url_prefix="/api/ai")

# ✅ Підключення OpenAI (якщо є ключ)
_AI_READY = False
try:
    import openai

    _OPENAI_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
    if _OPENAI_KEY:
        openai.api_key = _OPENAI_KEY
        _AI_READY = True
except Exception as e:  # noqa: F841
    _AI_READY = False


def _fallback_text(kind: str, prompt: str, target_lang: str | None = None) -> str:
    """
    Простий "заглушка"-варіант, якщо немає ключа OpenAI або сталася помилка.
    Щоб фронт ніколи не падав.
    """
    prompt = (prompt or "").strip()
    if kind == "name":
        base = prompt[:80] or "STL модель"
        return f"{base} — Proofly Edition"
    if kind == "description":
        base = prompt or "3D модель для друку на FDM/FFF принтері."
        return (
            base
            + "\n\n"
            "Особливості:\n"
            "• Оптимізовано для PLA\n"
            "• Рекомендована висота шару: 0.2 мм\n"
            "• Мінімум підтримок або без них\n"
        )
    if kind == "tags":
        base = prompt.lower()
        tags = ["3d print", "stl", "model", "proofly"]
        if "dragon" in base:
            tags += ["dragon", "flexi", "fantasy"]
        if "stand" in base or "holder" in base:
            tags += ["stand", "holder"]
        return ", ".join(dict.fromkeys(tags))  # унікальні
    if kind == "translate":
        lang = target_lang or "en"
        return f"[{lang}] {prompt}"
    return prompt or ""


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Виклик OpenAI ChatCompletion (якщо доступний).
    Якщо щось не так — повертає fallback-текст.
    """
    if not _AI_READY:
        return _fallback_text("description", user_prompt)

    try:
        # Якщо ти використовуєш нову бібліотеку openai з client = OpenAI(),
        # можеш адаптувати під свій варіант.
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        return text
    except Exception as e:
        current_app.logger.exception("AI call failed: %s", e)
        return _fallback_text("description", user_prompt)


@ai_api.route("/generate_name", methods=["POST"])
def generate_name():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    if _AI_READY:
        system = (
            "Ти допомагаєш автору STL моделей вигадувати короткі, "
            "чіпкі назви для маркетплейсу. До 60 символів, без зайвої води."
        )
        result = _call_llm(system, prompt)
    else:
        result = _fallback_text("name", prompt)

    return jsonify({"result": result})


@ai_api.route("/generate_description", methods=["POST"])
def generate_description():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    if _AI_READY:
        system = (
            "Ти копірайтер для STL-маркету Proofly. "
            "Створюй детальний, але структурований опис STL-моделі: "
            "короткий вступ, особливості, параметри друку (матеріал, висота шару, підтримки), "
            "рекомендований масштаб. Пиши дружньо, без HTML."
        )
        result = _call_llm(system, prompt)
    else:
        result = _fallback_text("description", prompt)

    return jsonify({"result": result})


@ai_api.route("/generate_tags", methods=["POST"])
def generate_tags():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    if _AI_READY:
        system = (
            "Ти генеруєш теги для STL-моделі 3D-друку. "
            "Поверни список тегів через кому, без нумерації, без хештегів. "
            "Використовуй англійські ключові слова, придатні для пошуку на маркетплейсі."
        )
        raw = _call_llm(system, prompt)
        # На всяк — приберемо можливі переноси рядків
        result = ", ".join(
            [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
        )
    else:
        result = _fallback_text("tags", prompt)

    return jsonify({"result": result})


@ai_api.route("/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    target_lang = (data.get("target_lang") or "en").lower()

    if not text:
        return jsonify({"error": "text is required"}), 400

    if _AI_READY:
        system = (
            "Ти професійний перекладач описів для STL-маркету. "
            "Переклади текст на вказану мову, зберігай зміст, стиль і технічні терміни. "
            "Не додавай пояснень, тільки переклад."
        )
        user_prompt = f"Мова призначення: {target_lang}\n\nТекст:\n{text}"
        result = _call_llm(system, user_prompt)
    else:
        result = _fallback_text("translate", text, target_lang=target_lang)

    return jsonify({"result": result})
