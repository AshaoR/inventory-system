from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Transaction
from app.services import InboundService
import openpyxl

api_inbounds_bp = Blueprint("api_inbounds", __name__)


@api_inbounds_bp.route("/inbounds", methods=["GET"])
@admin_required
def list_inbounds():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    query = Transaction.query.filter_by(direction="in")
    if warehouse_type in ("raw", "semi", "finished"):
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        if wh:
            query = query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(
            db.or_(Material.name.contains(search), Material.code.contains(search))
        )
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


@api_inbounds_bp.route("/inbounds", methods=["POST"])
@admin_required
def create_inbounds():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "请求数据格式错误，应为数组"}), 400

    warehouse_type = request.args.get("warehouse_type", "raw")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        return jsonify({"error": "仓库不存在"}), 404

    created = 0
    errors = []
    for i, item in enumerate(data):
        mid = item.get("material_id")
        qty = item.get("quantity", 0)
        if not mid or qty <= 0:
            errors.append({"index": i, "error": "无效的物料或数量"})
            continue
        try:
            InboundService.create(
                material_id=mid, warehouse_id=wh.id,
                quantity=qty, operator_id=current_user.id,
                transaction_type=item.get("type", "采购入库"),
                unit_price=item.get("unit_price"),
                remark=item.get("remark") or None,
            )
            created += 1
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    db.session.commit()
    return jsonify({"data": {"created": created, "errors": errors}}), 201


@api_inbounds_bp.route("/inbounds/<int:id>")
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
            "remark": t.remark or "",
            "batch_no": t.batch_no or "",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        }
    })


@api_inbounds_bp.route("/inbounds/export")
@admin_required
def export_excel():
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    query = Transaction.query.filter_by(direction="in")
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
    ws.title = "入库记录"
    ws.append(["时间", "类型", "物料编号", "物料名称", "规格", "仓库", "数量", "单价", "操作人", "备注"])
    for t in query.order_by(Transaction.created_at.desc()).all():
        ws.append([
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            t.transaction_type,
            t.material.code if t.material else "",
            t.material.name if t.material else "",
            t.material.spec or "",
            t.warehouse.name if t.warehouse else "",
            t.quantity,
            str(t.unit_price) if t.unit_price else "",
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
        download_name="入库记录.xlsx",
    )
