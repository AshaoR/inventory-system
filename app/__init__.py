from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")

    import os
    os.makedirs(app.instance_path, exist_ok=True)

    # 启用 SQLite WAL 模式提升并发性能
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录系统"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.materials import materials_bp
    from app.routes.inbounds import inbounds_bp
    from app.routes.outbounds import outbounds_bp
    from app.routes.inventory import inventory_bp
    from app.routes.stocktake import stocktake_bp
    from app.routes.initial_stock import initial_stock_bp
    from app.routes.sales_import import sales_import_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(inbounds_bp)
    app.register_blueprint(outbounds_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(stocktake_bp)
    app.register_blueprint(initial_stock_bp)
    app.register_blueprint(sales_import_bp)

    @app.context_processor
    def inject_user():
        from flask_login import current_user
        return {"current_user": current_user}

    @app.template_filter("qty")
    def format_quantity(value):
        if value is None:
            return "0"
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    @app.template_filter("local")
    def to_local_time(dt):
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M")

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("errors/500.html"), 500

    return app
