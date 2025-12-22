def build_cover_url(item) -> str:
    cover_url = getattr(item, "cover_url", None) or ""
    cover_filename = getattr(item, "cover_filename", None) or ""
    if cover_url.startswith("http") or cover_url.startswith("/media/"):
        return cover_url
    if cover_filename:
        return f"/api/market/media/{item.id}/{cover_filename}"
    return ""