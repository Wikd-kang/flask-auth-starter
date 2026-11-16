# -*- coding: utf-8 -*-
"""
认证路由
========
/register  注册
/login     登录（失败会累计次数，达到上限锁定一段时间）
/logout    登出
/password  修改密码（要求输入旧密码）
/users     用户列表（仅管理员）
"""
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import models
from .decorators import admin_required, current_user, login_required

bp = Blueprint("auth", __name__, url_prefix="/auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$")


def _safe_next(raw):
    """只允许站内相对路径，挡掉 //evil.com 和 http://evil.com 这类开放重定向。"""
    if not raw:
        return None
    if raw.startswith("/") and not raw.startswith("//") and "\\" not in raw:
        return raw
    return None


def _validate_username(username):
    cfg = current_app.config
    if not username:
        return "请填用户名"
    if not USERNAME_RE.match(username):
        return "用户名只能是 3–20 位的中英文、数字或下划线"
    if models.get_user_by_name(username):
        return "这个用户名已经被注册了"
    return None


def _validate_password(password, confirm=None):
    cfg = current_app.config
    if not password:
        return "请填密码"
    if len(password) < cfg["PASSWORD_MIN"]:
        return "密码至少 %d 位" % cfg["PASSWORD_MIN"]
    if confirm is not None and password != confirm:
        return "两次输入的密码不一致"
    return None


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------
@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("dashboard"))

    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = _validate_username(username) or _validate_password(password, confirm)
        if not error:
            # 第一个注册的人是管理员，省去手改数据库
            is_first = models.count_users() == 0
            models.create_user(username, generate_password_hash(password), is_admin=1 if is_first else 0)
            flash("注册成功，请登录" + ("（你是第一个用户，已自动获得管理员权限）" if is_first else ""), "ok")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", error=error, username=username)


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        nxt = _safe_next(request.form.get("next") or request.args.get("next"))
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        ua = request.headers.get("User-Agent", "")

        cfg = current_app.config
        user = models.get_user_by_name(username)

        if user is None:
            # 账号不存在和密码错误给同一个提示，避免被拿来枚举用户名
            models.add_login_log(None, username, ip, ua, 0)
            error = "用户名或密码不对"
        elif models.is_locked(user):
            models.add_login_log(user["id"], username, ip, ua, 0)
            error = "失败次数太多，账号暂时锁定，请 %d 分钟后再试" % cfg["LOCK_MINUTES"]
        elif not user["is_active"]:
            models.add_login_log(user["id"], username, ip, ua, 0)
            error = "这个账号已被管理员禁用"
        elif not check_password_hash(user["password_hash"], password):
            attempts, locked_until = models.record_login_failure(
                user["id"], cfg["MAX_FAILED_ATTEMPTS"], cfg["LOCK_MINUTES"]
            )
            models.add_login_log(user["id"], username, ip, ua, 0)
            if locked_until:
                error = "失败次数太多，账号已锁定 %d 分钟" % cfg["LOCK_MINUTES"]
            else:
                error = "用户名或密码不对（已失败 %d 次，连续 %d 次会锁定）" % (
                    attempts,
                    cfg["MAX_FAILED_ATTEMPTS"],
                )
        else:
            models.record_login_success(user["id"], ip)
            models.add_login_log(user["id"], username, ip, ua, 1)
            session.clear()
            session["uid"] = user["id"]
            session.permanent = remember  # 勾了「记住我」才有 7 天有效期
            return redirect(nxt or url_for("dashboard"))

    return render_template("auth/login.html", error=error, username=username,
                           next=request.args.get("next", ""))


# --------------------------------------------------------------------------
# 登出
# --------------------------------------------------------------------------
@bp.route("/logout")
def logout():
    session.clear()
    flash("已经退出登录", "ok")
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
# 修改密码
# --------------------------------------------------------------------------
@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    user = current_user()
    error = None
    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")

        if not check_password_hash(user["password_hash"], old):
            error = "旧密码不对"
        else:
            error = _validate_password(new, confirm)
            if not error and new == old:
                error = "新密码不能和旧密码一样"

        if not error:
            models.update_password_hash(user["id"], generate_password_hash(new))
            flash("密码已更新", "ok")
            return redirect(url_for("dashboard"))

    return render_template("auth/change_password.html", error=error)


# --------------------------------------------------------------------------
# 用户列表（管理员）
# --------------------------------------------------------------------------
@bp.route("/users")
@admin_required
def users():
    return render_template(
        "auth/users.html",
        users=models.list_users(),
        logs=models.recent_logins(30),
    )


@bp.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_user(uid):
    me = current_user()
    if uid == me["id"]:
        flash("不能禁用自己", "err")
        return redirect(url_for("auth.users"))
    target = models.get_user(uid)
    if target is None:
        abort(404)
    models.set_active(uid, not target["is_active"])
    flash("已%s用户 %s" % ("禁用" if target["is_active"] else "启用", target["username"]), "ok")
    return redirect(url_for("auth.users"))
