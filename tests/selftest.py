# -*- coding: utf-8 -*-
"""
自动化测试
==========
用 Flask 的 test_client 跑完整流程，不需要真的起服务器。

    python tests/selftest.py
"""
import os
import sys
import tempfile

TMP_DB = os.path.join(tempfile.gettempdir(), "auth_test_%d.db" % os.getpid())
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
os.environ["AUTH_DB_PATH"] = TMP_DB  # 让 app.py 模块级的默认实例也写临时库，不污染工作目录
os.environ["AUTH_ADMIN_USER"] = "admin"
os.environ["AUTH_ADMIN_PASSWORD"] = "admin123"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from app import create_app  # noqa: E402
import models  # noqa: E402


class TestConfig(Config):
    DB_PATH = TMP_DB
    SECRET_KEY = "test-secret"
    TESTING = True
    MAX_FAILED_ATTEMPTS = 3  # 测试里用 3 次，跑得快
    LOCK_MINUTES = 15


app = create_app(TestConfig)

passed, failed = [], []


def check(name, cond, extra=""):
    if cond:
        passed.append(name)
        print("  PASS  %s" % name)
    else:
        failed.append(name)
        print("  FAIL  %s  %s" % (name, extra))


def login(client, username, password, remember=False):
    data = {"username": username, "password": password}
    if remember:
        data["remember"] = "1"
    return client.post("/auth/login", data=data, follow_redirects=False)


