from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Inventory
from app.services import generate_code

api_materials_bp = Blueprint("api_materials", __name__)


@api_materials_bp.route("/materials", methods=["GET"])
@login_required
def list_materials():
    warehouse_type = request.args.get("warehouse_type", "raw")
    show_inactive = request.args.get("show_inactive", "0") == "1"
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = Material.query
    query = query.filter_by(is_active=False) if show_inactive else query.filter_by(is_active=True)
    if warehouse_type in ("raw", "semi", "finished"):
        query = query.filter_by(warehouse_type=warehouse_type)
    if search:
        query = query.filter(db.or_(
            Material.name.contains(search),
            Material.code.contains(search),
            Material.spec.contains(search),
        ))

    pagination = query.order_by(Material.code).paginate(page=page, per_page=per_page, error_out=False)
    material_ids = [m.id for m in pagination.items]
    invs = Inventory.query.filter(Inventory.material_id.in_(material_ids)).all()
    inv_map = {inv.material_id: inv.quantity for inv in invs}
    warehouses = {w.code: w.id for w in Warehouse.query.all()}
    items = []
    for m in pagination.items:
        wh_id = warehouses.get(m.warehouse_type)
        qty = inv_map.get(m.id, 0) if wh_id else 0
        d = m.to_dict()
        d["quantity"] = qty
        items.append(d)

    return jsonify({
        "data": items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
    })


@api_materials_bp.route("/materials", methods=["POST"])
@admin_required
def create_material():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400

    name = data.get("name", "").strip()
    warehouse_type = data.get("warehouse_type", "raw")
    spec = data.get("spec", "").strip() or None
    if not name:
        return jsonify({"error": "物料名称不能为空"}), 400

    existing = Material.query.filter_by(name=name, spec=spec, warehouse_type=warehouse_type, is_active=True).first()
    if existing:
        return jsonify({"error": f"该仓库已存在同名物料：{existing.code} {existing.name}"}), 409

    code = generate_code(warehouse_type)
    m = Material(
        code=code, name=name, spec=spec,
        unit=data.get("unit", "个"),
        warehouse_type=warehouse_type,
        category=data.get("category") or None,
        min_stock=data.get("min_stock", 0) or 0,
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({"data": m.to_dict()}), 201


@api_materials_bp.route("/materials/batch", methods=["POST"])
@admin_required
def batch_create():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "请求数据格式错误，应为数组"}), 400

    created, skipped = 0, 0
    for item in data:
        name = item.get("name", "").strip()
        if not name:
            skipped += 1
            continue
        wt = item.get("warehouse_type", "raw")
        spec = item.get("spec", "").strip() or None
        existing = Material.query.filter_by(name=name, spec=spec, warehouse_type=wt, is_active=True).first()
        if existing:
            skipped += 1
            continue

        code = generate_code(wt)
        m = Material(
            code=code, name=name,
            spec=item.get("spec") or None,
            unit=item.get("unit", "个"),
            warehouse_type=wt,
            category=item.get("category") or None,
            min_stock=item.get("min_stock", 0) or 0,
        )
        db.session.add(m)
        created += 1

    db.session.commit()
    return jsonify({"data": {"created": created, "skipped": skipped}}), 201


@api_materials_bp.route("/materials/<int:id>", methods=["PUT"])
@admin_required
def update_material(id):
    m = db.get_or_404(Material, id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400

    name = data.get("name", "").strip()
    if name:
        spec = data.get("spec", "").strip() or m.spec
        existing = Material.query.filter(
            Material.id != id,
            Material.name == name,
            Material.spec == spec,
            Material.warehouse_type == (data.get("warehouse_type") or m.warehouse_type),
            Material.is_active == True,
        ).first()
        if existing:
            return jsonify({"error": f"该仓库已存在同名同规格物料：{existing.code} {existing.name}"}), 409
        m.name = name

    m.spec = data.get("spec") or None
    m.unit = data.get("unit", m.unit)

    new_warehouse_type = data.get("warehouse_type")
    if new_warehouse_type and new_warehouse_type != m.warehouse_type:
        m.warehouse_type = new_warehouse_type
        m.code = generate_code(new_warehouse_type)

    m.category = data.get("category") or None
    m.min_stock = data.get("min_stock", m.min_stock) or 0
    db.session.commit()
    return jsonify({"data": m.to_dict()})


@api_materials_bp.route("/materials/<int:id>/deactivate", methods=["POST"])
@admin_required
def deactivate(id):
    m = db.get_or_404(Material, id)
    m.is_active = False
    db.session.commit()
    wh = Warehouse.query.filter_by(code=m.warehouse_type).first()
    qty = 0
    if wh:
        inv = Inventory.query.filter_by(material_id=m.id, warehouse_id=wh.id).first()
        qty = inv.quantity if inv else 0
    return jsonify({"data": m.to_dict(), "warning": f"该物料尚有 {qty} 件库存" if qty > 0 else None})


@api_materials_bp.route("/materials/<int:id>/reactivate", methods=["POST"])
@admin_required
def reactivate(id):
    m = db.get_or_404(Material, id)
    m.is_active = True
    db.session.commit()
    return jsonify({"data": m.to_dict()})


@api_materials_bp.route("/materials/check-stock/<int:id>")
@login_required
def check_stock(id):
    m = db.get_or_404(Material, id)
    wh = Warehouse.query.filter_by(code=m.warehouse_type).first()
    qty = 0
    if wh:
        inv = Inventory.query.filter_by(material_id=m.id, warehouse_id=wh.id).first()
        qty = inv.quantity if inv else 0
    return jsonify({"data": {"quantity": qty}})
