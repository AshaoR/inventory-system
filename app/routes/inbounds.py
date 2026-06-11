import io
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Transaction
from app.services import InboundService
import openpyxl

inbounds_bp = Blueprint("inbounds", __name__, url_prefix="/inbounds")


@inbounds_bp.route("/")
@admin_required
def index():
    page = request.args.get("page", 1, type=int)
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    query = Transaction.query.filter_by(direction="in")
    if warehouse_type in ("raw", "semi", "finished"):
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        if wh:
            query = query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(db.or_(Material.name.contains(search), Material.code.contains(search)))
    pagination = query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("inbounds/list.html", pagination=pagination, warehouse_type=warehouse_type, search=search)


@inbounds_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    warehouse_type = request.args.get("warehouse_type", "raw")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        flash("仓库不存在", "danger")
        return redirect(url_for("inbounds.index"))
    materials = Material.query.filter_by(warehouse_type=warehouse_type, is_active=True).order_by(Material.code).all()

    if request.method == "POST":
        material_ids = request.form.getlist("material_id")
        quantities = request.form.getlist("quantity")
        transaction_types = request.form.getlist("transaction_type")
        unit_prices = request.form.getlist("unit_price")
        remarks = request.form.getlist("remark")

        try:
            created = 0
            for i in range(len(material_ids)):
                try:
                    mid = int(material_ids[i]) if material_ids[i].strip() else 0
                except ValueError:
                    mid = 0
                if mid <= 0:
                    continue
                try:
                    qty = float(quantities[i]) if i < len(quantities) and quantities[i].strip() else 0
                except ValueError:
                    qty = 0
                if qty <= 0:
                    continue

                tt = transaction_types[i].strip() if i < len(transaction_types) else "采购入库"
                unit_price = None
                if i < len(unit_prices) and unit_prices[i].strip():
                    try:
                        unit_price = float(unit_prices[i])
                    except ValueError:
                        unit_price = None
                remark = remarks[i].strip() if i < len(remarks) and remarks[i].strip() else None

                InboundService.create(
                    material_id=mid, warehouse_id=wh.id,
                    quantity=qty, operator_id=current_user.id,
                    transaction_type=tt, unit_price=unit_price,
                    remark=remark,
                )
                created += 1

            db.session.commit()
            if created:
                flash(f"入库完成：成功 {created} 条", "success")
            else:
                flash("没有有效的入库记录", "warning")
        except Exception as e:
            db.session.rollback()
            flash(f"入库失败：{str(e)}", "danger")
        return redirect(url_for("inbounds.index"))

    return render_template("inbounds/create.html", materials=materials, warehouse_type=warehouse_type, warehouse_name=wh.name if wh else "")


@inbounds_bp.route("/export")
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
        query = query.join(Material).filter(db.or_(Material.name.contains(search), Material.code.contains(search)))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "入库记录"
    ws.append(["时间", "类型", "物料编号", "物料名称", "规格", "仓库", "数量", "单价", "操作人", "备注"])

    for t in query.order_by(Transaction.created_at.desc()).all():
        ws.append([
            t.created_at.strftime("%Y-%m-%d %H:%M"),
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

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="入库记录.xlsx")


@inbounds_bp.route("/<int:id>")
@admin_required
def detail(id):
    t = db.get_or_404(Transaction, id)
    return render_template("inbounds/detail.html", t=t)
