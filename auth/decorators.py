# -*- coding: utf-8 -*-
"""
权限装饰器
==========
没用 Flask-Login，登录态就是一个 session["uid"]。
少一个依赖，且客户想看「登录到底怎么实现的」时，只有不到 40 行。

规矩：
  - session 里只存用户 id，不存用户名/权限，每次请求都回数据库查一遍
    （这样管理员禁用某人后，对方下一个请求就立刻失效）
  - 账号被禁用时直接清 session
"""
from functools import wraps

from flask import abort, redirect, request, session, url_for

import models


def current_user():
    """返回当前登录用户的行对象，没登录返回 None。"""
    uid = session.get("uid")
    if not uid:
        return None
    user = models.get_user(uid)
    if user is None or not user["is_active"]:
        session.clear()
        return None
    return user


def _next_url():
    """登录后回跳的原地址。只接受站内路径，避免开放重定向。"""
    target = request.path
    if request.query_string:
        target += "?" + request.query_string.decode("utf-8", "ignore")
    return target


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=_next_url()))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=_next_url()))
        if not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapper
