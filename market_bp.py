@market_bp.route("/market/edit/<int:model_id>", methods=["GET", "POST"])
@login_required
def edit_model(model_id):
    model = STLModel.query.filter_by(id=model_id, owner_id=current_user.id).first_or_404()

    categories = ["Фігурки", "Аксесуари", "Іграшки", "Тварини", "Косплей", "Деталі", "Інше"]

    if request.method == "POST":
        model.title = request.form.get("title")
        model.price = request.form.get("price", type=int)
        model.description = request.form.get("description")
        model.tags = request.form.get("tags")
        model.category = request.form.get("category")

        # Видалення фото
        for img in model.images:
            if request.form.get(f"delete_img_{img.id}") == "on":
                db.session.delete(img)

        # Додавання нових фото
        if "new_images" in request.files:
            for file in request.files.getlist("new_images"):
                if file.filename:
                    url = upload_to_cloudinary(file)
                    new_img = ModelImage(model_id=model.id, url=url)
                    db.session.add(new_img)

        # Заміна STL-файлу
        stl = request.files.get("stl")
        if stl and stl.filename:
            new_url = upload_stl(stl)
            model.stl_url = new_url

        db.session.commit()
        return redirect(f"/market/edit/{model.id}")

    return render_template(
        "market/edit_model.html",
        model=model,
        categories=categories
    )
