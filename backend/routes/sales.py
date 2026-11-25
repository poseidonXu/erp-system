# -*- coding: utf-8 -*-
"""M04 销售管理：销售订单 -> 确认(校验库存/信用) -> 发货出库 -> 收款
发货同时扣减库存分类账 + 生成应收 + 凭证
"""
from flask import Blueprint, request
from db import get_conn, cursor, rows_to_dict, next_no, post_stock, available_qty, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("sales", __name__, url_prefix="/api")


@bp.route("/sales-orders", methods=["GET"])
@handle_errors
def list_so():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT so.*,c.name AS customer_name FROM sales_order so
                       JOIN customer c ON c.id=so.customer_id ORDER BY so.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/sales-orders/<int:so_id>", methods=["GET"])
@handle_errors
def get_so(so_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT so.*,c.name AS customer_name FROM sales_order so
                       JOIN customer c ON c.id=so.customer_id WHERE so.id=%s""", (so_id,))
        head = cur.fetchone()
        if not head:
            return fail("订单不存在", 404)
        cur.execute("""SELECT i.*,m.code AS material_code,m.name AS material_name,m.unit
                       FROM sales_order_item i JOIN material m ON m.id=i.material_id
                       WHERE i.so_id=%s ORDER BY i.id""", (so_id,))
        return ok({"head": dict(head), "items": rows_to_dict(cur.fetchall())})


@bp.route("/sales-orders", methods=["POST"])
@handle_errors
def save_so():
    b = body()
    items = b.get("items", [])
    if not items:
        return fail("请至少添加一条明细")
    with get_conn() as conn, cursor(conn) as cur:
        total_qty = sum(float(i["qty"]) for i in items)
        total_amt = sum(float(i["qty"]) * float(i["price"]) for i in items)
        if b.get("id"):
            so_id = b["id"]
            cur.execute("""UPDATE sales_order SET customer_id=%s,delivery_date=%s,address=%s,
                           total_qty=%s,total_amt=%s WHERE id=%s AND status='draft'""",
                        (b["customer_id"], b.get("delivery_date") or None, b.get("address"),
                         total_qty, round(total_amt, 2), so_id))
            cur.execute("DELETE FROM sales_order_item WHERE so_id=%s", (so_id,))
        else:
            so_no = next_no(cur, "SO", "sales_order", "so_no")
            cur.execute("""INSERT INTO sales_order(so_no,customer_id,delivery_date,address,total_qty,total_amt,creator)
                           VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (so_no, b["customer_id"], b.get("delivery_date") or None, b.get("address"),
                         total_qty, round(total_amt, 2), b.get("operator", "system")))
            so_id = cur.fetchone()["id"]
        for i in items:
            cur.execute("""INSERT INTO sales_order_item(so_id,material_id,qty,price,amount)
                           VALUES(%s,%s,%s,%s,%s)""",
                        (so_id, i["material_id"], i["qty"], i["price"],
                         round(float(i["qty"]) * float(i["price"]), 2)))
        write_log(cur, b.get("operator", "system"), "销售", "保存订单", f"SO#{so_id}", request.remote_addr)
        return ok({"id": so_id}, "销售订单保存成功")


