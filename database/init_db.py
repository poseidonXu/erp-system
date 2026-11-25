# -*- coding: utf-8 -*-
"""一键初始化 HighGo 数据库：建表 + 加载种子数据
用法: python database/init_db.py
"""
import os
import sys
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))
from config import DSN


def run_sql_file(cur, path):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    cur.execute(sql)
    print(f"  ✓ 已执行 {os.path.basename(path)}")


def main():
    print("正在连接 HighGo:", f"{DSN['host']}:{DSN['port']}/{DSN['dbname']}")
    try:
        conn = psycopg2.connect(**DSN)
    except Exception as e:
        print("连接失败:", e)
        print("请确认 HighGo 数据库已启动（双击项目根目录的 启动HighGo.lnk）")
        return
    cur = conn.cursor()
    try:
        # 重置语义：先清理整个 erp schema，保证可重复执行
        cur.execute("DROP SCHEMA IF EXISTS erp CASCADE")
        conn.commit()
        print("  ✓ 已清理旧 erp schema")
        run_sql_file(cur, os.path.join(HERE, "schema.sql"))
        conn.commit()
        run_sql_file(cur, os.path.join(HERE, "seed.sql"))
        conn.commit()
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='erp'")
        print(f"初始化完成：erp schema 共 {cur.fetchone()[0]} 张表")
    except Exception as e:
        conn.rollback()
        print("初始化失败:", e)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
