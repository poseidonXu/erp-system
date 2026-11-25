-- ============================================================
-- 华晟 ERP 系统 - 数据库表结构 (HighGo / PostgreSQL 10.6)
-- 设计参考：Odoo 模块化 + ERPNext 库存分类账(Stock Ledger)
-- 所有业务表放在独立 schema: erp
-- ============================================================

CREATE SCHEMA IF NOT EXISTS erp;
SET search_path TO erp, public;

-- ---------- 通用触发器函数：自动更新 updated_at ----------
CREATE OR REPLACE FUNCTION erp.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- M08 系统管理
-- ============================================================

-- 部门
CREATE TABLE erp.department (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,
    name        VARCHAR(80) NOT NULL,
    parent_id   INTEGER REFERENCES erp.department(id),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 用户
CREATE TABLE erp.sys_user (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) UNIQUE NOT NULL,
    password    VARCHAR(100) NOT NULL,          -- 演示用：sha256 摘要
    real_name   VARCHAR(50),
    role        VARCHAR(30) NOT NULL DEFAULT 'viewer', -- admin/purchaser/warehouse/sales/planner/finance
    dept_id     INTEGER REFERENCES erp.department(id),
    enabled     BOOLEAN DEFAULT TRUE,
    last_login  TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);
COMMENT ON COLUMN erp.sys_user.password IS '演示环境使用 sha256(明文); 生产环境应改用 bcrypt/argon2';

