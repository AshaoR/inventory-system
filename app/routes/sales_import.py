from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session as flask_session
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, SalesImportMapping, ImportPendingItem, ImportLog
from app.forms import ImportUploadForm, MappingForm
from app.services import ImportService, InventoryService, TransactionService

sales_import_bp = Blueprint("sales_import", __name__, url_prefix="/import")


@sales_import_bp.route("/sales", methods=["GET", "POST"])
@admin_required
def upload():
    form = ImportUploadForm()
    if form.validate_on_submit():
        f = form.file.data
        file_bytes = f.read()
        file_hash = ImportService.compute_hash(file_bytes)

        existing = ImportService.check_duplicate(file_hash)
        if existing and request.form.get("force_import") != "1":
            flash(f"此文件已于 {existing.created_at.strftime('%Y-%m-%d %H:%M')} 导入过（{existing.row_count} 条记录），请确认是否重复导入", "warning")
            return render_template("import/upload.html", form=form, show_force_button=True)

        try:
            rows = ImportService.parse_excel(BytesIO(file_bytes))
        except Exception as e:
            flash(f"文件解析失败：{str(e)}", "danger")
            return render_template("import/upload.html", form=form)

        if not rows:
            flash("未解析到有效数据，请检查文件格式", "warning")
            return render_template("import/upload.html", form=form)

        mapped, unmapped, seen_names = [], [], set()
        for row in rows:
            name = row["product_name"]
            material = ImportService.auto_match(name)
            if material:
                mapped.append({**row, "material": material})
                if name not in seen_names:
                    ImportService.save_mapping(name, material.id)
                    seen_names.add(name)
            else:
                unmapped.append(row)
        db.session.commit()

        flask_session["import_preview"] = {
            "file_hash": file_hash, "file_name": f.filename,
            "mapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price"), r["material"].id) for r in mapped],
            "unmapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price")) for r in unmapped],
        }
        return render_template("import/preview.html", mapped=mapped, unmapped=unmapped, mapped_count=len(mapped), unmapped_count=len(unmapped), file_hash=file_hash, file_name=f.filename)

    return render_template("import/upload.html", form=form)


@sales_import_bp.route("/sales/confirm", methods=["POST"])
@admin_required
def confirm():
    preview_data = flask_session.pop("import_preview", None)
    if not preview_data:
        flash("预览数据已过期，请重新上传", "danger")
        return redirect(url_for("sales_import.upload"))

    file_hash, file_name = preview_data["file_hash"], preview_data["file_name"]
    mapped, unmapped = preview_data["mapped"], preview_data["unmapped"]

    warehouse = Warehouse.query.filter_by(code="finished").first()
    if not warehouse:
        flash("成品仓未配置", "danger")
        return redirect(url_for("sales_import.upload"))

    try:
        if ImportService.check_duplicate(file_hash):
            flash("此文件已被其他用户导入", "danger")
            return redirect(url_for("sales_import.upload"))

        batch_no = ImportService.generate_batch_no()
        log = ImportLog(file_hash=file_hash, file_name=file_name, row_count=len(mapped) + len(unmapped), operator_id=current_user.id, batch_no=batch_no)
        db.session.add(log)
        db.session.flush()

        for order_no, product_name, quantity, unit_price, material_id in mapped:
            InventoryService.deduct_stock(material_id, warehouse.id, quantity)
            TransactionService.create(direction="out", transaction_type="销售出库", material_id=material_id, warehouse_id=warehouse.id, quantity=quantity, unit_price=unit_price, operator_id=current_user.id, batch_no=batch_no, remark=f"外部导入（{file_name}）")

        for order_no, product_name, quantity, unit_price in unmapped:
            db.session.add(ImportPendingItem(import_log_id=log.id, external_name=product_name, quantity=quantity, unit_price=unit_price, order_no=order_no or "", status="pending"))

        db.session.commit()
        flash(f"导入完成！已导入 {len(mapped)} 条" + (f"，未匹配 {len(unmapped)} 条待处理" if unmapped else ""), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"导入失败：{str(e)}", "danger")
    return redirect(url_for("sales_import.import_history"))


@sales_import_bp.route("/sales/history")
@admin_required
def import_history():
    page = request.args.get("page", 1, type=int)
    logs = ImportLog.query.order_by(ImportLog.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("import/history.html", pagination=logs)


@sales_import_bp.route("/mappings", methods=["GET", "POST"])
@admin_required
def mappings():
    form = MappingForm()
    materials = Material.query.filter_by(is_active=True).order_by(Material.code).all()
    form.material_id.choices = [(m.id, f"[{m.code}] {m.name}") for m in materials]

    if form.validate_on_submit():
        ImportService.save_mapping(form.external_name.data, form.material_id.data)
        db.session.commit()
        flash("映射已保存", "success")
        return redirect(url_for("sales_import.mappings"))

    page = request.args.get("page", 1, type=int)
    mappings_list = SalesImportMapping.query.order_by(SalesImportMapping.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("import/mappings.html", form=form, pagination=mappings_list, materials=materials)


@sales_import_bp.route("/mappings/delete/<int:id>", methods=["POST"])
@admin_required
def delete_mapping(id):
    mapping = db.get_or_404(SalesImportMapping, id)
    db.session.delete(mapping)
    db.session.commit()
    flash("映射已删除", "success")
    return redirect(url_for("sales_import.mappings"))


@sales_import_bp.route("/pending")
@admin_required
def pending_items():
    page = request.args.get("page", 1, type=int)
    items = ImportPendingItem.query.filter_by(status="pending").order_by(ImportPendingItem.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    materials = Material.query.filter_by(is_active=True).order_by(Material.code).all()
    return render_template("import/pending.html", pagination=items, materials=materials)


@sales_import_bp.route("/pending/bulk-resolve", methods=["POST"])
@admin_required
def bulk_resolve():
    material_id = request.form.get("material_id", type=int)
    pending_ids = request.form.getlist("pending_ids", type=int)
    if not material_id or not pending_ids:
        flash("请选择物料和待处理记录", "danger")
        return redirect(url_for("sales_import.pending_items"))
    count = ImportService.bulk_resolve_pending(pending_ids, material_id, current_user.id)
    flash(f"已处理 {count} 条待处理记录", "success")
    return redirect(url_for("sales_import.pending_items"))


@sales_import_bp.route("/api/materials-by-warehouse")
@login_required
def api_materials_by_warehouse():
    warehouse_type = request.args.get("warehouse_type", "finished")
    materials = Material.query.filter_by(warehouse_type=warehouse_type, is_active=True).order_by(Material.code).all()
    return jsonify([m.to_dict() for m in materials])
