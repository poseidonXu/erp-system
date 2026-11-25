# -*- coding: utf-8 -*-
"""M02 采购管理：采购订单 -> 确认 -> 到货入库 -> 应付
业务闭环：入库同时写库存分类账 + 生成应付账 + 凭证
"""
from flask import Blueprint, request
from db import get_conn, cursor, rows_to_dict, next_no, post_stock, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("purchase", __name__, url_prefix="/api")


@bp.route("/purchase-orders", methods=["GET"])
@handle_errors
def list_po():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT po.*,s.name AS supplier_name,w.name AS warehouse_name
                       FROM purchase_order po JOIN supplier s ON s.id=po.supplier_id
                       JOIN warehouse w ON w.id=po.warehouse_id
                       ORDER BY po.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/purchase-orders/<int:po_id>", methods=["GET"])
@handle_errors
def get_po(po_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT po.*,s.name AS supplier_name,w.name AS warehouse_name
                       FROM purchase_order po JOIN supplier s ON s.id=po.supplier_id
                       JOIN warehouse w ON w.id=po.warehouse_id WHERE po.id=%s""", (po_id,))
        head = cur.fetchone()
        if not head:
            return fail("订单不存在", 404)
        cur.execute("""SELECT i.*,m.code AS material_code,m.name AS material_name,m.unit
                       FROM purchase_order_item i JOIN material m ON m.id=i.material_id
                       WHERE i.po_id=%s ORDER BY i.id""", (po_id,))
        return ok({"head": dict(head), "items": rows_to_dict(cur.fetchall())})


@bp.route("/purchase-orders", methods=["POST"])
@handle_errors
def save_po():
    b = body()
    items = b.get("items", [])
    if not items:
        return fail("请至少添加一条明细")
    with get_conn() as conn, cursor(conn) as cur:
        total_qty = sum(float(i["qty"]) for i in items)
        total_amt = sum(float(i["qty"]) * float(i["price"]) for i in items)
        if b.get("id"):
            po_id = b["id"]
            cur.execute("""UPDATE purchase_order SET supplier_id=%s,warehouse_id=%s,need_date=%s,
                           total_qty=%s,total_amt=%s WHERE id=%s AND status='draft'""",
                        (b["supplier_id"], b["warehouse_id"], b.get("need_date") or None,
                         total_qty, round(total_amt, 2), po_id))
            cur.execute("DELETE FROM purchase_order_item WHERE po_id=%s", (po_id,))
        else:
            po_no = next_no(cur, "PO", "purchase_order", "po_no")
            cur.execute("""INSERT INTO purchase_order(po_no,supplier_id,warehouse_id,need_date,total_qty,total_amt,creator)
                           VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (po_no, b["supplier_id"], b["warehouse_id"], b.get("need_date") or None,
                         total_qty, round(total_amt, 2), b.get("operator", "system")))
            po_id = cur.fetchone()["id"]
        for i in items:
            cur.execute("""INSERT INTO purchase_order_item(po_id,material_id,qty,price,amount)
                           VALUES(%s,%s,%s,%s,%s)""",
                        (po_id, i["material_id"], i["qty"], i["price"],
                         round(float(i["qty"]) * float(i["price"]), 2)))
        write_log(cur, b.get("operator", "system"), "采购", "保存订单", f"PO#{po_id}", request.remote_addr)
        return ok({"id": po_id}, "采购订单保存成功")


@bp.route("/purchase-orders/<int:po_id>/confirm", methods=["POST"])
@handle_errors
def confirm_po(po_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("UPDATE purchase_order SET status='confirmed' WHERE id=%s AND status='draft'", (po_id,))
        if cur.rowcount == 0:
            return fail("只有草稿订单可以确认")
        return ok(msg="订单已确认")


@bp.route("/purchase-orders/<int:po_id>/receive", methods=["POST"])
@handle_errors
def receive_po(po_id):
    """到货入库：可整单或按明细数量入库，生成库存分类账 + 应付 + 凭证"""
    b = body()
    recv_items = b.get("items", [])  # [{item_id, qty}]
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM purchase_order WHERE id=%s", (po_id,))
        po = cur.fetchone()
        if not po:
            return fail("订单不存在", 404)
        if po["status"] not in ("confirmed", "partial"):
            return fail("只有已确认的订单可以入库")
        cur.execute("SELECT * FROM purchase_order_item WHERE po_id=%s", (po_id,))
        items = {r["id"]: dict(r) for r in cur.fetchall()}

        # 构建入库数量映射
        recv_map = {}
        if recv_items:
            for ri in recv_items:
                recv_map[int(ri["item_id"])] = float(ri["qty"])
        else:
            recv_map = {iid: float(it["qty"]) - float(it["received_qty"]) for iid, it in items.items()}

        receipt_no = next_no(cur, "RCV", "stock_ledger", "doc_no")
        total_received_amt = 0
        for iid, qty in recv_map.items():
            if qty <= 0:
                continue
            it = items.get(iid)
            if not it:
                continue
            remain = float(it["qty"]) - float(it["received_qty"])
            if qty > remain + 1e-6:
                raise ValueError(f"{it['material_id']} 入库数量超过未交数量")
            # 库存记账（采购入库，成本取采购单价）
            post_stock(cur, doc_type="采购入库", doc_no=receipt_no,
                       material_id=it["material_id"], warehouse_id=po["warehouse_id"],
                       qty=qty, cost=float(it["price"]),
                       operator=b.get("operator", "system"), remark=f"来源采购订单 {po['po_no']}")
            cur.execute("UPDATE purchase_order_item SET received_qty=received_qty+%s WHERE id=%s", (qty, iid))
            total_received_amt += qty * float(it["price"])

        # 更新订单状态
        cur.execute("""SELECT SUM(qty) tq, SUM(received_qty) rq FROM purchase_order_item WHERE po_id=%s""", (po_id,))
        ag = cur.fetchone()
        status = "received" if float(ag["rq"]) >= float(ag["tq"]) - 1e-6 else "partial"
        cur.execute("UPDATE purchase_order SET status=%s, received_amt=received_amt+%s WHERE id=%s",
                    (status, round(total_received_amt, 2), po_id))

        # 生成应付账
        cur.execute("""INSERT INTO account_payable(supplier_id,doc_no,amount,status)
                       VALUES(%s,%s,%s,'open')""",
                    (po["supplier_id"], receipt_no, round(total_received_amt, 2)))
        # 凭证对接数据
        vno = next_no(cur, "V", "voucher_export", "voucher_no")
        cur.execute("""INSERT INTO voucher_export(voucher_no,biz_doc_no,summary,debit_account,credit_account,amount)
                       VALUES(%s,%s,%s,%s,%s,%s)""",
                    (vno, receipt_no, f"采购入库-{receipt_no}", "原材料", "应付账款", round(total_received_amt, 2)))
        write_log(cur, b.get("operator", "system"), "采购", "到货入库", receipt_no, request.remote_addr)
        return ok({"receipt_no": receipt_no, "amount": round(total_received_amt, 2)}, "入库成功")


@bp.route("/purchase-orders/<int:po_id>/cancel", methods=["POST"])
@handle_errors
def cancel_po(po_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("UPDATE purchase_order SET status='cancelled' WHERE id=%s AND status IN ('draft','confirmed')", (po_id,))
        if cur.rowcount == 0:
            return fail("当前状态不能取消")
        return ok(msg="订单已取消")