-- 操作日志
CREATE TABLE erp.operation_log (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(50),
    module      VARCHAR(30),
    action      VARCHAR(30),
    detail      TEXT,
    ip          VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 系统参数
CREATE TABLE erp.sys_param (
    param_key   VARCHAR(60) PRIMARY KEY,
    param_value VARCHAR(200) NOT NULL,
    remark      VARCHAR(200)
);

-- ============================================================
-- M01 基础数据管理
-- ============================================================

-- 物料档案
CREATE TABLE erp.material (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,
    name        VARCHAR(120) NOT NULL,
    spec        VARCHAR(120),
    category    VARCHAR(60),                    -- 物料类别
    unit        VARCHAR(20) NOT NULL DEFAULT '件',
    price_method VARCHAR(20) DEFAULT '移动平均', -- 计价方式
    standard_cost NUMERIC(14,4) DEFAULT 0,      -- 标准成本
    safety_stock NUMERIC(14,3) DEFAULT 0,       -- 安全库存
    is_batch    BOOLEAN DEFAULT FALSE,          -- 是否批次管理
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER trg_material_updated BEFORE UPDATE ON erp.material
    FOR EACH ROW EXECUTE PROCEDURE erp.set_updated_at();

-- 客户档案
CREATE TABLE erp.customer (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,
    name        VARCHAR(120) NOT NULL,
    contact     VARCHAR(50),
    phone       VARCHAR(30),
    address     VARCHAR(200),
    settle_type VARCHAR(30) DEFAULT '月结30天',
    credit_limit NUMERIC(14,2) DEFAULT 0,       -- 信用额度
    price_level VARCHAR(20) DEFAULT '标准',
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 供应商档案
CREATE TABLE erp.supplier (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,
    name        VARCHAR(120) NOT NULL,
    contact     VARCHAR(50),
    phone       VARCHAR(30),
    supply_type VARCHAR(60),
    pay_terms   VARCHAR(30) DEFAULT '月结30天',
    qualified   BOOLEAN DEFAULT TRUE,           -- 合格供应商
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 仓库与库位（两级：仓库 -> 库位）
CREATE TABLE erp.warehouse (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,
    name        VARCHAR(80) NOT NULL,
    location    VARCHAR(200),
    enabled     BOOLEAN DEFAULT TRUE
);
CREATE TABLE erp.location (
    id          SERIAL PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES erp.warehouse(id),
    code        VARCHAR(40) NOT NULL,
    name        VARCHAR(80) NOT NULL,
    frozen      BOOLEAN DEFAULT FALSE,          -- 冻结库位
    UNIQUE(warehouse_id, code)
);

-- BOM 物料清单（表头 + 明细，支持版本）
CREATE TABLE erp.bom (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES erp.material(id), -- 产出物料(成品/半成品)
    version     VARCHAR(20) DEFAULT 'V1',
    qty_base    NUMERIC(14,3) DEFAULT 1,        -- 基准产量
    effective_date DATE DEFAULT CURRENT_DATE,
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(product_id, version)
);
CREATE TABLE erp.bom_item (
    id          SERIAL PRIMARY KEY,
    bom_id      INTEGER NOT NULL REFERENCES erp.bom(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,         -- 单位用量
    loss_rate   NUMERIC(6,3) DEFAULT 0,         -- 损耗率 %
    UNIQUE(bom_id, material_id)
);

-- ============================================================
-- M03 库存管理 —— 库存分类账(核心)
-- ============================================================

-- 库存结存（按 物料+仓库+库位+批次 维度）
CREATE TABLE erp.stock_balance (
    id          SERIAL PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    warehouse_id INTEGER NOT NULL REFERENCES erp.warehouse(id),
    location_id INTEGER REFERENCES erp.location(id),
    batch_no    VARCHAR(50) DEFAULT '',
    qty         NUMERIC(14,3) NOT NULL DEFAULT 0,
    avg_cost    NUMERIC(14,4) NOT NULL DEFAULT 0,
    UNIQUE(material_id, warehouse_id, location_id, batch_no)
);

-- 库存交易流水（Stock Ledger）：所有出入库都记账，保证可追溯、账实相符
CREATE TABLE erp.stock_ledger (
    id          BIGSERIAL PRIMARY KEY,
    txn_no      VARCHAR(40) UNIQUE NOT NULL,    -- 流水号
    doc_type    VARCHAR(30) NOT NULL,           -- 采购入库/生产入库/销售出库/领料出库/退料/调拨/盘盈/盘亏
    doc_no      VARCHAR(40) NOT NULL,           -- 来源单据号（可追溯）
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    warehouse_id INTEGER NOT NULL REFERENCES erp.warehouse(id),
    location_id INTEGER REFERENCES erp.location(id),
    batch_no    VARCHAR(50) DEFAULT '',
    qty         NUMERIC(14,3) NOT NULL,         -- 正=入库, 负=出库
    cost        NUMERIC(14,4) DEFAULT 0,        -- 单位成本
    direction   VARCHAR(10) NOT NULL,           -- IN / OUT
    operator    VARCHAR(50),
    remark      TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ledger_material ON erp.stock_ledger(material_id);
CREATE INDEX idx_ledger_doc ON erp.stock_ledger(doc_no);
CREATE INDEX idx_ledger_time ON erp.stock_ledger(created_at);

-- 库存调拨单
CREATE TABLE erp.stock_transfer (
    id          SERIAL PRIMARY KEY,
    transfer_no VARCHAR(40) UNIQUE NOT NULL,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    from_wh     INTEGER NOT NULL REFERENCES erp.warehouse(id),
    to_wh       INTEGER NOT NULL REFERENCES erp.warehouse(id),
    qty         NUMERIC(14,3) NOT NULL,
    status      VARCHAR(20) DEFAULT 'draft',
    operator    VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 盘点单
CREATE TABLE erp.stock_count (
    id          SERIAL PRIMARY KEY,
    count_no    VARCHAR(40) UNIQUE NOT NULL,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    warehouse_id INTEGER NOT NULL REFERENCES erp.warehouse(id),
    book_qty    NUMERIC(14,3) NOT NULL,         -- 账面数量
    actual_qty  NUMERIC(14,3) NOT NULL,         -- 实盘数量
    diff_qty    NUMERIC(14,3) DEFAULT 0,            -- 应用层计算: actual-book
    status      VARCHAR(20) DEFAULT 'draft',    -- draft/confirmed
    operator    VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- M02 采购管理
-- ============================================================

-- 采购订单（表头）
CREATE TABLE erp.purchase_order (
    id          SERIAL PRIMARY KEY,
    po_no       VARCHAR(40) UNIQUE NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES erp.supplier(id),
    warehouse_id INTEGER NOT NULL REFERENCES erp.warehouse(id),
    order_date  DATE DEFAULT CURRENT_DATE,
    need_date   DATE,
    status      VARCHAR(20) DEFAULT 'draft',    -- draft/confirmed/partial/received/cancelled
    total_qty   NUMERIC(14,3) DEFAULT 0,
    total_amt   NUMERIC(14,2) DEFAULT 0,
    received_amt NUMERIC(14,2) DEFAULT 0,
    creator     VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);
-- 采购订单明细
CREATE TABLE erp.purchase_order_item (
    id          SERIAL PRIMARY KEY,
    po_id       INTEGER NOT NULL REFERENCES erp.purchase_order(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,
    price       NUMERIC(14,4) NOT NULL,
    received_qty NUMERIC(14,3) DEFAULT 0,
    amount      NUMERIC(14,2) DEFAULT 0             -- 应用层计算: qty*price
);

-- ============================================================
-- M04 销售管理
-- ============================================================

-- 销售订单（表头）
CREATE TABLE erp.sales_order (
    id          SERIAL PRIMARY KEY,
    so_no       VARCHAR(40) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES erp.customer(id),
    order_date  DATE DEFAULT CURRENT_DATE,
    delivery_date DATE,
    address     VARCHAR(200),
    status      VARCHAR(20) DEFAULT 'draft',    -- draft/confirmed/partial/shipped/cancelled
    total_qty   NUMERIC(14,3) DEFAULT 0,
    total_amt   NUMERIC(14,2) DEFAULT 0,
    shipped_amt NUMERIC(14,2) DEFAULT 0,
    paid_amt    NUMERIC(14,2) DEFAULT 0,
    creator     VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);
-- 销售订单明细
CREATE TABLE erp.sales_order_item (
    id          SERIAL PRIMARY KEY,
    so_id       INTEGER NOT NULL REFERENCES erp.sales_order(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,
    price       NUMERIC(14,4) NOT NULL,
    shipped_qty NUMERIC(14,3) DEFAULT 0,
    amount      NUMERIC(14,2) DEFAULT 0             -- 应用层计算: qty*price
);

-- 收款记录
CREATE TABLE erp.payment_received (
    id          SERIAL PRIMARY KEY,
    so_id       INTEGER REFERENCES erp.sales_order(id),
    customer_id INTEGER NOT NULL REFERENCES erp.customer(id),
    amount      NUMERIC(14,2) NOT NULL,
    pay_date    DATE DEFAULT CURRENT_DATE,
    remark      VARCHAR(200),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- M05 生产管理
-- ============================================================

-- 主生产计划 MPS
CREATE TABLE erp.mps (
    id          SERIAL PRIMARY KEY,
    mps_no      VARCHAR(40) UNIQUE NOT NULL,
    product_id  INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,
    plan_finish DATE,
    so_no       VARCHAR(40),                    -- 来源销售订单
    status      VARCHAR(20) DEFAULT 'draft',
    created_at  TIMESTAMP DEFAULT NOW()
);

-- MRP 运算结果（存储每次运算的净需求建议）
CREATE TABLE erp.mrp_result (
    id          SERIAL PRIMARY KEY,
    mps_no      VARCHAR(40) NOT NULL,
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    gross_demand NUMERIC(14,3) NOT NULL,        -- 毛需求
    stock_qty   NUMERIC(14,3) DEFAULT 0,        -- 现有库存
    net_demand  NUMERIC(14,3) NOT NULL,         -- 净需求
    suggest_type VARCHAR(20) NOT NULL,          -- PURCHASE(采购) / PRODUCE(生产)
    suggest_qty NUMERIC(14,3) NOT NULL,
    calc_time   TIMESTAMP DEFAULT NOW()
);

-- 生产工单
CREATE TABLE erp.work_order (
    id          SERIAL PRIMARY KEY,
    wo_no       VARCHAR(40) UNIQUE NOT NULL,
    product_id  INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,
    produced_qty NUMERIC(14,3) DEFAULT 0,
    plan_start  DATE,
    plan_finish DATE,
    mps_no      VARCHAR(40),
    status      VARCHAR(20) DEFAULT 'draft',    -- draft/released/issued/wip/done/cancelled
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 领料记录（工单 -> 物料出库）
CREATE TABLE erp.material_issue (
    id          SERIAL PRIMARY KEY,
    issue_no    VARCHAR(40) UNIQUE NOT NULL,
    wo_id       INTEGER NOT NULL REFERENCES erp.work_order(id),
    material_id INTEGER NOT NULL REFERENCES erp.material(id),
    qty         NUMERIC(14,3) NOT NULL,
    operator    VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- M06 财务管理
-- ============================================================

-- 应付账（采购入库生成）
CREATE TABLE erp.account_payable (
    id          SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES erp.supplier(id),
    doc_no      VARCHAR(40) NOT NULL,           -- 来源入库单
    amount      NUMERIC(14,2) NOT NULL,
    paid_amount NUMERIC(14,2) DEFAULT 0,
    pay_date    DATE,
    status      VARCHAR(20) DEFAULT 'open',     -- open/partial/paid
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 应付付款记录
CREATE TABLE erp.payment_paid (
    id          SERIAL PRIMARY KEY,
    ap_id       INTEGER NOT NULL REFERENCES erp.account_payable(id),
    amount      NUMERIC(14,2) NOT NULL,
    pay_date    DATE DEFAULT CURRENT_DATE,
    remark      VARCHAR(200),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 凭证数据（供外部财务系统对接导出）
CREATE TABLE erp.voucher_export (
    id          SERIAL PRIMARY KEY,
    voucher_no  VARCHAR(40) UNIQUE NOT NULL,
    biz_doc_no  VARCHAR(40) NOT NULL,
    summary     VARCHAR(200),
    debit_account VARCHAR(40),
    credit_account VARCHAR(40),
    amount      NUMERIC(14,2) NOT NULL,
    exported    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 常用报表视图
-- ============================================================

-- 库存结存视图（含物料信息）
CREATE OR REPLACE VIEW erp.v_stock AS
SELECT sb.material_id, m.code AS material_code, m.name AS material_name, m.unit,
       sb.warehouse_id, w.name AS warehouse_name, sb.batch_no,
       sb.qty, sb.avg_cost, ROUND(sb.qty * sb.avg_cost, 2) AS amount
FROM erp.stock_balance sb
JOIN erp.material m ON m.id = sb.material_id
JOIN erp.warehouse w ON w.id = sb.warehouse_id;

-- 采购订单执行视图
CREATE OR REPLACE VIEW erp.v_po_exec AS
SELECT po.id, po.po_no, s.name AS supplier_name, po.status,
       po.total_qty, po.received_amt, po.total_amt, po.order_date,
       ROUND(CASE WHEN po.total_amt > 0 THEN po.received_amt / po.total_amt * 100 ELSE 0 END, 1) AS exec_rate
FROM erp.purchase_order po
JOIN erp.supplier s ON s.id = po.supplier_id;

-- 销售订单执行视图
CREATE OR REPLACE VIEW erp.v_so_exec AS
SELECT so.id, so.so_no, c.name AS customer_name, so.status,
       so.total_qty, so.shipped_amt, so.paid_amt, so.total_amt, so.order_date,
       ROUND(CASE WHEN so.total_amt > 0 THEN so.shipped_amt / so.total_amt * 100 ELSE 0 END, 1) AS ship_rate
FROM erp.sales_order so
JOIN erp.customer c ON c.id = so.customer_id;

-- 应收应付汇总视图
CREATE OR REPLACE VIEW erp.v_finance AS
SELECT '应收' AS biz_type, c.name AS party_name, so.so_no AS doc_no,
       so.total_amt AS amount, so.paid_amt AS settled, so.total_amt - so.paid_amt AS balance
FROM erp.sales_order so JOIN erp.customer c ON c.id = so.customer_id
WHERE so.status IN ('confirmed','partial','shipped')
UNION ALL
SELECT '应付' AS biz_type, s.name AS party_name, po.po_no AS doc_no,
       po.total_amt AS amount, ap.paid_amount AS settled, ap.amount - ap.paid_amount AS balance
FROM erp.account_payable ap
JOIN erp.supplier s ON s.id = ap.supplier_id
JOIN erp.purchase_order po ON po.po_no = ap.doc_no;
