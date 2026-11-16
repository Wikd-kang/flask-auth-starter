# -*- coding: utf-8 -*-
"""认证模块：蓝图 + 权限装饰器。"""
from .decorators import current_user, login_required, admin_required  # noqa: F401
from .routes import bp as auth_bp  # noqa: F401
