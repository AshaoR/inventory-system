import io
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required
from app import db
from app.models import Material, Inventory, Warehouse, Transaction
import openpyxl

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@inventory_bp.route("/")
@login_required
def index():
    warehouse_type = request.args.get("warehouse_type", "raw")
    search = request.args.get("search", "")
    alert_only = request.args.get("alert_only", "0") == "1"
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return render_template("inventory/list.html", items=[], warehouse_type=warehouse_type, search=search, alert_only=alert_only, warehouse_name="")

    query = Inventory.query.filter_by(warehouse_id=wh.id).join(Material).filter(Material.is_active == True)
    if search:
        query = query.filter(db.or_(Material.name.contains(search), Material.code.contains(search), Material.spec.contains(search)))
    if alert_only:
        query = query.filter(db.or_(
            db.and_(Inventory.quantity > 0, Inventory.quantity < Material.min_stock),
            Inventory.quantity < 0,
        ))

    result = []
    for item in query.order_by(Inventory.updated_at.desc()).all():
        result.append({
            "material": item.material,
            "quantity": item.quantity or 0,
            "min_stock": item.material.min_stock or 0,
            "is_low": 0 < item.quantity < (item.material.min_stock or 0),
            "is_negative": (item.quantity or 0) < 0,
        })

    return render_template("inventory/list.html", items=result, warehouse_type=warehouse_type, warehouse_name=wh.name, search=search, alert_only=alert_only)


@inventory_bp.route("/export")
@login_required
def export_excel():
    export_all = request.args.get("all", "0") == "1"
    warehouse_type = request.args.get("warehouse_type", "")

    wb = openpyxl.Workbook()
    first_sheet = True

    if export_all or not warehouse_type:
        warehouses = Warehouse.query.order_by(Warehouse.id).all()
    else:
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        warehouses = [wh] if wh else []

    if not warehouses:
        flash("仓库不存在", "danger")
        return redirect(url_for("inventory.index"))

    for wh in warehouses:
        query = Inventory.query.filter_by(warehouse_id=wh.id)
        if not export_all and request.args.get("search", ""):
            query = query.join(Material).filter(db.or_(Material.name.contains(request.args.get("search", "")), Material.code.contains(request.args.get("search", ""))))

        if first_sheet:
            ws = wb.active
            ws.title = wh.name
            first_sheet = False
        else:
            ws = wb.create_sheet(title=wh.name)

        ws.append(["物料编号", "名称", "规格", "分类", "单位", "当前库存", "最低预警"])

        for item in query.join(Material).order_by(Material.code).all():
            if not item.material or not item.material.is_active:
                continue
            ws.append([item.material.code, item.material.name, item.material.spec or "", item.material.category or "", item.material.unit, item.quantity or 0, item.material.min_stock or 0])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    name_suffix = "全仓" if export_all else "_".join(w.name for w in warehouses)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"库存_{name_suffix}.xlsx")


@inventory_bp.route("/material/<int:material_id>/transactions")
@login_required
def material_transactions(material_id):
    material = db.get_or_404(Material, material_id)
    page = request.args.get("page", 1, type=int)
    pagination = (
        Transaction.query.filter_by(material_id=material_id)
        .order_by(Transaction.created_at.desc())
        .paginate(page=page, per_page=50, error_out=False)
    )
    return render_template("inventory/material_transactions.html", material=material, pagination=pagination)
