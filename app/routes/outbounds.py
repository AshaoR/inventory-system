import io
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, Transaction
from app.services import OutboundService
import openpyxl

outbounds_bp = Blueprint("outbounds", __name__, url_prefix="/outbounds")


@outbounds_bp.route("/")
@admin_required
def index():
    page = request.args.get("page", 1, type=int)
    warehouse_type = request.args.get("warehouse_type", "")
    search = request.args.get("search", "")
    batch_no = request.args.get("batch_no", "")
    query = Transaction.query.filter_by(direction="out")
    if warehouse_type in ("raw", "semi", "finished"):
        wh = Warehouse.query.filter_by(code=warehouse_type).first()
        if wh:
            query = query.filter_by(warehouse_id=wh.id)
    if search:
        query = query.join(Material).filter(db.or_(Material.name.contains(search), Material.code.contains(search)))
    if batch_no:
        query = query.filter(Transaction.batch_no.contains(batch_no))
    pagination = query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("outbounds/list.html", pagination=pagination, warehouse_type=warehouse_type, search=search, batch_no=batch_no)


@outbounds_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    warehouse_type = request.args.get("warehouse_type", "finished")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        flash("仓库不存在", "danger")
        return redirect(url_for("outbounds.index"))
    materials = Material.query.filter_by(warehouse_type=warehouse_type, is_active=True).order_by(Material.code).all()

    if request.method == "POST":
        material_ids = request.form.getlist("material_id")
        quantities = request.form.getlist("quantity")
        transaction_types = request.form.getlist("transaction_type")
        remarks = request.form.getlist("remark")
        is_forced = request.form.get("is_forced") == "y"

        try:
            created, skipped = 0, 0
            for i in range(len(material_ids)):
                try:
                    mid = int(material_ids[i]) if material_ids[i].strip() else 0
                except ValueError:
                    mid = 0
                if mid <= 0:
                    skipped += 1
                    continue

                try:
                    qty = float(quantities[i]) if i < len(quantities) and quantities[i].strip() else 0
                except ValueError:
                    qty = 0
                if qty <= 0:
                    skipped += 1
                    continue

                ttype = transaction_types[i] if i < len(transaction_types) else "生产领用"
                remark = remarks[i].strip() if i < len(remarks) else None

                OutboundService.create(
                    material_id=mid, warehouse_id=wh.id,
                    quantity=qty, operator_id=current_user.id,
                    transaction_type=ttype, is_forced=is_forced,
                    forced_reason="批量出库" if is_forced else None,
                    remark=remark or None,
                )
                created += 1

            db.session.commit()
            parts = []
            if created:
                parts.append(f"成功出库 {created} 条")
            if skipped:
                parts.append(f"跳过 {skipped} 条")
            flash("，".join(parts), "success" if created else "warning")
        except Exception as e:
            db.session.rollback()
            flash(f"出库失败：{str(e)}", "danger")
        return redirect(url_for("outbounds.index"))

    from app.services import InventoryService
    materials_data = []
    for m in materials:
        qty = InventoryService.get_quantity(m.id, wh.id) if wh else 0
        materials_data.append({"material": m, "quantity": qty})
    return render_template("outbounds/create.html",
                           materials_data=materials_data,
                           warehouse_type=warehouse_type,
                           warehouse_name=wh.name if wh else "")


@outbounds_bp.route("/export")
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
        query = query.join(Material).filter(db.or_(Material.name.contains(search), Material.code.contains(search)))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "出库记录"
    ws.append(["时间", "类型", "物料编号", "物料名称", "规格", "仓库", "数量", "批次号", "强制出库", "操作人", "备注"])

    for t in query.order_by(Transaction.created_at.desc()).all():
        ws.append([
            t.created_at.strftime("%Y-%m-%d %H:%M"),
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

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="出库记录.xlsx")


@outbounds_bp.route("/check-stock")
@admin_required
def check_stock():
    material_id = request.args.get("material_id", type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    quantity = request.args.get("quantity", type=float)
    if not all([material_id, warehouse_id, quantity]):
        return jsonify({"sufficient": False, "current_stock": 0})
    from app.services import InventoryService
    current_stock = InventoryService.get_quantity(material_id, warehouse_id)
    return jsonify({"sufficient": current_stock >= quantity, "current_stock": current_stock})


@outbounds_bp.route("/<int:id>")
@admin_required
def detail(id):
    t = db.get_or_404(Transaction, id)
    return render_template("outbounds/detail.html", t=t)
