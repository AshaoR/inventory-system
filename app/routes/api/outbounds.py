from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Transaction
from app.services import OutboundService, InventoryService
import openpyxl

api_outbounds_bp = Blueprint("api_outbounds", __name__)


@api_outbounds_bp.route("/outbounds", methods=["GET"])
@admin_required
def list_outbounds():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    batch_no = request.args.get("batch_no", "")
    query = Transaction.query.filter_by(direction="out")
    if warehouse_type in ("raw", "semi", "finished"):
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        if wh:
            query = query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(
            db.or_(Material.name.contains(search), Material.code.contains(search))
        )
    if batch_no:
        query = query.filter(Transaction.batch_no.contains(batch_no))
    pagination = query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for t in pagination.items:
        items.append({
            "id": t.id,
            "type": t.transaction_type,
            "material_code": t.material.code if t.material else "",
            "material_name": t.material.name if t.material else "",
            "material_spec": t.material.spec if t.material else "",
            "warehouse_name": t.warehouse.name if t.warehouse else "",
            "quantity": t.quantity,
            "unit_price": float(t.unit_price) if t.unit_price else None,
            "operator": t.operator.display_name if t.operator else "",
            "batch_no": t.batch_no or "",
            "is_forced": t.is_forced,
            "remark": t.remark or "",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
    })


@api_outbounds_bp.route("/outbounds", methods=["POST"])
@admin_required
def create_outbounds():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "请求数据格式错误，应为数组"}), 400

    warehouse_type = data[0].get("warehouse_type", "finished") if data else "finished"
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return jsonify({"error": "仓库不存在"}), 404

    is_forced = request.args.get("is_forced") == "true"
    created = 0
    errors = []
    for i, item in enumerate(data):
        mid = item.get("material_id")
        qty = item.get("quantity", 0)
        if not mid or qty <= 0:
            errors.append({"index": i, "error": "无效的物料或数量"})
            continue
        try:
            OutboundService.create(
                material_id=mid, warehouse_id=wh.id,
                quantity=qty, operator_id=current_user.id,
                transaction_type=item.get("type", "生产领用"),
                is_forced=is_forced,
                forced_reason="批量出库" if is_forced else None,
                remark=item.get("remark") or None,
            )
            created += 1
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    db.session.commit()
    return jsonify({"data": {"created": created, "errors": errors}}), 201


@api_outbounds_bp.route("/outbounds/check-stock")
@admin_required
def check_stock():
    material_id = request.args.get("material_id", type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    quantity = request.args.get("quantity", type=float)
    if not all([material_id, warehouse_id, quantity]):
        return jsonify({"data": {"sufficient": False, "current_stock": 0}})
    current_stock = InventoryService.get_quantity(material_id, warehouse_id)
    return jsonify({"data": {"sufficient": current_stock >= quantity, "current_stock": current_stock}})


@api_outbounds_bp.route("/outbounds/<int:id>")
@admin_required
def detail(id):
    t = db.get_or_404(Transaction, id)
    return jsonify({
        "data": {
            "id": t.id,
            "type": t.transaction_type,
            "direction": t.direction,
            "material_id": t.material_id,
            "material_code": t.material.code if t.material else "",
            "material_name": t.material.name if t.material else "",
            "material_spec": t.material.spec if t.material else "",
            "warehouse_name": t.warehouse.name if t.warehouse else "",
            "quantity": t.quantity,
            "unit_price": float(t.unit_price) if t.unit_price else None,
            "operator": t.operator.display_name if t.operator else "",
            "batch_no": t.batch_no or "",
            "is_forced": t.is_forced,
            "remark": t.remark or "",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        }
    })


@api_outbounds_bp.route("/outbounds/export")
@admin_required
def export_excel():
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    query = Transaction.query.filter_by(direction="out")
    if warehouse_type in ("raw", "semi", "finished"):
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        if wh:
            query = query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(
            db.or_(Material.name.contains(search), Material.code.contains(search))
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "出库记录"
    ws.append(["时间", "类型", "物料编号", "物料名称", "规格", "仓库", "数量", "批次号", "强制出库", "操作人", "备注"])
    for t in query.order_by(Transaction.created_at.desc()).all():
        ws.append([
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            t.transaction_type,
            t.material.code if t.material else "",
            t.material.name if t.material else "",
            t.material.spec or "",
            t.warehouse.name if t.warehouse else "",
            t.quantity,
            t.batch_no or "",
            "是" if t.is_forced else "",
            t.operator.display_name if t.operator else "",
            t.remark or "",
        ])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="出库记录.xlsx",
    )
