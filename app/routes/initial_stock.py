import io
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Warehouse, Material, InitialStock, Transaction, Inventory
from app.services import InitialStockService
import openpyxl

initial_stock_bp = Blueprint("initial_stock", __name__, url_prefix="/initial-stock")


@initial_stock_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    warehouse_type = request.args.get("warehouse_type", "raw")
    wh = Warehouse.query.filter_by(code=warehouse_type).first()
    if not wh:
        flash("仓库不存在", "danger")
        return redirect(url_for("dashboard.index"))
    warehouse_name = wh.name

    if request.method == "POST":
        material_ids = request.form.getlist("material_id")
        quantities = request.form.getlist("quantity")
        unit_prices = request.form.getlist("unit_price")
        remarks = request.form.getlist("remark")

        created, skipped = 0, 0
        try:
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

                unit_price = None
                if i < len(unit_prices) and unit_prices[i].strip():
                    try:
                        unit_price = float(unit_prices[i])
                    except ValueError:
                        unit_price = None

                remark = remarks[i].strip() if i < len(remarks) else None

                InitialStockService.record(
                    material_id=mid, warehouse_id=wh.id,
                    quantity=qty, operator_id=current_user.id,
                    unit_price=unit_price, remark=remark or None,
                )
                created += 1

            db.session.commit()

            if created:
                flash(f"期初库存录入完成：成功 {created} 条" + (f"，跳过 {skipped} 条" if skipped else ""), "success")
            else:
                flash("没有有效的记录，请填写物料和数量", "warning")
        except Exception as e:
            db.session.rollback()
            flash(f"期初库存录入失败：{str(e)}", "danger")
        return redirect(url_for("initial_stock.index", warehouse_type=warehouse_type))

    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")

    records_query = InitialStock.query
    if search:
        records_query = records_query.join(Material).filter(
            db.or_(Material.name.contains(search), Material.code.contains(search))
        )
    records = records_query.order_by(InitialStock.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    materials = Material.query.filter_by(warehouse_type=warehouse_type, is_active=True).order_by(Material.code).all()
    return render_template("initial_stock/list.html",
                           materials=materials,
                           warehouse_type=warehouse_type,
                           warehouse_name=warehouse_name,
                           pagination=records,
                           search=search)


@initial_stock_bp.route("/export")
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
        # 左连查询：所有物料 + 初始录入记录（库存为0的也显示）
        rows = (
            db.session.query(Material, InitialStock)
            .outerjoin(InitialStock, InitialStock.material_id == Material.id)
            .filter(Material.is_active == True)
            .order_by(InitialStock.created_at.desc().nullslast(), Material.warehouse_type, Material.code)
            .all()
        )
        seen = set()
        for m, r in rows:
            if r:
                ws.append([
                    r.created_at.strftime("%Y-%m-%d %H:%M"),
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
                seen.add(m.id)
            elif m.id not in seen:
                ws.append(["", m.code, m.name, m.spec or "", m.unit, wh.name, 0, "", "", ""])
                seen.add(m.id)
        filename = f"录入记录_{wh.name if wh else ''}.xlsx"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)


@initial_stock_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    """Redirect to the unified index page. POST is forwarded to index handler."""
    warehouse_type = request.args.get("warehouse_type", "raw")
    if request.method == "POST":
        return index()
    return redirect(url_for("initial_stock.index", warehouse_type=warehouse_type))


@initial_stock_bp.route("/<int:id>/delete", methods=["POST"])
@admin_required
def delete(id):
    rec = db.get_or_404(InitialStock, id)
    try:
        # 通过 initial_stock_id 精确匹配对应的流水
        Transaction.query.filter_by(initial_stock_id=rec.id).delete()

        # 扣减库存
        inv = Inventory.query.filter_by(
            material_id=rec.material_id, warehouse_id=rec.warehouse_id
        ).first()
        if inv:
            inv.quantity = (inv.quantity or 0) - rec.quantity

        db.session.delete(rec)
        db.session.commit()
        flash("期初记录已删除，库存已自动调整", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"删除失败：{str(e)}", "danger")
    return redirect(url_for("initial_stock.index"))
