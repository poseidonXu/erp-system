# -*- coding: utf-8 -*-
"""系统配置 —— 数据库与全局参数"""
import os

# HighGo (PostgreSQL 10.6 兼容) 连接参数
DB_HOST = os.getenv("ERP_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("ERP_DB_PORT", "5866"))
DB_USER = os.getenv("ERP_DB_USER", "highgo")
# 本地演示库的教材示例密码；部署时请设置环境变量 ERP_DB_PASSWORD 覆盖
DB_PASSWORD = os.getenv("ERP_DB_PASSWORD", "highgo5866")
DB_NAME = os.getenv("ERP_DB_NAME", "highgo")
DB_SCHEMA = "erp"

DSN = {
    "host": DB_HOST,
    "port": DB_PORT,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "dbname": DB_NAME,
    "connect_timeout": 10,
}

SECRET_KEY = "hs-erp-demo-secret-key-2026"
DEBUG = True
HOST = "0.0.0.0"
PORT = 5000
