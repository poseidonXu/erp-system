# -*- coding: utf-8 -*-
"""M05 生产管理：MPS -> MRP展开 -> 工单 -> 领料 -> 完工入库

MRP 算法（参考 ERPNext）：
  对每个 MPS 产品，按 BOM 逐层展开：
    毛需求 = 上层需求 × 单位用量 × (1+损耗率)
    净需求 = 毛需求 - 现有库存 - 在途(已确认采购在途) - 在制(已下达工单)
    若子件本身有 BOM -> 建议 PRODUCE(生产子件)；否则 -> 建议 PURCHASE(采购)
"""
from flask import Blueprint, request
from db import get_conn, cursor, rows_to_dict, next_no, post_stock, available_qty, write_log
from util import ok, fail, body, handle_errors

bp = Blueprint("production", __name__, url_prefix="/api")


# ---------- MPS 主生产计划 ----------
@bp.route("/mps", methods=["GET"])
@handle_errors
def list_mps():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT m.*,p.name AS product_name,p.code AS product_code FROM mps m
                       JOIN material p ON p.id=m.product_id ORDER BY m.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/mps", methods=["POST"])
@handle_errors
def save_mps():
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        mps_no = next_no(cur, "MPS", "mps", "mps_no")
        cur.execute("""INSERT INTO mps(mps_no,product_id,qty,plan_finish,so_no)
                       VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                    (mps_no, b["product_id"], b["qty"], b.get("plan_finish") or None, b.get("so_no")))
        mid = cur.fetchone()["id"]
        write_log(cur, b.get("operator", "system"), "生产", "创建MPS", mps_no, request.remote_addr)
        return ok({"id": mid, "mps_no": mps_no}, "MPS创建成功")


# ---------- MRP 运算 ----------
@bp.route("/mrp/run", methods=["POST"])
@handle_errors
def run_mrp():
    b = body()
    mps_no = b.get("mps_no")
    with get_conn() as conn, cursor(conn) as cur:
        if mps_no:
            cur.execute("SELECT * FROM mps WHERE mps_no=%s", (mps_no,))
            plans = cur.fetchall()
        else:
            cur.execute("SELECT * FROM mps WHERE status='draft'")
            plans = cur.fetchall()
        if not plans:
            return fail("没有可运算的 MPS 计划")
        cur.execute("DELETE FROM mrp_result")
        results = []

        def explode(product_id, qty, depth=0):
            if depth > 5:
                return
            # 找到该产品的生效 BOM
            cur.execute("SELECT id FROM bom WHERE product_id=%s AND enabled=TRUE ORDER BY effective_date DESC LIMIT 1", (product_id,))
            br = cur.fetchone()
            if not br:
                return  # 叶子件（外购件）不继续展开
            bom_id = br["id"]
            cur.execute("SELECT * FROM bom_item WHERE bom_id=%s", (bom_id,))
            for comp in cur.fetchall():
                gross = float(qty) * float(comp["qty"]) * (1 + float(comp["loss_rate"]) / 100)
                stock = available_qty(cur, comp["material_id"])
                # 在途：已确认采购订单未入库量
                cur.execute("""SELECT COALESCE(SUM(i.qty-i.received_qty),0) q FROM purchase_order_item i
                               JOIN purchase_order p ON p.id=i.po_id
                               WHERE i.material_id=%s AND p.status IN ('confirmed','partial')""",
                            (comp["material_id"],))
                onhand = float(cur.fetchone()["q"])
                # 在制：已下达工单未完工量
                cur.execute("""SELECT COALESCE(SUM(qty-produced_qty),0) q FROM work_order
                               WHERE product_id=%s AND status IN ('released','issued','wip')""",
                            (comp["material_id"],))
                wip = float(cur.fetchone()["q"])
                net = max(0, gross - stock - onhand - wip)
                # 判断子件是否自制
                cur.execute("SELECT 1 FROM bom WHERE product_id=%s AND enabled=TRUE LIMIT 1", (comp["material_id"],))
                selfmade = cur.fetchone() is not None
                cur.execute("""INSERT INTO mrp_result(mps_no,material_id,gross_demand,stock_qty,net_demand,suggest_type,suggest_qty)
                               VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                            (mps_no or "BATCH", comp["material_id"], round(gross, 3), stock,
                             round(net, 3), "PRODUCE" if selfmade else "PURCHASE", round(net, 3)))
                cur.execute("SELECT code,name FROM material WHERE id=%s", (comp["material_id"],))
                m = cur.fetchone()
                results.append({"material_id": comp["material_id"], "code": m["code"], "name": m["name"],
                                "gross": round(gross, 3), "stock": stock, "net": round(net, 3),
                                "type": "PRODUCE" if selfmade else "PURCHASE", "suggest_qty": round(net, 3)})
                if selfmade and net > 0:
                    explode(comp["material_id"], net, depth + 1)

        for plan in plans:
            explode(plan["product_id"], float(plan["qty"]))
        cur.execute("UPDATE mps SET status='calculated' WHERE " +
                    ("mps_no=%s" if mps_no else "status='draft'"), (mps_no,) if mps_no else ())
        write_log(cur, b.get("operator", "system"), "生产", "MRP运算", mps_no or "全部", request.remote_addr)
        return ok(results, f"MRP 运算完成，共 {len(results)} 条净需求")


