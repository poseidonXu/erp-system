# -*- coding: utf-8 -*-
"""通用工具：统一响应、JSON 参数解析、异常处理"""
import hashlib
import functools
from flask import jsonify, request


def ok(data=None, msg="success", **extra):
    resp = {"code": 0, "msg": msg, "data": data}
    resp.update(extra)
    return jsonify(resp)


def fail(msg="error", code=1, status=200):
    return jsonify({"code": code, "msg": msg}), status


def body():
    return request.get_json(silent=True) or {}


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def handle_errors(fn):
    """把异常转成统一 JSON 错误响应，避免前端拿到 HTML 500 页"""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ValueError as e:
            return fail(str(e), code=2)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return fail(f"服务器错误: {e}", code=1)
    return wrapper
