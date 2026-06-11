from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Warehouse, Stocktake
from app.forms import StocktakeForm
from app.services import StocktakeService

stocktake_bp = Blueprint("stocktakes", __name__, url_prefix="/stocktakes")


@stocktake_bp.route("/")
@admin_required
def index():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    query = Stocktake.query
    if status_filter in ("in_progress", "completed"):
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(Stocktake.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("stocktakes/list.html", pagination=pagination, status_filter=status_filter)


@stocktake_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    form = StocktakeForm()
    form.warehouse_id.choices = [(w.id, w.name) for w in Warehouse.query.all()]
    if form.validate_on_submit():
        st = StocktakeService.create(warehouse_id=form.warehouse_id.data, operator_id=current_user.id, remark=form.remark.data or None)
        db.session.commit()
        flash("盘点单已创建，请录入实盘数量", "success")
        return redirect(url_for("stocktakes.edit", id=st.id))
    return render_template("stocktakes/create.html", form=form)


@stocktake_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def edit(id):
    st = db.get_or_404(Stocktake, id)
    if st.status == "completed":
        flash("该盘点已完成，无法修改", "warning")
        return redirect(url_for("stocktakes.detail", id=id))

    if request.method == "POST":
        actual_data = []
        for key, value in request.form.items():
            if key.startswith("actual_"):
                try:
                    item_id = int(key.replace("actual_", ""))
                except (ValueError, IndexError):
                    continue
                actual_qty = request.form.get(f"actual_{item_id}", type=float)
                remark = request.form.get(f"remark_{item_id}", "")
                actual_data.append({"item_id": item_id, "actual_quantity": actual_qty, "remark": remark})
        result = StocktakeService.complete(st.id, actual_data)
        if result:
            db.session.commit()
            flash("盘点完成，差异已自动调整库存", "success")
            return redirect(url_for("stocktakes.detail", id=st.id))
        flash("盘点提交失败", "danger")
    return render_template("stocktakes/edit.html", stocktake=st)


@stocktake_bp.route("/<int:id>")
@admin_required
def detail(id):
    st = db.get_or_404(Stocktake, id)
    return render_template("stocktakes/detail.html", stocktake=st)
