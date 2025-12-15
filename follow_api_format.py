"""
Демонстрація уніфікованого формату відповідей Follow API

Цей файл показує що обидва endpoints повертають однакову структуру
"""

# ✅ POST /api/follow/3 - УНІФІКОВАНИЙ ФОРМАТ
POST_FOLLOW_RESPONSE = {
    "ok": True,
    "following": True,  # Завжди є
    "followers_count": 5  # Завжди число (не "5", а int)
}

# ✅ DELETE /api/follow/3 - ТОЙ САМИЙ ФОРМАТ
DELETE_FOLLOW_RESPONSE = {
    "ok": True,
    "following": False,  # Завжди є
    "followers_count": 4  # Завжди число
}

# ✅ Cache-Control headers в обох
HEADERS = {
    "Cache-Control": "no-store"
}

# ❌ Помилки - теж уніфіковані
ERROR_UNAUTHORIZED = {
    "ok": False,
    "error": "unauthorized"
}

ERROR_SELF_FOLLOW = {
    "ok": False,
    "error": "self_follow"
}

ERROR_SERVER = {
    "ok": False,
    "error": "server",
    "detail": "Database error"  # Опціонально
}

"""
JavaScript очікує саме такий формат:

if (toggleData.ok) {
  isFollowing = toggleData.following;  // Завжди є
  followers_count = toggleData.followers_count;  // Завжди число
}

Якщо структура відрізняється - UI не оновиться!
"""

# Тест консистентності
def test_response_format():
    """Перевірка що обидва endpoints мають однакові ключі"""
    post_keys = set(POST_FOLLOW_RESPONSE.keys())
    delete_keys = set(DELETE_FOLLOW_RESPONSE.keys())
    
    assert post_keys == delete_keys, "Формати відповідей відрізняються!"
    assert "ok" in post_keys
    assert "following" in post_keys
    assert "followers_count" in post_keys
    
    # Перевірка типів
    assert isinstance(POST_FOLLOW_RESPONSE["following"], bool)
    assert isinstance(POST_FOLLOW_RESPONSE["followers_count"], int)
    
    print("✅ Формати уніфіковані!")

if __name__ == "__main__":
    test_response_format()
