# -*- coding: utf-8 -*-
"""华晟 ERP 系统 - Flask 应用入口
启动: python app.py   默认 http://127.0.0.1:5000
"""
import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

from config import DEBUG, HOST, PORT

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
CORS(app)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# ---------- 注册业务路由 ----------
# 注意顺序：base_data 中的通用 /api/<resource> 会匹配 /api/boms 等，
# 因此把含更具体路径的蓝图放在后面无法解决，需在 base_data 内用严格白名单（已实现），
# 且具体 Xxx 路由与通用路由路径不冲突（通用路由只处理 RESOURCES 白名单内的资源名）。
from routes import auth, purchase, sales, production, inventory, finance, reports, base_data

for bp in (auth.bp, purchase.bp, sales.bp, production.bp, inventory.bp, finance.bp, reports.bp, base_data.bp):
    app.register_blueprint(bp)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"code": 404, "msg": "接口不存在"}), 404


if __name__ == "__main__":
    print("=" * 60)
    print("  华晟 ERP 系统后端已启动")
    print(f"  访问地址: http://127.0.0.1:{PORT}")
    print(f"  数据库:   HighGo 127.0.0.1:5866 / erp schema")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
