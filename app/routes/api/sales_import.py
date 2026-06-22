from io import BytesIO
from flask import Blueprint, jsonify, request, session as flask_session
from flask_login import current_user
from app.decorators import admin_required
from app import db
from app.models import Material, Warehouse, SalesImportMapping, ImportPendingItem, ImportLog
from app.services import ImportService, InventoryService, TransactionService

api_sales_import_bp = Blueprint("api_sales_import", __name__)


@api_sales_import_bp.route("/import/sales/upload", methods=["POST"])
@admin_required
def upload():
    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400
    f = request.files["file"]
    file_bytes = f.read()
    file_hash = ImportService.compute_hash(file_bytes)

    existing = ImportService.check_duplicate(file_hash)
    if existing:
        return jsonify({
            "warning": f"此文件已于 {existing.created_at.strftime('%Y-%m-%d %H:%M') if existing.created_at else ''} 导入过（{existing.row_count} 条记录）",
            "duplicate": True,
            "file_hash": file_hash,
        })

    try:
        rows = ImportService.parse_excel(BytesIO(file_bytes))
    except Exception as e:
        return jsonify({"error": f"文件解析失败：{str(e)}"}), 400

    if not rows:
        return jsonify({"error": "未解析到有效数据"}), 400

    mapped, unmapped = [], []
    seen_names = set()
    for row in rows:
        name = row["product_name"]
        material = ImportService.auto_match(name)
        if material:
            mapped.append({**row, "material_id": material.id, "material_code": material.code, "material_name": material.name})
            if name not in seen_names:
                ImportService.save_mapping(name, material.id)
                seen_names.add(name)
        else:
            unmapped.append(row)
    db.session.commit()

    flask_session["import_preview"] = {
        "file_hash": file_hash,
        "file_name": f.filename,
        "mapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price"), r["material_id"]) for r in mapped],
        "unmapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price")) for r in unmapped],
    }

    return jsonify({
        "data": {
            "mapped": [{
                "order_no": r["order_no"],
                "product_name": r["product_name"],
                "quantity": r["quantity"],
                "unit_price": r.get("unit_price"),
                "material_id": r["material_id"],
                "material_code": r["material_code"],
                "material_name": r["material_name"],
            } for r in mapped],
            "unmapped": [{
                "order_no": r["order_no"],
                "product_name": r["product_name"],
                "quantity": r["quantity"],
                "unit_price": r.get("unit_price"),
            } for r in unmapped],
            "file_hash": file_hash,
            "file_name": f.filename,
        }
    })


@api_sales_import_bp.route("/import/sales/upload-force", methods=["POST"])
@admin_required
def upload_force():
    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400
    f = request.files["file"]
    file_bytes = f.read()
    file_hash = ImportService.compute_hash(file_bytes)

    try:
        rows = ImportService.parse_excel(BytesIO(file_bytes))
    except Exception as e:
        return jsonify({"error": f"文件解析失败：{str(e)}"}), 400

    if not rows:
        return jsonify({"error": "未解析到有效数据"}), 400

    mapped, unmapped = [], []
    seen_names = set()
    for row in rows:
        name = row["product_name"]
        material = ImportService.auto_match(name)
        if material:
            mapped.append({**row, "material_id": material.id, "material_code": material.code, "material_name": material.name})
            if name not in seen_names:
                ImportService.save_mapping(name, material.id)
                seen_names.add(name)
        else:
            unmapped.append(row)
    db.session.commit()

    flask_session["import_preview"] = {
        "file_hash": file_hash,
        "file_name": f.filename,
        "mapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price"), r["material_id"]) for r in mapped],
        "unmapped": [(r["order_no"], r["product_name"], r["quantity"], r.get("unit_price")) for r in unmapped],
    }

    return jsonify({
        "data": {
            "mapped": [{
                "order_no": r["order_no"],
                "product_name": r["product_name"],
                "quantity": r["quantity"],
                "unit_price": r.get("unit_price"),
                "material_id": r["material_id"],
                "material_code": r["material_code"],
                "material_name": r["material_name"],
            } for r in mapped],
            "unmapped": [{
                "order_no": r["order_no"],
                "product_name": r["product_name"],
                "quantity": r["quantity"],
                "unit_price": r.get("unit_price"),
            } for r in unmapped],
            "file_hash": file_hash,
            "file_name": f.filename,
        }
    })


