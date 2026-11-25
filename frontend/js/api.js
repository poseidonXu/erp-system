/* 统一 API 请求封装 */
const API = {
  async request(path, data, method) {
    const opt = {
      method: method || (data !== undefined ? 'POST' : 'GET'),
      headers: { 'Content-Type': 'application/json' }
    };
    if (data !== undefined) opt.body = JSON.stringify(data);
    const res = await fetch(path, opt);
    const json = await res.json().catch(() => ({ code: -1, msg: '响应解析失败' }));
    if (json.code !== 0 && json.code !== 401 && json.code !== 403) {
      const err = new Error(json.msg || `请求失败(${json.code})`);
      err.code = json.code;  // 供调用方区分错误类型（如 code=3 表示被引用）
      throw err;
    }
    return json;
  },
  get(path) { return this.request(path); },
  post(path, data) { return this.request(path, data || {}, 'POST'); },

  // 快捷方法
  login(u, p) { return this.post('/api/login', { username: u, password: p }); },
  list(r) { return this.get('/api/' + r); },
  save(r, data) { return this.post('/api/' + r, data); },
  del(r, id, data) { return this.request('/api/' + r + '/' + id, data, 'DELETE'); },
  action(path, data) { return this.post('/api/' + path, data || {}); },
  report(name) { return this.get('/api/report/' + name); },
};
