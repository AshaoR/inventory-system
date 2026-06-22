import re
from datetime import datetime
from hashlib import sha256

from app import db
from app.models import (
    Material, Inventory, Transaction, InitialStock,
    Stocktake, StocktakeItem, ImportLog,
    SalesImportMapping, ImportPendingItem, Warehouse,
)
from app.models import BJ


def generate_code(warehouse_type):
    """根据仓库类型生成物料编号 (R-0001 / S-0001 / F-0001)"""
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


class InventoryService:

    @staticmethod
    def get_or_create(material_id, warehouse_id):
        inv = Inventory.query.filter_by(
            material_id=material_id, warehouse_id=warehouse_id
        ).first()
        if not inv:
            inv = Inventory(material_id=material_id, warehouse_id=warehouse_id, quantity=0)
            db.session.add(inv)
        return inv

    @staticmethod
    def add_stock(material_id, warehouse_id, quantity):
        inv = InventoryService.get_or_create(material_id, warehouse_id)
        inv.quantity = (inv.quantity or 0) + quantity
        return inv

    @staticmethod
    def deduct_stock(material_id, warehouse_id, quantity):
        inv = InventoryService.get_or_create(material_id, warehouse_id)
        inv.quantity = (inv.quantity or 0) - quantity
        return inv

    @staticmethod
    def get_quantity(material_id, warehouse_id):
        inv = Inventory.query.filter_by(
            material_id=material_id, warehouse_id=warehouse_id
        ).first()
        return inv.quantity if inv else 0


class TransactionService:

    @staticmethod
    def create(direction, transaction_type, material_id, warehouse_id,
               quantity, operator_id, unit_price=None, batch_no=None,
               is_forced=False, remark=None, initial_stock_id=None):
        t = Transaction(
            direction=direction,
            transaction_type=transaction_type,
            material_id=material_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
            unit_price=unit_price,
            operator_id=operator_id,
            batch_no=batch_no,
            is_forced=is_forced,
            initial_stock_id=initial_stock_id,
            remark=remark,
        )
        db.session.add(t)
        return t


class InitialStockService:

    @staticmethod
    def record(material_id, warehouse_id, quantity, operator_id,
               unit_price=None, remark=None):
        rec = InitialStock(
            material_id=material_id, warehouse_id=warehouse_id,
            quantity=quantity, unit_price=unit_price,
            operator_id=operator_id, remark=remark,
        )
        db.session.add(rec)
        db.session.flush()  # 获取 rec.id
        InventoryService.add_stock(material_id, warehouse_id, quantity)
        TransactionService.create(
            direction="in", transaction_type="期初录入",
            material_id=material_id, warehouse_id=warehouse_id,
            quantity=quantity, unit_price=unit_price,
            operator_id=operator_id, remark=remark,
            initial_stock_id=rec.id,
        )
        return rec


class InboundService:

    @staticmethod
    def create(material_id, warehouse_id, quantity, operator_id,
               transaction_type="采购入库", unit_price=None, remark=None):
        InventoryService.add_stock(material_id, warehouse_id, quantity)
        return TransactionService.create(
            direction="in", transaction_type=transaction_type,
            material_id=material_id, warehouse_id=warehouse_id,
            quantity=quantity, unit_price=unit_price,
            operator_id=operator_id, remark=remark,
        )


class OutboundService:

    @staticmethod
    def create(material_id, warehouse_id, quantity, operator_id,
               transaction_type="生产领用", is_forced=False,
               forced_reason=None, remark=None, batch_no=None):
        current_stock = InventoryService.get_quantity(material_id, warehouse_id)
        stock_sufficient = current_stock >= quantity

        combined_remark = []
        if remark:
            combined_remark.append(remark)
        if is_forced and forced_reason:
            combined_remark.append(f"【强制出库】{forced_reason}")

        InventoryService.deduct_stock(material_id, warehouse_id, quantity)

        t = TransactionService.create(
            direction="out", transaction_type=transaction_type,
            material_id=material_id, warehouse_id=warehouse_id,
            quantity=quantity, operator_id=operator_id,
            batch_no=batch_no, is_forced=is_forced,
            remark="; ".join(combined_remark) if combined_remark else None,
        )
        return t, stock_sufficient


class StocktakeService:

    @staticmethod
    def create(warehouse_id, operator_id, remark=None):
        warehouse = db.session.get(Warehouse, warehouse_id)
        materials = Material.query.filter_by(
            warehouse_type=warehouse.code, is_active=True
        ).all()

        st = Stocktake(
            warehouse_id=warehouse_id, operator_id=operator_id,
            status="in_progress", remark=remark,
        )
        db.session.add(st)
        db.session.flush()

        invs = Inventory.query.filter_by(warehouse_id=warehouse_id).all()
        inv_map = {inv.material_id: inv.quantity for inv in invs}
        for m in materials:
            item = StocktakeItem(
                stocktake_id=st.id, material_id=m.id,
                book_quantity=inv_map.get(m.id, 0),
            )
            db.session.add(item)

        return st

    @staticmethod
    def complete(stocktake_id, actual_data):
        st = db.session.get(Stocktake, stocktake_id)
        if not st or st.status == "completed":
            return None

        st.status = "completed"

        for item_data in actual_data:
            item_id = item_data.get("item_id")
            actual_qty = item_data.get("actual_quantity")
            remark = item_data.get("remark", "")

            item = db.session.get(StocktakeItem, item_id)
            if not item or item.stocktake_id != stocktake_id:
                continue

            if actual_qty is None:
                continue  # 没填的项跳过，不调整库存

            item.actual_quantity = actual_qty
            item.remark = remark or None
            item.difference = actual_qty - item.book_quantity

            diff = item.difference
            if diff > 0:
                InventoryService.add_stock(item.material_id, st.warehouse_id, diff)
                TransactionService.create(
                    direction="in", transaction_type="盘盈入库",
                    material_id=item.material_id, warehouse_id=st.warehouse_id,
                    quantity=diff, operator_id=st.operator_id,
                    remark=f"盘点完成盘盈（盘点单 #{stocktake_id}）",
                )
            elif diff < 0:
                abs_diff = abs(diff)
                InventoryService.deduct_stock(item.material_id, st.warehouse_id, abs_diff)
                TransactionService.create(
                    direction="out", transaction_type="盘亏出库",
                    material_id=item.material_id, warehouse_id=st.warehouse_id,
                    quantity=abs_diff, operator_id=st.operator_id,
                    remark=f"盘点完成盘亏（盘点单 #{stocktake_id}）",
                )

        return st


