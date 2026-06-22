from flask import Blueprint, jsonify, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User

api_auth_bp = Blueprint("api_auth", __name__)


@api_auth_bp.route("/auth/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "data": {
            "id": current_user.id,
            "username": current_user.username,
            "display_name": current_user.display_name,
            "is_admin": current_user.is_admin,
        }
    })


@api_auth_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求数据为空"}), 400
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "用户名或密码错误"}), 401
    login_user(user)
    return jsonify({
        "data": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
        }
    })


@api_auth_bp.route("/auth/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"data": "ok"})
