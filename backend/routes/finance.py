# -*- coding: utf-8 -*-
"""M06 财务管理：应付账、付款核销、应收、凭证导出"""
from flask import Blueprint, request, Response
from db import get_conn, cursor, rows_to_dict, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("finance", __name__, url_prefix="/api")


@bp.route("/payables", methods=["GET"])
@handle_errors
def list_payables():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT ap.*,s.name AS supplier_name,ap.amount-ap.paid_amount AS balance
                       FROM account_payable ap JOIN supplier s ON s.id=ap.supplier_id ORDER BY ap.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/payables/<int:apid>/pay", methods=["POST"])
@handle_errors
def pay_payable(apid):
    b = body()
    amount = float(b.get("amount", 0))
    if amount <= 0:
        return fail("付款金额必须大于0")
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM account_payable WHERE id=%s", (apid,))
        ap = cur.fetchone()
        if not ap:
            return fail("应付记录不存在", 404)
        remain = float(ap["amount"]) - float(ap["paid_amount"])
        if amount > remain + 1e-6:
            raise ValueError("付款金额超过应付余额")
        cur.execute("INSERT INTO payment_paid(ap_id,amount,pay_date,remark) VALUES(%s,%s,%s,%s)",
                    (apid, amount, b.get("pay_date") or None, b.get("remark")))
        new_paid = float(ap["paid_amount"]) + amount
        status = "paid" if new_paid >= float(ap["amount"]) - 1e-6 else "partial"
        cur.execute("UPDATE account_payable SET paid_amount=%s,status=%s,pay_date=%s WHERE id=%s",
                    (new_paid, status, b.get("pay_date") or None, apid))
        write_log(cur, b.get("operator", "system"), "财务", "付款", f"AP#{apid} 付款{amount}", request.remote_addr)
        return ok(msg="付款成功")


@bp.route("/receivables", methods=["GET"])
@handle_errors
def list_receivables():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT so.id,so.so_no,c.name AS customer_name,so.total_amt AS amount,
                       so.paid_amt AS settled,so.total_amt-so.paid_amt AS balance,so.order_date
                       FROM sales_order so JOIN customer c ON c.id=so.customer_id
                       WHERE so.status IN ('confirmed','partial','shipped') ORDER BY so.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/payments", methods=["GET"])
@handle_errors
def list_payments():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT p.*,c.name AS customer_name FROM payment_received p
                       JOIN customer c ON c.id=p.customer_id ORDER BY p.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/vouchers", methods=["GET"])
@handle_errors
def list_vouchers():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM voucher_export ORDER BY id DESC")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/vouchers/export.csv", methods=["GET"])
@handle_errors
def export_vouchers():
    """凭证导出 CSV（供外部财务系统对接，UTF-8 BOM 便于 Excel 打开）"""
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM voucher_export ORDER BY id")
        rows = cur.fetchall()
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["凭证号","业务单号","摘要","借方科目","贷方科目","金额","是否已导出"])
        for r in rows:
            w.writerow([r["voucher_no"], r["biz_doc_no"], r["summary"], r["debit_account"],
                        r["credit_account"], r["amount"], "是" if r["exported"] else "否"])
        cur.execute("UPDATE voucher_export SET exported=TRUE")
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=vouchers.csv"})
