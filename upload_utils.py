import os
import cloudinary
import cloudinary.uploader
import uuid
from werkzeug.utils import secure_filename

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_URL").split("@")[-1],
    api_key=os.getenv("CLOUDINARY_URL").split("//")[1].split(":")[0],
    api_secret=os.getenv("CLOUDINARY_URL").split(":")[2].split("@")[0]
)

def upload_image(file, folder="proofly/market"):
    res = cloudinary.uploader.upload(file, folder=folder)
    return res["secure_url"], res["public_id"]

def upload_stl(file, folder="proofly/stl"):
    res = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="raw",
        public_id=f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    )
    return res["secure_url"], res["public_id"]
