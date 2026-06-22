from flask import Blueprint


def register_api_blueprints(app):
    """Register all API blueprints and exempt from CSRF."""
    from app import csrf

    from app.routes.api.auth import api_auth_bp
    from app.routes.api.materials import api_materials_bp
    from app.routes.api.dashboard import api_dashboard_bp
    from app.routes.api.inbounds import api_inbounds_bp
    from app.routes.api.outbounds import api_outbounds_bp
    from app.routes.api.inventory import api_inventory_bp
    from app.routes.api.stocktake import api_stocktake_bp
    from app.routes.api.initial_stock import api_initial_stock_bp
    from app.routes.api.sales_import import api_sales_import_bp

    blueprints = [
        api_auth_bp,
        api_materials_bp,
        api_dashboard_bp,
        api_inbounds_bp,
        api_outbounds_bp,
        api_inventory_bp,
        api_stocktake_bp,
        api_initial_stock_bp,
        api_sales_import_bp,
    ]

    for bp in blueprints:
        csrf.exempt(bp)
        app.register_blueprint(bp, url_prefix="/api")
