from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Inventory
from app.forms import MaterialForm

materials_bp = Blueprint("materials", __name__, url_prefix="/materials")


def generate_code(warehouse_type):
    prefix_map = {"raw": "R", "semi": "S", "finished": "F"}
    prefix = prefix_map.get(warehouse_type, "X")
    last = (
        Material.query
        .filter(Material.code.like(f"{prefix}-%"))
        .order_by(Material.code.desc())
        .first()
    )
    if last and "-" in last.code:
        try:
            seq = int(last.code.split("-")[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}-{seq:04d}"


@materials_bp.route("/")
@admin_required
def index():
    warehouse_type = request.args.get("warehouse_type", "raw")
    show_inactive = request.args.get("show_inactive", "0") == "1"
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)

    query = Material.query
    query = query.filter_by(is_active=False) if show_inactive else query.filter_by(is_active=True)
    if warehouse_type in ("raw", "semi", "finished"):
        query = query.filter_by(warehouse_type=warehouse_type)
    if search:
        query = query.filter(db.or_(Material.name.contains(search), Material.code.contains(search), Material.spec.contains(search)))

    pagination = query.order_by(Material.code).paginate(page=page, per_page=50, error_out=False)
    material_list = []
    for m in pagination.items:
        wh = Warehouse.query.filter_by(code=m.warehouse_type).first()
        qty = 0
        if wh:
            inv = Inventory.query.filter_by(material_id=m.id, warehouse_id=wh.id).first()
            qty = inv.quantity if inv else 0
        material_list.append({**m.to_dict(), "quantity": qty})

    return render_template("materials/list.html", materials=material_list, pagination=pagination, warehouse_type=warehouse_type, show_inactive=show_inactive, search=search)


@materials_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    form = MaterialForm()
    warehouse_type = request.args.get("warehouse_type")
    if warehouse_type in ("raw", "semi", "finished"):
        form.warehouse_type.data = warehouse_type
    if form.validate_on_submit():
        # 检查同名
        existing = Material.query.filter_by(name=form.name.data, warehouse_type=form.warehouse_type.data, is_active=True).first()
        if existing:
            flash(f"该仓库已存在同名物料：{existing.code} {existing.name}", "danger")
            return render_template("materials/create.html", form=form)
        code = generate_code(form.warehouse_type.data)
        m = Material(code=code, name=form.name.data, spec=form.spec.data or None, unit=form.unit.data, warehouse_type=form.warehouse_type.data, category=form.category.data or None, min_stock=form.min_stock.data or 0)
        db.session.add(m)
        db.session.commit()
        flash(f"物料已创建，编号：{code}", "success")
        return redirect(url_for("materials.index", warehouse_type=form.warehouse_type.data))
    return render_template("materials/create.html", form=form)


@materials_bp.route("/batch-create", methods=["GET", "POST"])
@admin_required
def batch_create():
    unit_choices = ["个","只","米","千克","包","箱","套","张","卷","条"]
    cat_choices = ["面料","填充棉","配件","包装","衣服","其他"]
    wt_choices = [("raw","原材料仓"),("semi","半成品仓"),("finished","成品仓")]
    warehouse_type = request.args.get("warehouse_type", "raw")

    if request.method == "POST":
        names = request.form.getlist("name")
        specs = request.form.getlist("spec")
        units = request.form.getlist("unit")
        warehouse_types = request.form.getlist("warehouse_type")
        categories = request.form.getlist("category")
        min_stocks = request.form.getlist("min_stock")

        created, skipped = 0, 0
        for i in range(len(names)):
            name = names[i].strip()
            if not name:
                skipped += 1
                continue
            # 检查同名
            existing = Material.query.filter_by(name=name, warehouse_type=wt, is_active=True).first()
            if existing:
                skipped += 1
                continue
            spec = specs[i].strip() if i < len(specs) else ""
            unit = units[i].strip() if i < len(units) else "个"
            wt = warehouse_types[i].strip() if i < len(warehouse_types) else "raw"
            cat = categories[i].strip() if i < len(categories) else ""
            try:
                ms = float(min_stocks[i]) if i < len(min_stocks) and min_stocks[i].strip() else 0
            except ValueError:
                ms = 0

            code = generate_code(wt)
            m = Material(
                code=code, name=name, spec=spec or None,
                unit=unit, warehouse_type=wt,
                category=cat or None, min_stock=ms,
            )
            db.session.add(m)
            created += 1

        db.session.commit()
        parts = []
        if created:
            parts.append(f"成功创建 {created} 条物料")
        if skipped:
            parts.append(f"{skipped} 条已跳过（名称为空或重复）")
        flash("，".join(parts), "success" if created else "warning")
        return redirect(url_for("materials.index"))

    return render_template("materials/batch_create.html",
                           unit_choices=unit_choices,
                           cat_choices=cat_choices,
                           wt_choices=wt_choices,
                           warehouse_type=warehouse_type)


@materials_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def edit(id):
    m = db.get_or_404(Material, id)
    form = MaterialForm(obj=m)
    if form.validate_on_submit():
        m.name = form.name.data
        m.spec = form.spec.data or None
        m.unit = form.unit.data
        new_warehouse_type = form.warehouse_type.data
        if new_warehouse_type != m.warehouse_type:
            m.warehouse_type = new_warehouse_type
            m.code = generate_code(new_warehouse_type)
        else:
            m.warehouse_type = new_warehouse_type
        m.category = form.category.data or None
        m.min_stock = form.min_stock.data or 0
        db.session.commit()
        flash("物料已更新", "success")
        return redirect(url_for("materials.index"))
    form.warehouse_type.data = m.warehouse_type
    form.category.data = m.category
    return render_template("materials/edit.html", form=form, material=m)


@materials_bp.route("/<int:id>/deactivate", methods=["POST"])
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
    if qty > 0:
        flash(f"物料已停用（注意：该物料尚有 {qty} 件库存）", "warning")
    else:
        flash("物料已停用", "success")
    return redirect(url_for("materials.index"))


@materials_bp.route("/<int:id>/reactivate", methods=["POST"])
@admin_required
def reactivate(id):
    m = db.get_or_404(Material, id)
    m.is_active = True
    db.session.commit()
    flash("物料已恢复", "success")
    return redirect(url_for("materials.index", show_inactive=1))


@materials_bp.route("/check-stock/<int:id>")
@login_required
def check_stock(id):
    m = db.get_or_404(Material, id)
    wh = Warehouse.query.filter_by(code=m.warehouse_type).first()
    qty = 0
    if wh:
        inv = Inventory.query.filter_by(material_id=m.id, warehouse_id=wh.id).first()
        qty = inv.quantity if inv else 0
    return jsonify({"quantity": qty})
