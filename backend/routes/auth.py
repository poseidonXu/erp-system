# -*- coding: utf-8 -*-
"""认证、用户/角色、操作日志、系统参数"""
from flask import Blueprint, g, request
from db import get_conn, cursor, rows_to_dict, write_log
from util import ok, fail, body, sha256, handle_errors

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.route("/login", methods=["POST"])
@handle_errors
def login():
    b = body()
    username = b.get("username", "").strip()
    password = b.get("password", "")
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute(
            "SELECT id,username,real_name,role,dept_id,enabled FROM sys_user WHERE username=%s AND password=%s",
            (username, sha256(password)),
        )
        r = cur.fetchone()
        if not r:
            return fail("用户名或密码错误", code=401)
        if not r["enabled"]:
            return fail("账号已停用", code=403)
        user = dict(r)
        cur.execute("UPDATE sys_user SET last_login=NOW() WHERE id=%s", (user["id"],))
        write_log(cur, username, "系统", "登录", "用户登录成功", request.remote_addr)
        return ok(user, "登录成功")


@bp.route("/users", methods=["GET"])
@handle_errors
def list_users():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT u.id,u.username,u.real_name,u.role,u.enabled,u.last_login,d.name AS dept
                       FROM sys_user u LEFT JOIN department d ON d.id=u.dept_id ORDER BY u.id""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/users", methods=["POST"])
@handle_errors
def save_user():
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        if b.get("id"):
            cur.execute("""UPDATE sys_user SET real_name=%s,role=%s,dept_id=%s,enabled=%s WHERE id=%s""",
                        (b.get("real_name"), b.get("role"), b.get("dept_id") or None,
                         bool(b.get("enabled", True)), b["id"]))
            if b.get("password"):
                cur.execute("UPDATE sys_user SET password=%s WHERE id=%s", (sha256(b["password"]), b["id"]))
            uid = b["id"]
        else:
            cur.execute("""INSERT INTO sys_user(username,password,real_name,role,dept_id,enabled)
                           VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (b["username"], sha256(b.get("password") or "123456"), b.get("real_name"),
                         b.get("role", "viewer"), b.get("dept_id") or None, True))
            uid = cur.fetchone()["id"]
        write_log(cur, b.get("operator", "admin"), "系统", "保存用户", b.get("username", ""), request.remote_addr)
        return ok({"id": uid}, "保存成功")


@bp.route("/departments", methods=["GET"])
@handle_errors
def list_departments():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT id,code,name FROM department ORDER BY id")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/logs", methods=["GET"])
@handle_errors
def list_logs():
    limit = min(int(request.args.get("limit", 100)), 500)
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute(f"SELECT * FROM operation_log ORDER BY id DESC LIMIT {limit}")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/params", methods=["GET"])
@handle_errors
def list_params():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT param_key,param_value,remark FROM sys_param ORDER BY param_key")
        return ok(rows_to_dict(cur.fetchall()))
