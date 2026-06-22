from flask import Blueprint, jsonify
from flask_login import login_required
from sqlalchemy import func
from app import db
from app.models import Material, Inventory, Transaction, Stocktake, Warehouse

api_dashboard_bp = Blueprint("api_dashboard", __name__)


@api_dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def index():
    total_materials = Material.query.filter_by(is_active=True).count()
    total_inventory_items = (
        db.session.query(func.count(func.distinct(Inventory.material_id)))
        .join(Material)
        .filter(Material.is_active == True, Inventory.quantity > 0)
        .scalar()
    ) or 0

    low_stock_count = 0
    low_stock_items = []
    for m in Material.query.filter_by(is_active=True).all():
        inv = Inventory.query.filter_by(material_id=m.id).first()
        qty = inv.quantity if inv else 0
        if 0 < qty < (m.min_stock or 0):
            low_stock_count += 1
            if len(low_stock_items) < 10:
                low_stock_items.append({
                    "code": m.code, "name": m.name,
                    "quantity": qty, "min_stock": m.min_stock,
                })

    negative_count = Inventory.query.filter(Inventory.quantity < 0).count()

    recent_transactions = []
    for t in Transaction.query.order_by(Transaction.created_at.desc()).limit(20).all():
        recent_transactions.append({
            "id": t.id,
            "direction": t.direction,
            "type": t.transaction_type,
            "material_name": t.material.name if t.material else "",
            "material_code": t.material.code if t.material else "",
            "warehouse_name": t.warehouse.name if t.warehouse else "",
            "quantity": t.quantity,
            "operator": t.operator.display_name if t.operator else "",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            "is_forced": t.is_forced,
        })

    active_stocktakes = []
    for st in Stocktake.query.filter_by(status="in_progress").order_by(Stocktake.created_at.desc()).all():
        active_stocktakes.append({
            "id": st.id,
            "warehouse_name": st.warehouse.name if st.warehouse else "",
            "operator": st.operator.display_name if st.operator else "",
            "started_at": st.started_at.strftime("%Y-%m-%d %H:%M") if st.started_at else "",
        })

    warehouse_stats = (
        db.session.query(
            Inventory.warehouse_id,
            func.sum(Inventory.quantity).label("total_qty"),
            func.count(Inventory.id).label("item_count"),
        )
        .group_by(Inventory.warehouse_id)
        .all()
    )

    warehouses = {w.id: {"name": w.name, "code": w.code} for w in Warehouse.query.all()}

    stats_list = []
    for ws in warehouse_stats:
        wh_info = warehouses.get(ws.warehouse_id, {})
        stats_list.append({
            "warehouse_name": wh_info.get("name", ""),
            "warehouse_code": wh_info.get("code", ""),
            "total_qty": float(ws.total_qty or 0),
            "item_count": ws.item_count,
        })

    return jsonify({
        "data": {
            "total_materials": total_materials,
            "total_inventory_items": total_inventory_items,
            "low_stock_count": low_stock_count,
            "low_stock_items": low_stock_items,
            "negative_count": negative_count,
            "recent_transactions": recent_transactions,
            "active_stocktakes": active_stocktakes,
            "warehouse_stats": stats_list,
        }
    })