class ImportService:

    @staticmethod
    def compute_hash(file_bytes):
        return sha256(file_bytes).hexdigest()

    @staticmethod
    def check_duplicate(file_hash):
        return ImportLog.query.filter_by(file_hash=file_hash).first()

    @staticmethod
    def generate_batch_no():
        today = datetime.now(BJ).strftime("%Y%m%d")
        prefix = f"IMP-{today}-"
        last = (
            ImportLog.query
            .filter(ImportLog.batch_no.like(f"{prefix}%"))
            .order_by(ImportLog.batch_no.desc())
            .first()
        )
        if last and last.batch_no:
            seq = int(last.batch_no.split("-")[-1]) + 1
        else:
            seq = 1
        return f"{prefix}{seq:03d}"

    @staticmethod
    def parse_excel(file_stream):
        import openpyxl
        wb = openpyxl.load_workbook(file_stream, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        current_order_no = None
        current_date = None

        for row in ws.iter_rows(values_only=True):
            values = list(row)
            if not any(v is not None for v in values):
                continue

            first = str(values[0] or "").strip()

            if "销售单号" in first or "产品名称" in first or "合计" in first:
                continue
            if "日期" in first:
                if len(values) > 1 and values[1]:
                    try:
                        from dateutil import parser as dt_parser
                        current_date = dt_parser.parse(str(values[1]))
                    except (ImportError, ValueError):
                        current_date = datetime.now(BJ)
                continue

            if first.startswith("NO") or first.startswith("XS") or first.replace("-", "").replace("/", "").isdigit():
                current_order_no = first
                continue

            if len(values) >= 3:
                product_name = str(values[0] or "").strip()
                qty = values[1] if len(values) > 1 else None
                price = values[2] if len(values) > 2 else None
                if product_name:
                    try:
                        qty_float = float(qty) if qty else 0
                    except (ValueError, TypeError):
                        qty_float = 0
                    try:
                        price_float = float(price) if price else None
                    except (ValueError, TypeError):
                        price_float = None
                    if qty_float > 0:
                        rows.append({
                            "order_no": current_order_no or "",
                            "sales_date": current_date,
                            "product_name": product_name,
                            "quantity": qty_float,
                            "unit_price": price_float,
                        })

        wb.close()
        return rows

    @staticmethod
    def auto_match(product_name):
        name = product_name.strip()
        if not name:
            return None

        m = Material.query.filter(
            Material.name == name, Material.is_active == True
        ).first()
        if m:
            return m

        mapping = SalesImportMapping.query.filter_by(external_name=name).first()
        if mapping:
            m = db.session.get(Material, mapping.material_id)
            if m and m.is_active:
                return m

        materials = Material.query.filter(
            Material.warehouse_type == "finished",
            Material.is_active == True,
        ).all()
        for m in materials:
            if m.name in name or name in m.name:
                return m

        keywords = re.split(r'[\s（(）)\-]', name)
        keywords = [k for k in keywords if len(k) >= 2]
        for kw in keywords:
            m = Material.query.filter(
                Material.name.contains(kw),
                Material.warehouse_type == "finished",
                Material.is_active == True,
            ).first()
            if m:
                return m

        return None

    @staticmethod
    def save_mapping(external_name, material_id):
        existing = SalesImportMapping.query.filter_by(external_name=external_name).first()
        if existing:
            existing.material_id = material_id
        else:
            mapping = SalesImportMapping(external_name=external_name, material_id=material_id)
            db.session.add(mapping)

    @staticmethod
    def bulk_resolve_pending(pending_ids, material_id, operator_id):
        warehouse = Warehouse.query.filter_by(code="finished").first()
        if not warehouse:
            return 0

        count = 0
        for pid in pending_ids:
            item = db.session.get(ImportPendingItem, pid)
            if not item or item.status != "pending":
                continue

            ImportService.save_mapping(item.external_name, material_id)
            InventoryService.deduct_stock(material_id, warehouse.id, item.quantity)
            TransactionService.create(
                direction="out", transaction_type="销售出库",
                material_id=material_id, warehouse_id=warehouse.id,
                quantity=item.quantity, unit_price=item.unit_price,
                operator_id=operator_id,
                batch_no=item.import_log.batch_no if item.import_log else None,
                remark=f"待处理补映射出库（来自待处理记录 #{pid}）",
            )
            item.material_id = material_id
            item.status = "resolved"
            item.resolved_at = datetime.now(BJ)
            count += 1

        db.session.commit()
        return count