@bp.route("/sales-orders/<int:so_id>/confirm", methods=["POST"])
@handle_errors
def confirm_so(so_id):
    """确认订单：校验客户信用额度与库存可用性"""
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT so.*,c.credit_limit,
                       COALESCE((SELECT SUM(total_amt-paid_amt) FROM sales_order
                                 WHERE customer_id=so.customer_id AND status IN ('confirmed','partial','shipped')),0) AS ar_balance
                       FROM sales_order so JOIN customer c ON c.id=so.customer_id WHERE so.id=%s""", (so_id,))
        so = cur.fetchone()
        if not so:
            return fail("订单不存在", 404)
        if so["status"] != "draft":
            return fail("只有草稿订单可以确认")
        # 信用额度校验
        if float(so["credit_limit"]) > 0 and float(so["ar_balance"]) + float(so["total_amt"]) > float(so["credit_limit"]):
            return fail(f"超出客户信用额度（额度{so['credit_limit']}，当前应收{round(float(so['ar_balance']),2)}）")
        # 库存校验
        cur.execute("SELECT * FROM sales_order_item WHERE so_id=%s", (so_id,))
        for it in cur.fetchall():
            avail = available_qty(cur, it["material_id"])
            if avail < float(it["qty"]):
                return fail(f"物料库存不足：需要 {it['qty']}，可用 {avail}")
        cur.execute("UPDATE sales_order SET status='confirmed' WHERE id=%s", (so_id,))
        return ok(msg="订单已确认")


@bp.route("/sales-orders/<int:so_id>/ship", methods=["POST"])
@handle_errors
def ship_so(so_id):
    """发货出库：扣库存 + 生成应收 + 凭证"""
    b = body()
    ship_items = b.get("items", [])
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM sales_order WHERE id=%s", (so_id,))
        so = cur.fetchone()
        if not so:
            return fail("订单不存在", 404)
        if so["status"] not in ("confirmed", "partial"):
            return fail("只有已确认订单可以发货")
        cur.execute("SELECT * FROM sales_order_item WHERE so_id=%s", (so_id,))
        items = {r["id"]: dict(r) for r in cur.fetchall()}
        ship_map = {}
        if ship_items:
            for si in ship_items:
                ship_map[int(si["item_id"])] = float(si["qty"])
        else:
            ship_map = {iid: float(it["qty"]) - float(it["shipped_qty"]) for iid, it in items.items()}

        delivery_no = next_no(cur, "DN", "stock_ledger", "doc_no")
        # 找成品库作为默认出库仓
        cur.execute("SELECT id FROM warehouse WHERE code='WH03' LIMIT 1")
        wr = cur.fetchone()
        wh_id = wr["id"] if wr else 1
        total_ship_amt = 0
        for iid, qty in ship_map.items():
            if qty <= 0:
                continue
            it = items.get(iid)
            if not it:
                continue
            remain = float(it["qty"]) - float(it["shipped_qty"])
            if qty > remain + 1e-6:
                raise ValueError("发货数量超过未发数量")
            # 读取当前移动平均成本作为出库成本
            cur.execute("SELECT COALESCE(AVG(avg_cost),0) c FROM stock_balance WHERE material_id=%s", (it["material_id"],))
            cost = float(cur.fetchone()["c"])
            post_stock(cur, doc_type="销售出库", doc_no=delivery_no,
                       material_id=it["material_id"], warehouse_id=wh_id,
                       qty=-qty, cost=cost, operator=b.get("operator", "system"),
                       remark=f"来源销售订单 {so['so_no']}")
            cur.execute("UPDATE sales_order_item SET shipped_qty=shipped_qty+%s WHERE id=%s", (qty, iid))
            total_ship_amt += qty * float(it["price"])

        cur.execute("SELECT SUM(qty) tq,SUM(shipped_qty) sq FROM sales_order_item WHERE so_id=%s", (so_id,))
        ag = cur.fetchone()
        status = "shipped" if float(ag["sq"]) >= float(ag["tq"]) - 1e-6 else "partial"
        cur.execute("UPDATE sales_order SET status=%s, shipped_amt=shipped_amt+%s WHERE id=%s",
                    (status, round(total_ship_amt, 2), so_id))
        # 凭证
        vno = next_no(cur, "V", "voucher_export", "voucher_no")
        cur.execute("""INSERT INTO voucher_export(voucher_no,biz_doc_no,summary,debit_account,credit_account,amount)
                       VALUES(%s,%s,%s,%s,%s,%s)""",
                    (vno, delivery_no, f"销售出库-{delivery_no}", "应收账款", "主营业务收入", round(total_ship_amt, 2)))
        write_log(cur, b.get("operator", "system"), "销售", "发货出库", delivery_no, request.remote_addr)
        return ok({"delivery_no": delivery_no, "amount": round(total_ship_amt, 2)}, "发货成功")


@bp.route("/sales-orders/<int:so_id>/pay", methods=["POST"])
@handle_errors
def receive_payment(so_id):
    """收款核销"""
    b = body()
    amount = float(b.get("amount", 0))
    if amount <= 0:
        return fail("收款金额必须大于0")
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM sales_order WHERE id=%s", (so_id,))
        so = cur.fetchone()
        if not so:
            return fail("订单不存在", 404)
        cur.execute("INSERT INTO payment_received(so_id,customer_id,amount,pay_date,remark) VALUES(%s,%s,%s,%s,%s)",
                    (so_id, so["customer_id"], amount, b.get("pay_date") or None, b.get("remark")))
        cur.execute("UPDATE sales_order SET paid_amt=paid_amt+%s WHERE id=%s", (amount, so_id))
        write_log(cur, b.get("operator", "system"), "销售", "收款", f"SO#{so_id} 收款{amount}", request.remote_addr)
        return ok(msg="收款成功")


@bp.route("/sales-orders/<int:so_id>/cancel", methods=["POST"])
@handle_errors
def cancel_so(so_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("UPDATE sales_order SET status='cancelled' WHERE id=%s AND status IN ('draft','confirmed')", (so_id,))
        if cur.rowcount == 0:
            return fail("当前状态不能取消")
        return ok(msg="订单已取消")
