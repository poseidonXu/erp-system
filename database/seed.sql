-- ============================================================
-- 华晟 ERP 系统 - 初始化种子数据
-- 覆盖：部门/用户/物料/客户/供应商/仓库库位/BOM/期初库存
-- 执行前需先执行 schema.sql
-- ============================================================
SET search_path TO erp, public;

-- 清空业务数据（保留结构），便于重复初始化
TRUNCATE TABLE erp.operation_log, erp.payment_paid, erp.payment_received,
  erp.account_payable, erp.material_issue, erp.work_order, erp.mrp_result, erp.mps,
  erp.stock_ledger, erp.stock_count, erp.stock_transfer, erp.stock_balance,
  erp.purchase_order_item, erp.purchase_order, erp.sales_order_item, erp.sales_order,
  erp.voucher_export, erp.bom_item, erp.bom, erp.location, erp.warehouse,
  erp.customer, erp.supplier, erp.material, erp.sys_user, erp.department,
  erp.sys_param RESTART IDENTITY CASCADE;

-- ---------- 部门 ----------
INSERT INTO erp.department(code,name) VALUES
 ('D01','总经办'),('D02','采购部'),('D03','仓储部'),('D04','销售部'),('D05','生产部'),('D06','财务部');

-- ---------- 用户（密码均 sha256('123456')，演示用） ----------
INSERT INTO erp.sys_user(username,password,real_name,role,dept_id) VALUES
 ('admin','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','系统管理员','admin',1),
 ('buyer01','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','张采购','purchaser',2),
 ('store01','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','李仓管','warehouse',3),
 ('sales01','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','王销售','sales',4),
 ('planner','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','赵计划','planner',5),
 ('finance','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','陈财务','finance',6);

-- ---------- 系统参数 ----------
INSERT INTO erp.sys_param(param_key,param_value,remark) VALUES
 ('PO_PREFIX','PO','采购订单前缀'),('SO_PREFIX','SO','销售订单前缀'),
 ('WO_PREFIX','WO','生产工单前缀'),('SAFETY_STOCK_ALERT','1','库存预警开关');

-- ---------- 物料 ----------
INSERT INTO erp.material(code,name,spec,category,unit,standard_cost,safety_stock,is_batch) VALUES
 ('RM001','冷轧钢板','1.5mm*1250*2500','原材料','张',180,50,false),
 ('RM002','铝合金型材','6063-T5 3m','原材料','根',95,80,false),
 ('RM003','轴承','6204-2RS','外购件','个',12,200,false),
 ('RM004','电机','Y2-90L-4 1.1kW','外购件','台',320,20,false),
 ('SF001','机架组件','自制','半成品','套',560,10,false),
 ('FG001',' centrifugal泵','80-50-200','成品','台',1500,5,true),
 ('FG002','轴流风机','T35-11 No.4','成品','台',900,8,true);

-- ---------- 客户 ----------
INSERT INTO erp.customer(code,name,contact,phone,address,credit_limit) VALUES
 ('C001','华东重工集团','刘经理','13800001001','上海市浦东新区','500000'),
 ('C002','南方装备公司','陈主管','13800001002','广州市黄埔区','300000'),
 ('C003','北方机械制造','孙工','13800001003','北京市通州区','200000');

-- ---------- 供应商 ----------
INSERT INTO erp.supplier(code,name,contact,phone,supply_type,pay_terms) VALUES
 ('S001','宝钢金属材料','周经理','13900002001','钢材/铝材','月结30天'),
 ('S002','万向轴承有限公司','吴销售','13900002002','轴承','月结30天'),
 ('S003','西门子电机','郑经理','13900002003','电机','月结60天');

-- ---------- 仓库与库位 ----------
INSERT INTO erp.warehouse(code,name,location) VALUES
 ('WH01','原料库','厂区A栋1层'),('WH02','半成品库','厂区A栋2层'),('WH03','成品库','厂区B栋');
INSERT INTO erp.location(warehouse_id,code,name) VALUES
 (1,'A-01','原料区A-01'),(1,'A-02','原料区A-02'),(2,'B-01','半成品区'),(3,'C-01','成品区'),(3,'C-02','成品区');

-- ---------- BOM ----------
-- FG001 泵 = 机架1 + 电机1 + 轴承2 + 钢板1
INSERT INTO erp.bom(product_id,version,qty_base,effective_date) VALUES (6,'V1',1,CURRENT_DATE);
INSERT INTO erp.bom_item(bom_id,material_id,qty,loss_rate) VALUES
 (1,5,1,0),(1,4,1,0),(1,3,2,1),(1,1,1,0);
-- SF001 机架 = 钢板2 + 铝型材1
INSERT INTO erp.bom(product_id,version,qty_base,effective_date) VALUES (5,'V1',1,CURRENT_DATE);
INSERT INTO erp.bom_item(bom_id,material_id,qty,loss_rate) VALUES
 (2,1,2,2),(2,2,1,0);

-- ---------- 期初库存（同时写结存 + 分类账，保证账实相符） ----------
INSERT INTO erp.stock_balance(material_id,warehouse_id,location_id,qty,avg_cost) VALUES
 (1,1,1,120,180),(2,1,2,200,95),(3,1,1,500,12),
 (4,1,2,60,320),(5,2,3,25,560),(6,3,4,12,1500),(7,3,5,15,900);
INSERT INTO erp.stock_ledger(txn_no,doc_type,doc_no,material_id,warehouse_id,location_id,qty,cost,direction,operator,remark) VALUES
 ('TXN-INIT-001','期初建账','INIT',1,1,1,120,180,'IN','admin','系统初始化'),
 ('TXN-INIT-002','期初建账','INIT',2,1,2,200,95,'IN','admin','系统初始化'),
 ('TXN-INIT-003','期初建账','INIT',3,1,1,500,12,'IN','admin','系统初始化'),
 ('TXN-INIT-004','期初建账','INIT',4,1,2,60,320,'IN','admin','系统初始化'),
 ('TXN-INIT-005','期初建账','INIT',5,2,3,25,560,'IN','admin','系统初始化'),
 ('TXN-INIT-006','期初建账','INIT',6,3,4,12,1500,'IN','admin','系统初始化'),
 ('TXN-INIT-007','期初建账','INIT',7,3,5,15,900,'IN','admin','系统初始化');
