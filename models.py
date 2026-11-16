# -*- coding: utf-8 -*-
"""
数据层
======
两张表：
  users      —— 账号、密码哈希、权限、防爆破计数、最后登录信息
  login_log  —— 每次登录尝试都记一条，管理员能看到谁在什么时候从哪登的

这里刻意不引入 ORM：项目小，手写 SQL 更好读，客户后续想换 SQLAlchemy 也方便。
"""
import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AUTH_DB_PATH") or os.path.join(BASE_DIR, "auth.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    is_admin       INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT    NOT NULL,
    last_login_at  TEXT,
    last_login_ip  TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until   TEXT
);

CREATE TABLE IF NOT EXISTS login_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    username   TEXT    NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    ok         INTEGER NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_created ON login_log (created_at DESC);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# 用户
# --------------------------------------------------------------------------
def create_user(username, password_hash, is_admin=0):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at) "
            "VALUES (?, ?, ?, ?)",
            (username, password_hash, is_admin, _now_str()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_name(username):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()


def get_user(uid):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()


def list_users():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    finally:
        conn.close()


def count_users():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def update_password_hash(uid, password_hash):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, uid))
        conn.commit()
    finally:
        conn.close()


def set_active(uid, active):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, uid))
        conn.commit()
    finally:
        conn.close()


def record_login_success(uid, ip):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
            "last_login_at = ?, last_login_ip = ? WHERE id = ?",
            (_now_str(), ip, uid),
        )
        conn.commit()
    finally:
        conn.close()


def record_login_failure(uid, max_failed, lock_minutes):
    """失败计数 +1，达到上限就锁定一段时间。返回 (失败次数, 锁定到什么时候)。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT failed_attempts FROM users WHERE id = ?", (uid,)).fetchone()
        attempts = (row["failed_attempts"] if row else 0) + 1
        locked_until = None
        if attempts >= max_failed:
            locked_until = (datetime.now() + timedelta(minutes=lock_minutes)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            attempts = 0  # 锁定期内重新计数
        conn.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (attempts, locked_until, uid),
        )
        conn.commit()
        return attempts, locked_until
    finally:
        conn.close()


def is_locked(user):
    """当前账号是否还在锁定期内。"""
    if not user or not user["locked_until"]:
        return False
    try:
        return datetime.strptime(user["locked_until"], "%Y-%m-%d %H:%M:%S") > datetime.now()
    except ValueError:
        return False


# --------------------------------------------------------------------------
# 登录日志
# --------------------------------------------------------------------------
def add_login_log(user_id, username, ip, user_agent, ok):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO login_log (user_id, username, ip, user_agent, ok, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, ip, (user_agent or "")[:200], 1 if ok else 0, _now_str()),
        )
        conn.commit()
    finally:
        conn.close()


def recent_logins(limit=50):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM login_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
