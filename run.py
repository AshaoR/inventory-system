"""启动入口"""
import os
from app import create_app, db

app = create_app()


def init_db():
    from app.models import User, Warehouse

    db.create_all()

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", display_name="管理员", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)

    if not User.query.filter_by(username="operator").first():
        op = User(username="operator", display_name="仓管员", is_admin=False)
        op.set_password("operator123")
        db.session.add(op)

    if not Warehouse.query.first():
        warehouses = [
            Warehouse(name="成品仓", code="finished"),
            Warehouse(name="半成品仓", code="semi"),
            Warehouse(name="原材料仓", code="raw"),
        ]
        db.session.add_all(warehouses)

    db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
