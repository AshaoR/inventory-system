from flask import Blueprint, jsonify, request
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Warehouse, Stocktake
from app.services import StocktakeService

api_stocktake_bp = Blueprint("api_stocktake", __name__)


@api_stocktake_bp.route("/stocktakes", methods=["GET"])
@admin_required
def list_stocktakes():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status_filter = request.args.get("status", "")
    query = Stocktake.query
    if status_filter in ("in_progress", "completed"):
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(Stocktake.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for st in pagination.items:
        items.append({
            "id": st.id,
            "warehouse_name": st.warehouse.name if st.warehouse else "",
            "operator": st.operator.display_name if st.operator else "",
            "status": st.status,
            "started_at": st.started_at.strftime("%Y-%m-%d %H:%M") if st.started_at else "",
            "remark": st.remark or "",
            "item_count": len(st.items) if st.items else 0,
            "created_at": st.created_at.strftime("%Y-%m-%d %H:%M") if st.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
    })


@api_stocktake_bp.route("/stocktakes", methods=["POST"])
@admin_required
def create_stocktake():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400
    warehouse_id = data.get("warehouse_id")
    if not warehouse_id:
        return jsonify({"error": "请选择仓库"}), 400
    try:
        st = StocktakeService.create(
            warehouse_id=warehouse_id,
            operator_id=current_user.id,
            remark=data.get("remark") or None,
        )
        db.session.commit()
        return jsonify({"data": {"id": st.id}}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@api_stocktake_bp.route("/stocktakes/<int:id>")
@admin_required
def detail(id):
    st = db.get_or_404(Stocktake, id)
    items = []
    for item in st.items:
        items.append({
            "id": item.id,
            "material_id": item.material_id,
            "material_code": item.material.code if item.material else "",
            "material_name": item.material.name if item.material else "",
            "material_spec": item.material.spec if item.material else "",
            "book_quantity": item.book_quantity,
            "actual_quantity": item.actual_quantity,
            "difference": item.difference,
            "remark": item.remark or "",
        })
    return jsonify({
        "data": {
            "id": st.id,
            "warehouse_id": st.warehouse_id,
            "warehouse_name": st.warehouse.name if st.warehouse else "",
            "operator": st.operator.display_name if st.operator else "",
            "status": st.status,
            "started_at": st.started_at.strftime("%Y-%m-%d %H:%M") if st.started_at else "",
            "remark": st.remark or "",
            "created_at": st.created_at.strftime("%Y-%m-%d %H:%M") if st.created_at else "",
            "items": items,
        }
    })


@api_stocktake_bp.route("/stocktakes/<int:id>/complete", methods=["POST"])
@admin_required
def complete_stocktake(id):
    st = db.get_or_404(Stocktake, id)
    if st.status == "completed":
        return jsonify({"error": "该盘点已完成"}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "请求数据格式错误"}), 400

    actual_data = []
    for item in data:
        actual_data.append({
            "item_id": item.get("item_id"),
            "actual_quantity": item.get("actual_quantity"),
            "remark": item.get("remark", ""),
        })

    try:
        result = StocktakeService.complete(st.id, actual_data)
        if result:
            db.session.commit()
            return jsonify({"data": "ok"})
        return jsonify({"error": "盘点提交失败"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@api_stocktake_bp.route("/warehouses")
@admin_required
def list_warehouses():
    warehouses = Warehouse.query.all()
    return jsonify({
        "data": [{"id": w.id, "name": w.name, "code": w.code} for w in warehouses]
    })
