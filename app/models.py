from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

BJ = timezone(timedelta(hours=8))


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Warehouse(db.Model):
    __tablename__ = "warehouses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)


class Material(db.Model):
    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    spec = db.Column(db.String(200), nullable=True)
    unit = db.Column(db.String(20), nullable=False, default="个")
    warehouse_type = db.Column(db.String(20), nullable=False)  # finished/semi/raw
    category = db.Column(db.String(100), nullable=True)
    min_stock = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(BJ),
        onupdate=lambda: datetime.now(BJ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "spec": self.spec or "",
            "unit": self.unit,
            "warehouse_type": self.warehouse_type,
            "category": self.category or "",
            "min_stock": self.min_stock,
            "is_active": self.is_active,
        }


class Inventory(db.Model):
    __tablename__ = "inventory"

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(BJ),
        onupdate=lambda: datetime.now(BJ),
    )

    __table_args__ = (
        db.UniqueConstraint("material_id", "warehouse_id"),
        db.Index("ix_inventory_warehouse_id", "warehouse_id"),
    )

    material = db.relationship("Material", lazy="joined")
    warehouse = db.relationship("Warehouse", lazy="joined")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    direction = db.Column(db.String(3), nullable=False)  # "in" / "out"
    transaction_type = db.Column(db.String(20), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    batch_no = db.Column(db.String(50), nullable=True, index=True)
    is_forced = db.Column(db.Boolean, default=False)
    initial_stock_id = db.Column(db.Integer, db.ForeignKey("initial_stock.id"), nullable=True)
    remark = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    material = db.relationship("Material", lazy="joined")
    warehouse = db.relationship("Warehouse", lazy="joined")
    operator = db.relationship("User", lazy="joined")

    __table_args__ = (
        db.Index("ix_transaction_material_id", "material_id"),
        db.Index("ix_transaction_warehouse_id", "warehouse_id"),
        db.Index("ix_transaction_direction", "direction"),
    )


class Stocktake(db.Model):
    __tablename__ = "stocktakes"

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="in_progress")  # in_progress / completed
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))
    remark = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    warehouse = db.relationship("Warehouse", lazy="joined")
    operator = db.relationship("User", lazy="joined")
    items = db.relationship("StocktakeItem", back_populates="stocktake", lazy="select")


class StocktakeItem(db.Model):
    __tablename__ = "stocktake_items"

    id = db.Column(db.Integer, primary_key=True)
    stocktake_id = db.Column(db.Integer, db.ForeignKey("stocktakes.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    book_quantity = db.Column(db.Float, default=0)
    actual_quantity = db.Column(db.Float, nullable=True)
    difference = db.Column(db.Float, default=0)
    remark = db.Column(db.Text, nullable=True)

    stocktake = db.relationship("Stocktake", back_populates="items")
    material = db.relationship("Material", lazy="joined")


class InitialStock(db.Model):
    __tablename__ = "initial_stock"

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    remark = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    material = db.relationship("Material", lazy="joined")
    warehouse = db.relationship("Warehouse", lazy="joined")
    operator = db.relationship("User", lazy="joined")


class ImportLog(db.Model):
    __tablename__ = "import_logs"

    id = db.Column(db.Integer, primary_key=True)
    file_hash = db.Column(db.String(64), nullable=False, unique=True)
    file_name = db.Column(db.String(255), nullable=False)
    row_count = db.Column(db.Integer, default=0)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    batch_no = db.Column(db.String(50), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    operator = db.relationship("User", lazy="joined")


class SalesImportMapping(db.Model):
    __tablename__ = "sales_import_mapping"

    id = db.Column(db.Integer, primary_key=True)
    external_name = db.Column(db.String(200), unique=True, nullable=False, index=True)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    material = db.relationship("Material", lazy="joined")


class ImportPendingItem(db.Model):
    __tablename__ = "import_pending_items"

    id = db.Column(db.Integer, primary_key=True)
    import_log_id = db.Column(db.Integer, db.ForeignKey("import_logs.id"), nullable=False)
    external_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    sales_date = db.Column(db.DateTime, nullable=True)
    order_no = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending / resolved / ignored
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BJ))

    import_log = db.relationship("ImportLog", lazy="joined")
    material = db.relationship("Material", lazy="joined")
