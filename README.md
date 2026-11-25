# 华晟 ERP 系统（HighGo 版）

一个基于《ERP系统需求规格说明书（模拟样例）》实现的教学演示型 ERP 系统。
**Python Flask + HighGo 数据库 + 原生前端**，可用 VSCode 直接开发调试。

> **Author: henry** — 基于 HighGo 数据库的模块化 ERP 教学演示项目

## 快速开始

```bash
# 1. 确保 HighGo 数据库已运行（双击根目录 启动HighGo.lnk）
# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库（建表 + 演示数据）
python database/init_db.py

# 4. 启动服务
cd backend && python app.py
# 或双击 run.bat / VSCode 按 F5
```

浏览器访问 <http://127.0.0.1:5000>，账号 `admin` / `123456`。

## 功能

- **基础数据**：物料、客户、供应商、仓库库位、BOM
- **采购**：采购订单 → 确认 → 到货入库（自动记账 + 应付 + 凭证）
- **销售**：销售订单（信用校验）→ 发货出库 → 收款核销
- **库存**：库存结存、出入库分类账、盘点、预警、调整
- **生产**：MPS、MRP 运算（BOM 展开/净需求）、工单、领料、完工入库
- **财务**：应付/应收、付款核销、凭证导出
- **报表**：经营看板 + 7 张报表 + CSV 导出
- **系统**：用户、角色、操作日志、参数

## 文档与目录

- 开发文档：[docs/开发文档.md](docs/开发文档.md)
- 数据库脚本：`database/schema.sql`、`database/seed.sql`
- 后端代码：`backend/`（分层：配置/数据层/路由）
- 前端代码：`frontend/`（免构建，刷新即用）
- VSCode 配置：`.vscode/`

## 连接信息

HighGo `127.0.0.1:5866` / 库 `highgo` / 用户 `highgo` / Schema `erp`

密码不写入代码，通过环境变量提供：

```bash
# Windows PowerShell
$env:ERP_DB_PASSWORD = "你的数据库密码"
# 或在 backend/config.py 中修改 ERP_DB_PASSWORD 的默认值（仅本地使用）
```

演示库默认密码为 `highgo5866`（见教材），生产环境请务必修改。
