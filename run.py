"""启动入口"""
import os
from app import create_app, db

app = create_app()


def init_db():
    # 确保数据库目录存在（PyInstaller 打包后 __file__ 在 _internal 里）
    import os, sys
    if getattr(sys, "frozen", False):
        db_dir = os.path.join(os.path.dirname(sys.executable), "instance")
    else:
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
    os.makedirs(db_dir, exist_ok=True)

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
    # 启动前自动备份数据库
    try:
        from backup import backup
        backup()
    except Exception:
        pass

    with app.app_context():
        init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
