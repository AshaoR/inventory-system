from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Warehouse, Material, InitialStock, Transaction, Inventory
from app.services import InitialStockService
import openpyxl

api_initial_stock_bp = Blueprint("api_initial_stock", __name__)


@api_initial_stock_bp.route("/initial-stock", methods=["GET"])
@admin_required
def list_initial_stock():
    warehouse_type = request.args.get("warehouse_type", "raw")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return jsonify({"error": "仓库不存在"}), 404

    query = InitialStock.query
    if search:
        query = query.join(Material).filter(
            db.or_(Material.name.contains(search), Material.code.contains(search))
        )
    pagination = query.order_by(InitialStock.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for r in pagination.items:
        items.append({
            "id": r.id,
            "material_id": r.material_id,
            "material_code": r.material.code if r.material else "",
            "material_name": r.material.name if r.material else "",
            "material_spec": r.material.spec if r.material else "",
            "unit": r.material.unit if r.material else "",
            "warehouse_name": r.warehouse.name if r.warehouse else "",
            "quantity": r.quantity,
            "unit_price": float(r.unit_price) if r.unit_price else None,
            "operator": r.operator.display_name if r.operator else "",
            "remark": r.remark or "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "warehouse_name": wh.name,
    })


@api_initial_stock_bp.route("/initial-stock", methods=["POST"])
@admin_required
def create_initial_stock():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "请求数据格式错误，应为数组"}), 400

    warehouse_type = request.args.get("warehouse_type", "raw")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return jsonify({"error": "仓库不存在"}), 404

    created, skipped = 0, 0
    errors = []
    for i, item in enumerate(data):
        mid = item.get("material_id")
        qty = item.get("quantity", 0)
        if not mid or qty <= 0:
            skipped += 1
            continue
        try:
            InitialStockService.record(
                material_id=mid, warehouse_id=wh.id,
                quantity=qty, operator_id=current_user.id,
                unit_price=item.get("unit_price"),
                remark=item.get("remark") or None,
            )
            created += 1
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    db.session.commit()
    return jsonify({"data": {"created": created, "skipped": skipped, "errors": errors}}), 201


@api_initial_stock_bp.route("/initial-stock/<int:id>", methods=["DELETE"])
@admin_required
def delete_initial_stock(id):
    rec = db.get_or_404(InitialStock, id)
    try:
        Transaction.query.filter_by(initial_stock_id=rec.id).delete()
        inv = Inventory.query.filter_by(
            material_id=rec.material_id, warehouse_id=rec.warehouse_id
        ).first()
        if inv:
            inv.quantity = (inv.quantity or 0) - rec.quantity
        db.session.delete(rec)
        db.session.commit()
        return jsonify({"data": "ok"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@api_initial_stock_bp.route("/initial-stock/export")
@admin_required
def export_excel():
    export_type = request.args.get("type", "records")
    warehouse_type = request.args.get("warehouse_type", "raw")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()

    wb = openpyxl.Workbook()

    if export_type == "materials":
        ws = wb.active
        ws.title = "物料清单"
        ws.append(["物料编号", "名称", "规格", "单位", "期初数量", "单价", "备注"])
        materials = Material.query.filter_by(warehouse_type=warehouse_type, is_active=True).order_by(Material.code).all()
        for m in materials:
            ws.append([m.code, m.name, m.spec or "", m.unit, "", "", ""])
        filename = f"物料清单_{wh.name if wh else ''}.xlsx"
    else:
        ws = wb.active
        ws.title = "录入记录"
        ws.append(["时间", "物料编号", "物料名称", "规格", "单位", "仓库", "数量", "单价", "操作人", "备注"])
        records = InitialStock.query.order_by(InitialStock.created_at.desc()).all()
        for r in records:
            ws.append([
                r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                r.material.code if r.material else "",
                r.material.name if r.material else "",
                r.material.spec or "",
                r.material.unit if r.material else "",
                r.warehouse.name if r.warehouse else "",
                r.quantity,
                str(r.unit_price) if r.unit_price else "",
                r.operator.display_name if r.operator else "",
                r.remark or "",
            ])
        filename = f"录入记录_{wh.name if wh else ''}.xlsx"

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )
