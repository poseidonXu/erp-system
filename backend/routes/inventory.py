# -*- coding: utf-8 -*-
"""M03 库存管理：库存结存、出入库流水、预警、调拨、盘点"""
from flask import Blueprint, request
from db import get_conn, cursor, rows_to_dict, next_no, post_stock, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("inventory", __name__, url_prefix="/api")


@bp.route("/stock", methods=["GET"])
@handle_errors
def stock_balance():
    with get_conn() as conn, cursor(conn) as cur:
        kw = request.args.get("keyword", "").strip()
        where, params = "", []
        if kw:
            where = "WHERE m.name ILIKE %s OR m.code ILIKE %s"
            params = [f"%{kw}%", f"%{kw}%"]
        cur.execute(f"""SELECT sb.*,m.code AS material_code,m.name AS material_name,m.unit,m.safety_stock,
                        w.name AS warehouse_name,l.name AS location_name,
                        ROUND(sb.qty*sb.avg_cost,2) AS amount
                        FROM stock_balance sb JOIN material m ON m.id=sb.material_id
                        JOIN warehouse w ON w.id=sb.warehouse_id
                        LEFT JOIN location l ON l.id=sb.location_id {where}
                        ORDER BY sb.material_id""", params)
        data = rows_to_dict(cur.fetchall())
        for d in data:
            d["warning"] = float(d["qty"]) < float(d["safety_stock"])
        return ok(data)


@bp.route("/stock/ledger", methods=["GET"])
@handle_errors
def stock_ledger():
    with get_conn() as conn, cursor(conn) as cur:
        clauses, params = [], []
        mid = request.args.get("material_id")
        doc = request.args.get("doc_no")
        start = request.args.get("start")
        end = request.args.get("end")
        if mid:
            clauses.append("l.material_id=%s"); params.append(mid)
        if doc:
            clauses.append("l.doc_no ILIKE %s"); params.append(f"%{doc}%")
        if start:
            clauses.append("l.created_at>=%s"); params.append(start)
        if end:
            clauses.append("l.created_at<=%s"); params.append(end + " 23:59:59")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        cur.execute(f"""SELECT l.*,m.code AS material_code,m.name AS material_name,m.unit
                        FROM stock_ledger l JOIN material m ON m.id=l.material_id {where}
                        ORDER BY l.id DESC LIMIT 1000""", params)
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/stock/adjust", methods=["POST"])
@handle_errors
def stock_adjust():
    """其他出入库（手工调整），如盘盈盘亏"""
    b = body()
    qty = float(b.get("qty", 0))
    if qty == 0:
        return fail("数量不能为0")
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT id FROM warehouse WHERE code='WH01' LIMIT 1")
        wr = cur.fetchone()
        wh = b.get("warehouse_id") or (wr["id"] if wr else 1)
        post_stock(cur, doc_type=b.get("doc_type") or ("盘盈入库" if qty > 0 else "盘亏出库"),
                   doc_no=b.get("doc_no") or next_no(cur, "ADJ", "stock_ledger", "doc_no"),
                   material_id=b["material_id"], warehouse_id=wh, qty=qty,
                   cost=float(b.get("cost") or 0), operator=b.get("operator", "system"),
                   remark=b.get("remark", "手工调整"))
        write_log(cur, b.get("operator", "system"), "库存", "库存调整", str(b["material_id"]), request.remote_addr)
        return ok(msg="库存调整成功")


@bp.route("/transfers", methods=["GET"])
@handle_errors
def list_transfers():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT t.*,m.name AS material_name,f.name AS from_name,to.name AS to_name
                       FROM stock_transfer t JOIN material m ON m.id=t.material_id
                       JOIN warehouse f ON f.id=t.from_wh JOIN warehouse to ON to.id=t.to_wh ORDER BY t.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/transfers", methods=["POST"])
@handle_errors
def save_transfer():
    b = body()
    qty = float(b.get("qty", 0))
    with get_conn() as conn, cursor(conn) as cur:
        no = next_no(cur, "TR", "stock_transfer", "transfer_no")
        cur.execute("""INSERT INTO stock_transfer(transfer_no,material_id,from_wh,to_wh,qty,operator)
                       VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (no, b["material_id"], b["from_wh"], b["to_wh"], qty, b.get("operator", "system")))
        tid = cur.fetchone()["id"]
        if b.get("execute") and b["status"] == "confirmed":
            do_transfer(cur, tid)
        return ok({"id": tid, "transfer_no": no}, "调拨单保存成功")


def do_transfer(cur, tid):
    cur.execute("SELECT * FROM stock_transfer WHERE id=%s", (tid,))
    t = cur.fetchone()
    if not t or t["status"] == "done":
        return False
    cur.execute("SELECT COALESCE(AVG(avg_cost),0) c FROM stock_balance WHERE material_id=%s", (t["material_id"],))
    cost = float(cur.fetchone()["c"])
    post_stock(cur, doc_type="调拨出库", doc_no=t["transfer_no"], material_id=t["material_id"],
               warehouse_id=t["from_wh"], qty=-float(t["qty"]), cost=cost, remark="调出")
    post_stock(cur, doc_type="调拨入库", doc_no=t["transfer_no"], material_id=t["material_id"],
               warehouse_id=t["to_wh"], qty=float(t["qty"]), cost=cost, remark="调入")
    cur.execute("UPDATE stock_transfer SET status='done' WHERE id=%s", (tid,))
    return True


@bp.route("/transfers/<int:tid>/confirm", methods=["POST"])
@handle_errors
def confirm_transfer(tid):
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        if not do_transfer(cur, tid):
            return fail("调拨单不存在或已执行")
        write_log(cur, b.get("operator", "system"), "库存", "执行调拨", str(tid), request.remote_addr)
        return ok(msg="调拨执行成功")


@bp.route("/counts", methods=["GET"])
@handle_errors
def list_counts():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT c.*,m.name AS material_name,w.name AS warehouse_name FROM stock_count c
                       JOIN material m ON m.id=c.material_id JOIN warehouse w ON w.id=c.warehouse_id ORDER BY c.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/counts", methods=["POST"])
@handle_errors
def save_count():
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        no = next_no(cur, "PD", "stock_count", "count_no")
        from db import available_qty
        book = available_qty(cur, b["material_id"], b.get("warehouse_id"))
        actual = float(b.get("actual_qty", 0))
        cur.execute("""INSERT INTO stock_count(count_no,material_id,warehouse_id,book_qty,actual_qty,diff_qty,operator)
                       VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (no, b["material_id"], b.get("warehouse_id"), book, actual,
                     round(actual - book, 3), b.get("operator", "system")))
        cid = cur.fetchone()["id"]
        return ok({"id": cid, "count_no": no, "book_qty": book, "diff_qty": round(actual - book, 3)}, "盘点单保存成功")


@bp.route("/counts/<int:cid>/confirm", methods=["POST"])
@handle_errors
def confirm_count(cid):
    """盘点差异确认：按差异调整账面库存"""
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM stock_count WHERE id=%s", (cid,))
        c = cur.fetchone()
        if not c or c["status"] != "draft":
            return fail("盘点单不存在或已确认")
        diff = float(c["diff_qty"])
        if diff != 0:
            post_stock(cur, doc_type="盘盈入库" if diff > 0 else "盘亏出库", doc_no=c["count_no"],
                       material_id=c["material_id"], warehouse_id=c["warehouse_id"], qty=diff,
                       operator=b.get("operator", "system"), remark="盘点差异调整")
        cur.execute("UPDATE stock_count SET status='confirmed' WHERE id=%s", (cid,))
        write_log(cur, b.get("operator", "system"), "库存", "盘点确认", c["count_no"], request.remote_addr)
        return ok(msg="盘点已确认，库存已调整")