@bp.route("/mrp/results", methods=["GET"])
@handle_errors
def mrp_results():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT r.*,m.code AS material_code,m.name AS material_name,m.unit
                       FROM mrp_result r JOIN material m ON m.id=r.material_id
                       ORDER BY r.suggest_type,r.id""")
        return ok(rows_to_dict(cur.fetchall()))


# ---------- 生产工单 ----------
@bp.route("/work-orders", methods=["GET"])
@handle_errors
def list_wo():
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT w.*,m.name AS product_name,m.code AS product_code FROM work_order w
                       JOIN material m ON m.id=w.product_id ORDER BY w.id DESC""")
        return ok(rows_to_dict(cur.fetchall()))


@bp.route("/work-orders/<int:wo_id>", methods=["GET"])
@handle_errors
def get_wo(wo_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("""SELECT w.*,m.name AS product_name FROM work_order w JOIN material m ON m.id=w.product_id WHERE w.id=%s""", (wo_id,))
        head = cur.fetchone()
        if not head:
            return fail("工单不存在", 404)
        cur.execute("""SELECT i.*,m.code AS material_code,m.name AS material_name FROM material_issue i
                       JOIN material m ON m.id=i.material_id WHERE i.wo_id=%s ORDER BY i.id""", (wo_id,))
        return ok({"head": dict(head), "issues": rows_to_dict(cur.fetchall())})


@bp.route("/work-orders", methods=["POST"])
@handle_errors
def save_wo():
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        wo_no = next_no(cur, "WO", "work_order", "wo_no")
        cur.execute("""INSERT INTO work_order(wo_no,product_id,qty,plan_start,plan_finish,mps_no)
                       VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (wo_no, b["product_id"], b["qty"], b.get("plan_start") or None,
                     b.get("plan_finish") or None, b.get("mps_no")))
        wid = cur.fetchone()["id"]
        write_log(cur, b.get("operator", "system"), "生产", "创建工单", wo_no, request.remote_addr)
        return ok({"id": wid, "wo_no": wo_no}, "工单创建成功")


@bp.route("/work-orders/<int:wo_id>/release", methods=["POST"])
@handle_errors
def release_wo(wo_id):
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("UPDATE work_order SET status='released' WHERE id=%s AND status='draft'", (wo_id,))
        if cur.rowcount == 0:
            return fail("只有草稿工单可以下达")
        return ok(msg="工单已下达")


@bp.route("/work-orders/<int:wo_id>/issue", methods=["POST"])
@handle_errors
def issue_material(wo_id):
    """按 BOM 领料：扣减原材料库存"""
    b = body()
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM work_order WHERE id=%s", (wo_id,))
        wo = cur.fetchone()
        if not wo:
            return fail("工单不存在", 404)
        if wo["status"] not in ("released", "issued", "wip"):
            return fail("工单尚未下达或已完工")
        cur.execute("""SELECT bi.material_id,bi.qty FROM bom_item bi JOIN bom b ON b.id=bi.bom_id
                       WHERE b.product_id=%s AND b.enabled=TRUE ORDER BY b.id DESC""", (wo["product_id"],))
        comps = cur.fetchall()
        if not comps:
            return fail("该产品未维护 BOM，无法按 BOM 领料")
        issue_no = None
        for c in comps:
            need = float(c["qty"]) * float(wo["qty"])
            # 找到该物料有库存的仓库（优先库存充足者）
            cur.execute("""SELECT warehouse_id,SUM(qty) q FROM stock_balance
                           WHERE material_id=%s AND qty>0 GROUP BY warehouse_id ORDER BY q DESC""",
                        (c["material_id"],))
            wh_rows = cur.fetchall()
            remain = need
            for wr in wh_rows:
                if remain <= 1e-6:
                    break
                take = min(remain, float(wr["q"]))
                # 每条领料记录独立单号，避免唯一约束冲突
                line_no = next_no(cur, "ISS", "material_issue", "issue_no")
                issue_no = issue_no or line_no
                post_stock(cur, doc_type="领料出库", doc_no=line_no,
                           material_id=c["material_id"], warehouse_id=wr["warehouse_id"],
                           qty=-take, operator=b.get("operator", "system"),
                           remark=f"工单 {wo['wo_no']} 领料")
                cur.execute("""INSERT INTO material_issue(issue_no,wo_id,material_id,qty,operator)
                               VALUES(%s,%s,%s,%s,%s)""",
                            (line_no, wo_id, c["material_id"], take, b.get("operator", "system")))
                remain -= take
            if remain > 1e-6:
                raise ValueError(f"物料 {c['material_id']} 库存不足，缺 {round(remain,3)}")
        cur.execute("UPDATE work_order SET status='issued' WHERE id=%s", (wo_id,))
        write_log(cur, b.get("operator", "system"), "生产", "领料", issue_no, request.remote_addr)
        return ok({"issue_no": issue_no}, "领料成功")


@bp.route("/work-orders/<int:wo_id>/finish", methods=["POST"])
@handle_errors
def finish_wo(wo_id):
    """完工入库：成品入库 + 更新工单完工数量"""
    b = body()
    qty = float(b.get("qty", 0))
    if qty <= 0:
        return fail("完工数量必须大于0")
    with get_conn() as conn, cursor(conn) as cur:
        cur.execute("SELECT * FROM work_order WHERE id=%s", (wo_id,))
        wo = cur.fetchone()
        if not wo:
            return fail("工单不存在", 404)
        if wo["status"] not in ("issued", "wip", "released"):
            return fail("工单状态不允许完工")
        remain = float(wo["qty"]) - float(wo["produced_qty"])
        if qty > remain + 1e-6:
            raise ValueError("完工数量超过工单计划数量")
        # 计算成品成本 = 已领材料成本汇总 / 工单数量 * 完工数量（简化）
        cur.execute("""SELECT COALESCE(SUM(mi.qty * sb.avg_cost),0) c FROM material_issue mi
                       JOIN stock_balance sb ON sb.material_id=mi.material_id WHERE mi.wo_id=%s""", (wo_id,))
        mat_cost = float(cur.fetchone()["c"])
        unit_cost = mat_cost / float(wo["qty"]) if float(wo["qty"]) else 0
        cur.execute("SELECT id FROM warehouse WHERE code='WH03' LIMIT 1")
        wr = cur.fetchone()
        wh_id = wr["id"] if wr else 3
        post_stock(cur, doc_type="生产入库", doc_no=wo["wo_no"],
                   material_id=wo["product_id"], warehouse_id=wh_id,
                   qty=qty, cost=unit_cost, operator=b.get("operator", "system"),
                   remark=f"工单 {wo['wo_no']} 完工")
        cur.execute("UPDATE work_order SET produced_qty=produced_qty+%s,status=%s WHERE id=%s",
                    (qty, "done" if qty >= remain - 1e-6 else "wip", wo_id))
        write_log(cur, b.get("operator", "system"), "生产", "完工入库", wo["wo_no"], request.remote_addr)
        return ok(msg="完工入库成功")