def run():
    # ---- 1. 未登录 ----
    c = app.test_client()
    r = c.get("/")
    check("未登录访问首页跳登录", r.status_code == 302 and "/auth/login" in r.headers["Location"])

    r = c.get("/auth/login")
    check("登录页可访问", r.status_code == 200)

    r = c.get("/auth/register")
    check("注册页可访问", r.status_code == 200)

    r = c.get("/auth/users")
    check("未登录访问用户列表跳登录", r.status_code == 302)

    # ---- 2. 管理员登录 ----
    r = login(c, "admin", "admin123")
    check("管理员登录成功重定向", r.status_code == 302 and "/auth/login" not in r.headers["Location"])

    r = c.get("/")
    check("登录后进面板", r.status_code == 200 and "你好" in r.get_data(as_text=True))

    r = c.get("/auth/users")
    body = r.get_data(as_text=True)
    check("管理员能看用户列表", r.status_code == 200 and "用户管理" in body)
    check("用户列表含登录记录", "登录记录" in body)

    # ---- 3. 注册（必须用未登录的 client，否则会被「已登录」重定向走） ----
    reg = app.test_client()
    r = reg.post("/auth/register", data={"username": "alice", "password": "alicepass1", "confirm": "alicepass1"})
    check("注册成功跳登录", r.status_code == 302 and "/auth/login" in r.headers["Location"])

    r = reg.post("/auth/register", data={"username": "bob", "password": "short", "confirm": "short"})
    check("密码太短被拒", r.status_code == 200 and "至少 8 位" in r.get_data(as_text=True))

    r = reg.post("/auth/register", data={"username": "a b", "password": "longenough1", "confirm": "longenough1"})
    check("用户名含空格被拒", "用户名只能是" in r.get_data(as_text=True))

    r = reg.post("/auth/register", data={"username": "alice", "password": "longenough1", "confirm": "longenough1"})
    check("重复用户名被拒", "已经被注册" in r.get_data(as_text=True))

    r = reg.post("/auth/register", data={"username": "carol", "password": "carolpass1", "confirm": "different1"})
    check("两次密码不一致被拒", "不一致" in r.get_data(as_text=True))

    # ---- 4. 开放重定向防护 ----
    c2 = app.test_client()
    r = c2.post("/auth/login", data={"username": "alice", "password": "alicepass1", "next": "//evil.com"})
    check("next=//evil.com 不回跳外站", r.headers.get("Location", "").startswith("/") and "evil.com" not in r.headers.get("Location", ""))

    c2b = app.test_client()  # 上一行已经登录了，换一个干净的 client
    r = c2b.post("/auth/login", data={"username": "alice", "password": "alicepass1", "next": "/auth/password"})
    check("next 站内路径正常回跳", r.headers.get("Location", "").endswith("/auth/password"))

    c2.get("/auth/logout")

    # ---- 5. 失败锁定 ----
    c3 = app.test_client()
    r = login(c3, "alice", "wrong-one")
    check("错误密码登录失败", "用户名或密码不对" in r.get_data(as_text=True))
    r = login(c3, "alice", "wrong-two")
    check("失败次数递增提示", "已失败 2 次" in r.get_data(as_text=True))
    r = login(c3, "alice", "wrong-three")
    check("达到上限后锁定", "锁定" in r.get_data(as_text=True))
    r = login(c3, "alice", "alicepass1")
    check("锁定期内正确密码也进不去", "锁定" in r.get_data(as_text=True))

    # 手动解锁，方便后面测
    conn = models.get_conn()
    conn.execute("UPDATE users SET locked_until = NULL, failed_attempts = 0 WHERE username='alice'")
    conn.commit()
    conn.close()

    # ---- 6. 普通用户权限 ----
    c4 = app.test_client()
    login(c4, "alice", "alicepass1")
    r = c4.get("/")
    check("普通用户能进面板", r.status_code == 200)

    r = c4.get("/auth/users")
    check("普通用户进用户列表 403", r.status_code == 403)

    # ---- 7. 改密码 ----
    r = c4.post("/auth/password", data={"old": "wrongold", "new": "newpass123", "confirm": "newpass123"})
    check("旧密码错误被拒", "旧密码不对" in r.get_data(as_text=True))

    r = c4.post("/auth/password", data={"old": "alicepass1", "new": "newpass123", "confirm": "newpass123"},
                follow_redirects=True)
    check("改密码成功", "密码已更新" in r.get_data(as_text=True))

    c4.get("/auth/logout")
    c5 = app.test_client()
    r = login(c5, "alice", "alicepass1")
    check("旧密码已失效", "用户名或密码不对" in r.get_data(as_text=True))
    r = login(c5, "alice", "newpass123")
    check("新密码可登录", r.status_code == 302)

    # ---- 8. 管理员禁用用户 ----
    r = c.get("/")
    alice = models.get_user_by_name("alice")
    r = c.post("/auth/users/%d/toggle" % alice["id"], follow_redirects=True)
    check("禁用成功", "已禁用" in r.get_data(as_text=True))

    r = c5.get("/")
    check("被禁用用户立刻掉线", r.status_code == 302 and "/auth/login" in r.headers["Location"])

    r = login(app.test_client(), "alice", "newpass123")
    check("被禁用账号无法登录", "禁用" in r.get_data(as_text=True))

    # 恢复
    c.post("/auth/users/%d/toggle" % alice["id"], follow_redirects=True)
    r = login(app.test_client(), "alice", "newpass123")
    check("启用后可以重新登录", r.status_code == 302)

    # ---- 9. 不能禁用自己 ----
    r = c.post("/auth/users/%d/toggle" % models.get_user_by_name("admin")["id"], follow_redirects=True)
    check("管理员不能禁用自己", "不能禁用自己" in r.get_data(as_text=True))

    # ---- 10. 记住我 ----
    c6 = app.test_client()
    login(c6, "admin", "admin123", remember=True)
    with c6.session_transaction() as s:
        check("勾记住我后 session 是 permanent", s.permanent is True)

    c7 = app.test_client()
    login(c7, "admin", "admin123")
    with c7.session_transaction() as s:
        check("不勾记住我 session 非 permanent", s.permanent is False)

    # ---- 11. 登出 ----
    r = c7.get("/auth/logout", follow_redirects=True)
    check("登出成功", "已经退出登录" in r.get_data(as_text=True))

    # ---- 12. 404 ----
    r = app.test_client().get("/no-such-page")
    check("404 页面", r.status_code == 404 and "404" in r.get_data(as_text=True))

    # ---- 13. 密码哈希 ----
    u = models.get_user_by_name("admin")
    h = u["password_hash"]
    check("密码是哈希不是明文", h != "admin123" and ":" in h and len(h) > 40)

    # ---- 14. 登录日志有记录 ----
    logs = models.recent_logins(200)
    check("登录日志有记录", len(logs) > 0)
    check("日志区分成功失败", any(l["ok"] for l in logs) and any(not l["ok"] for l in logs))

    print("\n%d passed, %d failed" % (len(passed), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    code = run()
    try:
        os.remove(TMP_DB)
    except OSError:
        pass
    sys.exit(code)
