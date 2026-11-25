# -*- coding: utf-8 -*-
"""M01 基础数据管理：物料、客户、供应商、仓库库位、BOM"""
from flask import Blueprint, request
from db import get_conn, cursor, rows_to_dict, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("base_data", __name__, url_prefix="/api")

# 配置化：资源名 -> (表名, 可写字段, 唯一编码字段, 是否启用字段)
RESOURCES = {
    "materials":  ("material",  ["code","name","spec","category","unit","price_method",
                                 "standard_cost","safety_stock","is_batch","enabled"], "code", True),
    "customers":  ("customer",  ["code","name","contact","phone","address","settle_type",
                                 "credit_limit","price_level","enabled"], "code", True),
    "suppliers":  ("supplier",  ["code","name","contact","phone","supply_type",
                                 "pay_terms","qualified","enabled"], "code", True),
    "warehouses": ("warehouse", ["code","name","location","enabled"], "code", True),
}


@bp.route("/<resource>", methods=["GET"])
@handle_errors
def list_resource(resource):
    if resource not in RESOURCES:
        return fail("未知资源", 404)
    table = RESOURCES[resource][0]
    kw = request.args.get("keyword", "").strip()
    with get_conn() as conn, cursor(conn) as cur:
        where, params = "", []
        if kw:
            where = "WHERE name ILIKE %s OR code ILIKE %s"
            params = [f"%{kw}%", f"%{kw}%"]
        cur.execute(f"SELECT * FROM {table} {where} ORDER BY id", params)
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/<resource>", methods=["POST"])
@handle_errors
def save_resource(resource):
    if resource not in RESOURCES:
        return fail("未知资源", 404)
    table, fields, codefield, has_enabled = RESOURCES[resource]
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        values = [b.get(f) for f in fields]
        if has_enabled and b.get("id") is None:
            # 新增默认启用
            idx = fields.index("enabled")
            if values[idx] is None:
                values[idx] = True
        if b.get("id"):
            sets = ",".join(f"{f}=%s" for f in fields)
            cur.execute(f"UPDATE {table} SET {sets} WHERE id=%s", values + [b["id"]])
            rid = b["id"]
        else:
            cols = ",".join(fields)
            ph = ",".join(["%s"] * len(fields))
            cur.execute(f"INSERT INTO {table}({cols}) VALUES({ph}) RETURNING id", values)
            rid = cur.fetchone()["id"]
        write_log(cur, b.get("operator", "system"), "基础数据", "保存", f"{resource}:{b.get(codefield,'')}", request.remote_addr)
        return ok({"id": rid}, "保存成功")


@bp.route("/<resource>/<int:rid>", methods=["DELETE"])
@handle_errors
def delete_resource(resource, rid):
    if resource not in RESOURCES:
        return fail("未知资源", 404)
    table, _fields, codefield, _enabled = RESOURCES[resource]
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        # 1) 存在性校验：避免对不存在的记录误报"删除成功"
        cur.execute(f"SELECT {codefield} FROM {table} WHERE id=%s", (rid,))
        target = cur.fetchone()
        if not target:
            return fail("该记录不存在或已被删除", 404)

        # 2) 业务引用校验：有引用则禁止删除（可改用停用）
        checks = {
            "material": ["stock_balance","stock_ledger","purchase_order_item","sales_order_item","bom","bom_item"],
            "customer": ["sales_order"], "supplier": ["purchase_order"], "warehouse": ["stock_balance"],
        }
        for ref in checks.get(table, []):
            ref_col = ("material_id" if ref in ("stock_balance","stock_ledger","purchase_order_item",
                       "sales_order_item","bom_item") else "product_id" if ref=="bom" else
                       "customer_id" if table=="customer" else "supplier_id" if table=="supplier" else
                       "warehouse_id")
            cur.execute(f"SELECT 1 FROM {ref} WHERE {ref_col}=%s LIMIT 1", (rid,))
            if cur.fetchone():
                return fail(f"「{target[codefield]}」已被业务单据引用，不能删除（可改用「停用」）", code=3)

        # 3) 执行删除并记录审计日志
        cur.execute(f"DELETE FROM {table} WHERE id=%s", (rid,))
        write_log(cur, b.get("operator", "system"), "基础数据", "删除",
                  f"{resource}:{target[codefield]}(id={rid})", request.remote_addr)
        return ok(msg=f"已删除「{target[codefield]}」")


@bp.route("/<resource>/<int:rid>/toggle", methods=["POST"])
@handle_errors
def toggle_resource(resource, rid):
    """启用/停用基础数据（被引用记录无法删除时的替代方案）"""
    if resource not in RESOURCES:
        return fail("未知资源", 404)
    table, _fields, codefield, has_enabled = RESOURCES[resource]
    if not has_enabled:
        return fail("该资源不支持停用", code=3)
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute(f"SELECT {codefield},enabled FROM {table} WHERE id=%s", (rid,))
        row = cur.fetchone()
        if not row:
            return fail("该记录不存在或已被删除", 404)
        new_enabled = not bool(row["enabled"])
        cur.execute(f"UPDATE {table} SET enabled=%s WHERE id=%s", (new_enabled, rid))
        action = "启用" if new_enabled else "停用"
        write_log(cur, b.get("operator", "system"), "基础数据", action,
                  f"{resource}:{row[codefield]}(id={rid})", request.remote_addr)
        return ok({"enabled": new_enabled}, f"已{action}「{row[codefield]}」")


