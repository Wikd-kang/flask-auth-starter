# -*- coding: utf-8 -*-
"""配置：所有可调参数集中在这里，改行为不用翻代码。"""
import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # 生产环境必须用环境变量覆盖，否则重启后所有人的登录态都会失效
    SECRET_KEY = os.environ.get("AUTH_SECRET_KEY") or "dev-only-please-change-me"

    DB_PATH = os.environ.get("AUTH_DB_PATH") or os.path.join(BASE_DIR, "auth.db")

    # 会话 7 天过期；没勾「记住我」的会话关浏览器就没
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # 防爆破：连续失败 5 次锁 15 分钟
    MAX_FAILED_ATTEMPTS = 5
    LOCK_MINUTES = 15

    # 用户名 / 密码规则
    USERNAME_MIN = 3
    USERNAME_MAX = 20
    PASSWORD_MIN = 8
