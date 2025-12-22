def upload_video(file, folder="proofly/video"):
    import cloudinary
    import uuid
    from werkzeug.utils import secure_filename
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="video",
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    )
    return res.get("secure_url"), res.get("public_id")
# ===============================================================
#  Завантаження ВІДЕО
# ===============================================================
def upload_video_to_cloudinary(file, folder="proofly/videos"):
    """
    Завантажує відео (mp4/webm/mov) у Cloudinary
    :param file: FileStorage із Flask request.files
    :param folder: Каталог у Cloudinary
    :return: secure_url
    """
    import os
    import cloudinary
    import cloudinary.uploader
    from werkzeug.utils import secure_filename
    import uuid
    cloud_url = os.getenv("CLOUDINARY_URL", "")
    if not cloud_url:
        raise RuntimeError("CLOUDINARY_URL не знайдено в .env — додай його у форматі cloudinary://<api_key>:<api_secret>@<cloud_name>")
    try:
        cloud_name = cloud_url.split("@")[-1]
        api_key = cloud_url.split("//")[1].split(":")[0]
        api_secret = cloud_url.split(":")[2].split("@")[0]
    except Exception as e:
        raise RuntimeError(f"Невірний формат CLOUDINARY_URL: {cloud_url}") from e
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret
    )
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="video",
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}",
        overwrite=True
    )
    return res.get("secure_url")



# ===============================================================
#  Завантаження ЗОБРАЖЕНЬ
# ===============================================================
def upload_image(file, folder="proofly/market"):
    """
    Завантажує зображення (jpg/png/webp) у Cloudinary
    :param file: FileStorage із Flask request.files
    :param folder: Каталог у Cloudinary
    :return: (secure_url, public_id)
    """
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}",
        resource_type="image"
    )
    return res.get("secure_url"), res.get("public_id")

# ===============================================================
#  Завантаження STL / RAW файлів
# ===============================================================
def upload_stl(file, folder="proofly/stl"):
    """
    Завантажує STL-файли (або будь-які інші "raw" файли)
    :param file: FileStorage
    :param folder: Каталог у Cloudinary
    :return: (secure_url, public_id)
    """
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="raw",
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    )
    return res.get("secure_url"), res.get("public_id")

# ===============================================================
#  Завантаження ZIP / архівів
# ===============================================================
def upload_zip(file, folder="proofly/zip"):
    """
    Завантажує архіви (.zip, .rar, .7z)
    :param file: FileStorage
    :param folder: Каталог у Cloudinary
    :return: (secure_url, public_id)
    """
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="raw",
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    )
    return res.get("secure_url"), res.get("public_id")

# ===============================================================
#  Видалення з Cloudinary (за public_id)
# ===============================================================
def delete_file(public_id):
    """
    Видаляє файл із Cloudinary
    :param public_id: Ідентифікатор файлу (res['public_id'])
    :return: результат операції
    """
    try:
        result = cloudinary.uploader.destroy(public_id, invalidate=True)
        return result
    except Exception as e:
        print(f"[delete_file] Error: {e}")
        return None

# ===============================================================
#  Допоміжна функція для перевірки дозволених форматів
# ===============================================================
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
ALLOWED_STL_EXT = {"stl", "obj"}
ALLOWED_ZIP_EXT = {"zip", "rar", "7z"}

def allowed_file(filename, kind="image"):
    """
    Перевіряє чи файл має дозволене розширення
    :param filename: ім'я файлу
    :param kind: image|stl|zip
    """
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    if kind == "image":
        return ext in ALLOWED_IMAGE_EXT
    if kind == "stl":
        return ext in ALLOWED_STL_EXT
    if kind == "zip":
        return ext in ALLOWED_ZIP_EXT
    return False
