# -*- coding: utf-8 -*-
"""
应用工厂
========
用 create_app() 而不是模块级 app，好处是测试时能传一份测试配置进去，
两个 app 实例互不影响。Flask 官方推荐的写法。

跑起来：
    python app.py
"""
import os

from flask import Flask, redirect, render_template, session, url_for
from werkzeug.security import generate_password_hash

import models
from auth import auth_bp, current_user, login_required
from config import Config


def _bootstrap_admin(app):
    """一个用户都没有时，建一个管理员，省得手动插数据库。"""
    if models.count_users() > 0:
        return
    username = os.environ.get("AUTH_ADMIN_USER", "admin")
    password = os.environ.get("AUTH_ADMIN_PASSWORD", "admin123")
    models.create_user(username, generate_password_hash(password), is_admin=1)
    print(" * 已创建管理员账号：%s / %s（上线前请改掉）" % (username, password))


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # models.py 不依赖 Flask，这里把配置里的库路径塞给它
    models.DB_PATH = app.config["DB_PATH"]
    models.init_db()
    _bootstrap_admin(app)

    app.register_blueprint(auth_bp)

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user()}

    # ------------------------------------------------------------------
    # 业务演示页：换成客户自己的首页就行
    # ------------------------------------------------------------------
    @app.route("/")
    @login_required
    def dashboard():
        user = current_user()
        from models import recent_logins

        mine = [l for l in recent_logins(200) if l["user_id"] == user["id"]][:10]
        return render_template("dashboard.html", logs=mine)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
