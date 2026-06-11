from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func
from app import db
from app.models import Material, Inventory, Transaction, Stocktake, Warehouse

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    total_materials = Material.query.filter_by(is_active=True).count()
    total_inventory_items = (
        Inventory.query
        .join(Material)
        .filter(Material.is_active == True, Inventory.quantity > 0)
        .count()
    )

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

    recent_transactions = (
        Transaction.query.order_by(Transaction.created_at.desc()).limit(20).all()
    )

    active_stocktakes = (
        Stocktake.query.filter_by(status="in_progress")
        .order_by(Stocktake.created_at.desc()).all()
    )

    warehouse_stats = (
        db.session.query(
            Inventory.warehouse_id,
            func.sum(Inventory.quantity).label("total_qty"),
            func.count(Inventory.id).label("item_count"),
        )
        .group_by(Inventory.warehouse_id)
        .all()
    )

    warehouses = {w.id: w.name for w in Warehouse.query.all()}

    return render_template(
        "dashboard.html",
        total_materials=total_materials,
        total_inventory_items=total_inventory_items,
        low_stock_count=low_stock_count,
        low_stock_items=low_stock_items,
        negative_count=negative_count,
        recent_transactions=recent_transactions,
        active_stocktakes=active_stocktakes,
        warehouse_stats=warehouse_stats,
        warehouses=warehouses,
    )