@api_sales_import_bp.route("/import/sales/confirm", methods=["POST"])
@admin_required
def confirm():
    preview_data = flask_session.pop("import_preview", None)
    if not preview_data:
        return jsonify({"error": "预览数据已过期，请重新上传"}), 400

    file_hash, file_name = preview_data["file_hash"], preview_data["file_name"]
    mapped, unmapped = preview_data["mapped"], preview_data["unmapped"]

    warehouse = Warehouse.query.filter_by(code="finished").first()
    if not warehouse:
        return jsonify({"error": "成品仓未配置"}), 400

    try:
        if ImportService.check_duplicate(file_hash):
            return jsonify({"error": "此文件已被其他用户导入"}), 409

        batch_no = ImportService.generate_batch_no()
        log = ImportLog(
            file_hash=file_hash, file_name=file_name,
            row_count=len(mapped) + len(unmapped),
            operator_id=current_user.id, batch_no=batch_no,
        )
        db.session.add(log)
        db.session.flush()

        for order_no, product_name, quantity, unit_price, material_id in mapped:
            InventoryService.deduct_stock(material_id, warehouse.id, quantity)
            TransactionService.create(
                direction="out", transaction_type="销售出库",
                material_id=material_id, warehouse_id=warehouse.id,
                quantity=quantity, unit_price=unit_price,
                operator_id=current_user.id, batch_no=batch_no,
                remark=f"外部导入（{file_name}）",
            )

        for order_no, product_name, quantity, unit_price in unmapped:
            db.session.add(ImportPendingItem(
                import_log_id=log.id, external_name=product_name,
                quantity=quantity, unit_price=unit_price,
                order_no=order_no or "", status="pending",
            ))

        db.session.commit()
        return jsonify({
            "data": {
                "imported": len(mapped),
                "pending": len(unmapped),
                "batch_no": batch_no,
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@api_sales_import_bp.route("/import/history")
@admin_required
def import_history():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    logs = ImportLog.query.order_by(ImportLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for log in logs.items:
        items.append({
            "id": log.id,
            "file_name": log.file_name,
            "row_count": log.row_count,
            "operator": log.operator.display_name if log.operator else "",
            "batch_no": log.batch_no or "",
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": logs.total,
        "page": logs.page,
        "per_page": logs.per_page,
        "pages": logs.pages,
    })


@api_sales_import_bp.route("/import/mappings", methods=["GET"])
@admin_required
def list_mappings():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    mappings_list = SalesImportMapping.query.order_by(SalesImportMapping.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    items = []
    for m in mappings_list.items:
        items.append({
            "id": m.id,
            "external_name": m.external_name,
            "material_id": m.material_id,
            "material_code": m.material.code if m.material else "",
            "material_name": m.material.name if m.material else "",
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
        })
    return jsonify({
        "data": items,
        "total": mappings_list.total,
        "page": mappings_list.page,
        "per_page": mappings_list.per_page,
        "pages": mappings_list.pages,
    })


@api_sales_import_bp.route("/import/mappings", methods=["POST"])
@admin_required
def create_mapping():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400
    external_name = data.get("external_name", "").strip()
    material_id = data.get("material_id")
    if not external_name or not material_id:
        return jsonify({"error": "外部名称和物料不能为空"}), 400
    ImportService.save_mapping(external_name, material_id)
    db.session.commit()
    return jsonify({"data": "ok"}), 201


@api_sales_import_bp.route("/import/mappings/<int:id>", methods=["DELETE"])
@admin_required
def delete_mapping(id):
    mapping = db.get_or_404(SalesImportMapping, id)
    db.session.delete(mapping)
    db.session.commit()
    return jsonify({"data": "ok"})


@api_sales_import_bp.route("/import/pending")
@admin_required
def pending_items():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items = ImportPendingItem.query.filter_by(status="pending").order_by(
        ImportPendingItem.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    result = []
    for item in items.items:
        result.append({
            "id": item.id,
            "external_name": item.external_name,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price else None,
            "order_no": item.order_no or "",
            "import_log_id": item.import_log_id,
            "file_name": item.import_log.file_name if item.import_log else "",
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "",
        })
    return jsonify({
        "data": result,
        "total": items.total,
        "page": items.page,
        "per_page": items.per_page,
        "pages": items.pages,
    })


@api_sales_import_bp.route("/import/pending/bulk-resolve", methods=["POST"])
@admin_required
def bulk_resolve():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400
    material_id = data.get("material_id")
    pending_ids = data.get("pending_ids", [])
    if not material_id or not pending_ids:
        return jsonify({"error": "请选择物料和待处理记录"}), 400
    count = ImportService.bulk_resolve_pending(pending_ids, material_id, current_user.id)
    return jsonify({"data": {"resolved": count}})