# ---------- 库位 ----------
@bp.route("/locations", methods=["GET"])
@handle_errors
def list_locations():
    with get_conn() as conn, cursor(conn) as cur:
        wid = request.args.get("warehouse_id")
        if wid:
            cur.execute("""SELECT l.*,w.name AS warehouse_name FROM location l
                           JOIN warehouse w ON w.id=l.warehouse_id WHERE l.warehouse_id=%s ORDER BY l.id""", (wid,))
        else:
            cur.execute("SELECT l.*,w.name AS warehouse_name FROM location l JOIN warehouse w ON w.id=l.warehouse_id ORDER BY l.id")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/locations", methods=["POST"])
@handle_errors
def save_location():
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        if b.get("id"):
            cur.execute("UPDATE location SET warehouse_id=%s,code=%s,name=%s,frozen=%s WHERE id=%s",
                        (b["warehouse_id"], b["code"], b["name"], bool(b.get("frozen")), b["id"]))
            lid = b["id"]
        else:
            cur.execute("INSERT INTO location(warehouse_id,code,name,frozen) VALUES(%s,%s,%s,%s) RETURNING id",
                        (b["warehouse_id"], b["code"], b["name"], bool(b.get("frozen"))))
            lid = cur.fetchone()["id"]
        return ok({"id": lid}, "保存成功")


# ---------- BOM ----------
@bp.route("/boms", methods=["GET"])
@handle_errors
def list_boms():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT b.*,m.name AS product_name,m.code AS product_code FROM bom b
                       JOIN material m ON m.id=b.product_id ORDER BY b.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/boms/<int:bom_id>", methods=["GET"])
@handle_errors
def get_bom(bom_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT b.*,m.name AS product_name FROM bom b JOIN material m ON m.id=b.product_id WHERE b.id=%s""", (bom_id,))
        head = cur.fetchone()
        if not head:
            return fail("BOM不存在", 404)
        cur.execute("""SELECT bi.*,m.code AS material_code,m.name AS material_name,m.unit
                       FROM bom_item bi JOIN material m ON m.id=bi.material_id WHERE bi.bom_id=%s ORDER BY bi.id""", (bom_id,))
        return ok({"head": dict(head), "items": rows_to_dict(cur.fetchall())})


@bp.route("/boms", methods=["POST"])
@handle_errors
def save_bom():
    b = body()
    items = b.get("items", [])
    with get_conn() as conn, cursor(conn) as cur:
        if b.get("id"):
            bid = b["id"]
            cur.execute("UPDATE bom SET product_id=%s,version=%s,qty_base=%s,effective_date=%s,enabled=%s WHERE id=%s",
                        (b["product_id"], b.get("version") or "V1", b.get("qty_base") or 1,
                         b.get("effective_date") or None, bool(b.get("enabled", True)), bid))
            cur.execute("DELETE FROM bom_item WHERE bom_id=%s", (bid,))
        else:
            cur.execute("""INSERT INTO bom(product_id,version,qty_base,effective_date,enabled)
                           VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                        (b["product_id"], b.get("version") or "V1", b.get("qty_base") or 1,
                         b.get("effective_date") or None, True))
            bid = cur.fetchone()["id"]
        for it in items:
            cur.execute("INSERT INTO bom_item(bom_id,material_id,qty,loss_rate) VALUES(%s,%s,%s,%s)",
                        (bid, it["material_id"], it["qty"], it.get("loss_rate") or 0))
        write_log(cur, b.get("operator", "system"), "基础数据", "保存BOM", str(b.get("product_id")), request.remote_addr)
        return ok({"id": bid}, "BOM保存成功")


@bp.route("/boms/<int:bom_id>", methods=["DELETE"])
@handle_errors
def delete_bom(bom_id):
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        # 存在性校验 + 取出产品名用于确认提示和日志
        cur.execute("""SELECT b.version,m.name AS product_name FROM bom b
                       JOIN material m ON m.id=b.product_id WHERE b.id=%s""", (bom_id,))
        target = cur.fetchone()
        if not target:
            return fail("该 BOM 不存在或已被删除", 404)
        # 统计将一并删除的子件数
        cur.execute("SELECT COUNT(*) AS n FROM bom_item WHERE bom_id=%s", (bom_id,))
        item_count = cur.fetchone()["n"]
        cur.execute("DELETE FROM bom_item WHERE bom_id=%s", (bom_id,))
        cur.execute("DELETE FROM bom WHERE id=%s", (bom_id,))
        write_log(cur, b.get("operator", "system"), "基础数据", "删除BOM",
                  f"{target['product_name']} {target['version']}(含{item_count}个子件)", request.remote_addr)
        return ok(msg=f"已删除 BOM「{target['product_name']} {target['version']}」及 {item_count} 个子件")
