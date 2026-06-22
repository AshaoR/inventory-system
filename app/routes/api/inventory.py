from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required
from app import db
from app.models import Material, Inventory, Warehouse, Transaction
import openpyxl

api_inventory_bp = Blueprint("api_inventory", __name__)


@api_inventory_bp.route("/inventory", methods=["GET"])
@login_required
def list_inventory():
    warehouse_type = request.args.get("warehouse_type", "raw")
    search = request.args.get("search", "")
    alert_only = request.args.get("alert_only", "0") == "1"
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return jsonify({"data": [], "warehouse_name": ""})

    query = Inventory.query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(
            db.or_(
                Material.name.contains(search),
                Material.code.contains(search),
                Material.spec.contains(search),
            )
        )

    result = []
    for item in query.order_by(Inventory.updated_at.desc()).all():
        if not item.material or not item.material.is_active:
            continue
        entry = {
            "material_id": item.material.id,
            "code": item.material.code,
            "name": item.material.name,
            "spec": item.material.spec or "",
            "category": item.material.category or "",
            "unit": item.material.unit,
            "quantity": item.quantity or 0,
            "min_stock": item.material.min_stock or 0,
            "is_low": 0 < (item.quantity or 0) < (item.material.min_stock or 0),
            "is_negative": (item.quantity or 0) < 0,
        }
        result.append(entry)

    if alert_only:
        result = [r for r in result if r["is_low"] or r["is_negative"]]

    return jsonify({"data": result, "warehouse_name": wh.name})


@api_inventory_bp.route("/inventory/export")
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

    for wh in warehouses:
        query = Inventory.query.filter_by(warehouse_id=wh.id)
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
            ws.append([
                item.material.code, item.material.name,
                item.material.spec or "", item.material.category or "",
                item.material.unit, item.quantity or 0,
                item.material.min_stock or 0,
            ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    name_suffix = "全仓" if export_all else "_".join(w.name for w in warehouses)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"库存_{name_suffix}.xlsx",
    )


@api_inventory_bp.route("/inventory/materials/<int:material_id>/transactions")
@login_required
def material_transactions(material_id):
    material = db.get_or_404(Material, material_id)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = (
        Transaction.query.filter_by(material_id=material_id)
        .order_by(Transaction.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    items = []
    for t in pagination.items:
        items.append({
            "id": t.id,
            "direction": t.direction,
            "type": t.transaction_type,
            "warehouse_name": t.warehouse.name if t.warehouse else "",
            "quantity": t.quantity,
            "unit_price": float(t.unit_price) if t.unit_price else None,
            "operator": t.operator.display_name if t.operator else "",
            "batch_no": t.batch_no or "",
            "remark": t.remark or "",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "material": {"id": material.id, "code": material.code, "name": material.name},
    })
