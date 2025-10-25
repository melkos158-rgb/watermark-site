import os

# === БАЗОВІ ШЛЯХИ ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# === КОНФІГУРАЦІЯ FLASK ===
class Config:
    # Безпека
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # === БАЗА ДАНИХ ===
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}"
    ).replace("postgres://", "postgresql://")  # фікс для Railway
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # === МЕДІА ФАЙЛИ ===
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # де фізично зберігаються файли
    MEDIA_URL = '/media/'                        # URL, по якому Flask віддає файли

    # === СТАТИЧНІ ФАЙЛИ (якщо треба вручну вказати) ===
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    TEMPLATES_FOLDER = os.path.join(BASE_DIR, 'templates')

    # === РІЗНЕ ===
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # обмеження розміру файлів (50 МБ)
    UPLOAD_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.stl', '.obj', '.zip']

    # === Cloudinary / Supabase / S3 (опціонально, якщо підключатимеш) ===
    CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", None)
    SUPABASE_URL = os.getenv("SUPABASE_URL", None)
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", None)

