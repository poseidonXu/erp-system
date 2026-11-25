# -*- coding: utf-8 -*-
"""数据库连接层 + 事务管理 + 库存记账核心

设计要点（参考 ERPNext Stock Ledger）：
- 所有库存变动必须通过 post_stock() 写入 stock_ledger，再回写 stock_balance
- 业务单据与库存记账在同一事务内完成，保证账实相符与原子性
"""
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from config import DSN, DB_SCHEMA


@contextmanager
def get_conn():
    """获取连接，自动提交/回滚/关闭"""
    conn = psycopg2.connect(**DSN)
    conn.set_client_encoding("UTF8")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


@contextmanager
def cursor(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SET search_path TO {DB_SCHEMA}, public")
    try:
        yield cur
    finally:
        cur.close()


def rows_to_dict(rows):
    return [dict(r) for r in rows]


def next_no(cur, prefix, table, column):
    """生成单据编号: PREFIX + YYYYMMDD + 3位序号"""
    from datetime import datetime
    day = datetime.now().strftime("%Y%m%d")
    like = f"{prefix}{day}%"
    cur.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE %s ORDER BY {column} DESC LIMIT 1",
        (like,),
    )
    r = cur.fetchone()
    seq = 1
    if r:
        last = dict(r)[column]
        try:
            seq = int(last[-3:]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{day}{seq:03d}"


def post_stock(cur, *, doc_type, doc_no, material_id, warehouse_id, qty,
               cost=0, location_id=None, batch_no="", operator="system", remark=""):
    """库存记账核心：写分类账 + 回写结存（移动加权平均）

    qty > 0 入库；qty < 0 出库。移动平均成本在入库时重算。
    """
    direction = "IN" if qty > 0 else "OUT"
    txn_no = next_no(cur, "TXN", "stock_ledger", "txn_no")
    cur.execute(
        """INSERT INTO stock_ledger
           (txn_no,doc_type,doc_no,material_id,warehouse_id,location_id,batch_no,
            qty,cost,direction,operator,remark)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (txn_no, doc_type, doc_no, material_id, warehouse_id, location_id, batch_no,
         abs(qty), cost, direction, operator, remark),
    )

    if qty > 0:
        # 入库：优先精确匹配 物料+仓库+库位+批次；未指定库位时归入该仓库现有行或新建
        cur.execute(
            """SELECT id,qty,avg_cost FROM stock_balance
               WHERE material_id=%s AND warehouse_id=%s
                 AND location_id IS NOT DISTINCT FROM %s AND batch_no=%s""",
            (material_id, warehouse_id, location_id, batch_no),
        )
        row = cur.fetchone()
        if not row and location_id is None:
            # 未指定库位：归入同物料同仓库的现有行（保持库位维度）
            cur.execute("""SELECT id,qty,avg_cost FROM stock_balance
                           WHERE material_id=%s AND warehouse_id=%s AND batch_no=%s
                           ORDER BY id LIMIT 1""", (material_id, warehouse_id, batch_no))
            row = cur.fetchone()
        if row:
            old_qty = float(row["qty"]); old_cost = float(row["avg_cost"])
            new_qty = old_qty + qty
            new_avg = (old_qty * old_cost + qty * cost) / new_qty if new_qty else cost
            cur.execute("UPDATE stock_balance SET qty=%s, avg_cost=%s WHERE id=%s",
                        (new_qty, round(new_avg, 4), row["id"]))
        else:
            cur.execute(
                """INSERT INTO stock_balance
                   (material_id,warehouse_id,location_id,batch_no,qty,avg_cost)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (material_id, warehouse_id, location_id, batch_no, qty, cost),
            )
    else:
        # 出库：按先进先出（id 升序）跨库位/批次扣减，直到满足数量
        need = abs(qty)
        cur.execute("""SELECT id,qty FROM stock_balance
                       WHERE material_id=%s AND warehouse_id=%s AND qty>0 ORDER BY id""",
                    (material_id, warehouse_id))
        rows = cur.fetchall()
        total = sum(float(r["qty"]) for r in rows)
        if total + 1e-6 < need:
            raise ValueError(f"库存不足：需要 {need}，{warehouse_id}号仓可用 {round(total,3)}")
        for r in rows:
            if need <= 1e-6:
                break
            take = min(need, float(r["qty"]))
            cur.execute("UPDATE stock_balance SET qty=qty-%s WHERE id=%s", (take, r["id"]))
            need -= take
    return txn_no


def available_qty(cur, material_id, warehouse_id=None):
    """查询可用库存数量"""
    if warehouse_id:
        cur.execute("SELECT COALESCE(SUM(qty),0) AS q FROM stock_balance WHERE material_id=%s AND warehouse_id=%s",
                    (material_id, warehouse_id))
    else:
        cur.execute("SELECT COALESCE(SUM(qty),0) AS q FROM stock_balance WHERE material_id=%s", (material_id,))
    r = cur.fetchone()
    return float(r["q"]) if hasattr(r, "__getitem__") else 0.0


def write_log(cur, username, module, action, detail, ip=""):
    cur.execute(
        "INSERT INTO operation_log(username,module,action,detail,ip) VALUES(%s,%s,%s,%s,%s)",
        (username, module, action, detail, ip),
    )
