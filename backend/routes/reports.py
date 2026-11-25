# -*- coding: utf-8 -*-
"""M07 报表中心：经营看板 + 采购/库存/销售/生产/财务报表 + Excel(CSV)导出"""
from flask import Blueprint, request, Response
from db import get_conn, cursor, rows_to_dict, write_log
from util import ok, handle_errors

bp = Blueprint("reports", __name__, url_prefix="/api")


@bp.route("/dashboard", methods=["GET"])
@handle_errors
def dashboard():
    with get_conn() as conn, cursor(conn) as cur:
        def scalar(sql, params=None):
            cur.execute(sql, params or ())
            r = cur.fetchone()
            return float(r["v"]) if r and r["v"] is not None else 0

        data = {
            "sales_amount": scalar("SELECT COALESCE(SUM(total_amt),0) v FROM sales_order WHERE status IN ('confirmed','partial','shipped')"),
            "purchase_amount": scalar("SELECT COALESCE(SUM(received_amt),0) v FROM purchase_order"),
            "stock_amount": scalar("SELECT COALESCE(SUM(qty*avg_cost),0) v FROM stock_balance"),
            "ar_balance": scalar("SELECT COALESCE(SUM(total_amt-paid_amt),0) v FROM sales_order WHERE status IN ('confirmed','partial','shipped')"),
            "ap_balance": scalar("SELECT COALESCE(SUM(amount-paid_amount),0) v FROM account_payable"),
            "low_stock_count": scalar("SELECT COUNT(*) v FROM stock_balance sb JOIN material m ON m.id=sb.material_id WHERE sb.qty<m.safety_stock"),
            "so_count": scalar("SELECT COUNT(*) v FROM sales_order"),
            "po_count": scalar("SELECT COUNT(*) v FROM purchase_order"),
            "wo_count": scalar("SELECT COUNT(*) v FROM work_order"),
            "material_count": scalar("SELECT COUNT(*) v FROM material WHERE enabled=TRUE"),
        }
        # 采购/销售近6个月趋势
        cur.execute("""SELECT TO_CHAR(order_date,'YYYY-MM') m,SUM(total_amt) v FROM sales_order
                       GROUP BY 1 ORDER BY 1 DESC LIMIT 6""")
        data["sales_trend"] = [{"month": r["m"], "value": float(r["v"])} for r in cur.fetchall()][::-1]
        cur.execute("""SELECT TO_CHAR(order_date,'YYYY-MM') m,SUM(total_amt) v FROM purchase_order
                       GROUP BY 1 ORDER BY 1 DESC LIMIT 6""")
        data["purchase_trend"] = [{"month": r["m"], "value": float(r["v"])} for r in cur.fetchall()][::-1]
        # 交付率
        cur.execute("""SELECT COALESCE(SUM(shipped_amt),0) s,COALESCE(SUM(total_amt),0) t FROM sales_order
                       WHERE status IN ('confirmed','partial','shipped')""")
        r = cur.fetchone()
        data["delivery_rate"] = round(float(r["s"]) / float(r["t"]) * 100, 1) if float(r["t"]) else 0
        return ok(data)


# 报表注册表：名称 -> SQL
REPORTS = {
    "purchase_exec": ("""SELECT po.po_no,s.name AS supplier_name,po.order_date,po.status,
        po.total_qty,po.total_amt,po.received_amt,ROUND(CASE WHEN po.total_amt>0
        THEN po.received_amt/po.total_amt*100 ELSE 0 END,1) AS exec_rate
        FROM purchase_order po JOIN supplier s ON s.id=po.supplier_id ORDER BY po.id DESC""",
        "采购订单执行表"),
    "stock_balance": ("""SELECT m.code AS material_code,m.name AS material_name,m.unit,w.name AS warehouse_name,
        sb.qty,sb.avg_cost,ROUND(sb.qty*sb.avg_cost,2) AS amount,m.safety_stock
        FROM stock_balance sb JOIN material m ON m.id=sb.material_id JOIN warehouse w ON w.id=sb.warehouse_id
        ORDER BY sb.material_id""", "库存结存表"),
    "stock_ledger": ("""SELECT l.created_at,l.txn_no,l.doc_type,l.doc_no,m.name AS material_name,
        l.direction,l.qty,l.cost,u.name AS operator FROM stock_ledger l
        JOIN material m ON m.id=l.material_id LEFT JOIN sys_user u ON u.username=l.operator
        ORDER BY l.id DESC LIMIT 2000""", "出入库流水账"),
    "sales_exec": ("""SELECT so.so_no,c.name AS customer_name,so.order_date,so.status,
        so.total_qty,so.total_amt,so.shipped_amt,so.paid_amt,ROUND(CASE WHEN so.total_amt>0
        THEN so.shipped_amt/so.total_amt*100 ELSE 0 END,1) AS ship_rate
        FROM sales_order so JOIN customer c ON c.id=so.customer_id ORDER BY so.id DESC""", "销售订单执行表"),
    "work_order": ("""SELECT w.wo_no,p.name AS product_name,w.qty,w.produced_qty,w.plan_finish,w.status
        FROM work_order w JOIN material p ON p.id=w.product_id ORDER BY w.id DESC""", "工单进度表"),
    "finance": ("""SELECT '应收' AS biz_type,c.name AS party_name,so.so_no AS doc_no,
        so.total_amt,so.paid_amt,so.total_amt-so.paid_amt AS balance FROM sales_order so
        JOIN customer c ON c.id=so.customer_id WHERE so.status IN ('confirmed','partial','shipped')
        UNION ALL
        SELECT '应付',s.name,po.po_no,ap.amount,ap.paid_amount,ap.amount-ap.paid_amount
        FROM account_payable ap JOIN supplier s ON s.id=ap.supplier_id
        JOIN purchase_order po ON po.po_no=ap.doc_no ORDER BY 1,3 DESC""", "应收应付汇总表"),
    "mrp": ("""SELECT r.material_id,m.code,m.name,r.gross_demand,r.stock_qty,r.net_demand,
        r.suggest_type,r.suggest_qty FROM mrp_result r JOIN material m ON m.id=r.material_id ORDER BY r.id""", "物料需求清单"),
}


@bp.route("/report/<name>", methods=["GET"])
@handle_errors
def get_report(name):
    if name not in REPORTS:
        return ok({"columns": [], "rows": [], "title": "未知报表"})
    sql, title = REPORTS[name]
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute(sql)
        rows = rows_to_dict(cur.fetchall())
        columns = list(rows[0].keys()) if rows else []
        return ok({"title": title, "columns": columns, "rows": rows})


@bp.route("/report/<name>/export", methods=["GET"])
@handle_errors
def export_report(name):
    if name not in REPORTS:
        return fail("未知报表", 404)
    sql, title = REPORTS[name]
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        if rows:
            cols = list(rows[0].keys())
            w.writerow(cols)
            for r in rows:
                w.writerow([r[c] for c in cols])
        write_log(cur, "system", "报表", "导出", title, request.remote_addr)
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={name}.csv"})


def fail(msg, code):
    from util import fail as _fail
    return _fail(msg, code)
