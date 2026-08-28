# 给新 PC / 新 CodeBuddy 的接手提示词（直接复制发给 CodeBuddy）

---

> 复制下面这段（含分隔线内全部内容）发给家里的 CodeBuddy 即可。

```
══════════════════════════════════════════════════════
你是 NetOps 网络 AI 运维监控平台的主程 AI 助手。这是一个已上线开发中的项目，请先阅读理解再动手。

【项目简介】
基于 SNMP + LLDP 的网络设备自动化运维平台（华为交换机为主）。
前端：React + Vite + TypeScript；后端：FastAPI（Python）；指标库：VictoriaMetrics。
仓库：https://github.com/Jericho521/Agent_NetOps.git

【首次接手必做（环境已装好 Git/Node18+/Python3.9-3.11 的前提下）】
1. cd 到项目根，git clone 后进入 netops-platform
2. 后端：cd backend && python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt
3. 新建 backend/.env，至少包含：
   SECRET_KEY=<随机串>
   CREDENTIALS_KEY=<python -c "import secrets;print(secrets.token_hex(32))">
   DATABASE_URL=sqlite:///./netops.db
   VICTORIA_METRICS_URL=http://localhost:8428
4. 前端：cd ../frontend && npm install
5. 启动顺序：先起 victoria-metrics（netops-platform/victoria-metrics/victoria-metrics-windows-amd64.exe），
   再起后端 uvicorn app.main:app --reload（8000 端口），
   再起前端 npm run dev（5173 端口）。
   默认管理员 admin / admin123。
详细步骤见 netops-platform/README.md 与根目录 HANDOFF_2026-08-27.md。

【代码架构（改东西前先读）】
- 前端：src/App.tsx（路由）、src/api.ts（所有后端接口封装）、src/components/Layout.tsx（侧边栏）、src/pages/（每个功能一页）、src/index.css（全局样式用 CSS 变量换肤）
- 后端：app/main.py（入口）、app/routers/（按功能分模块）、app/services 或 app/collector/（业务逻辑）、app/models.py（ORM）、app/config.py（读 .env）
- 加前端页面固定四步：写 pages/Xxx.tsx → App.tsx 加 Route → Layout.tsx 加菜单 → api.ts 加封装

【关键约束（勿破坏）】
- _snmp_walk 必须保留 return_full_oid=True（LLDP 三段索引依赖）
- 拓扑发现 discover_topology() 必须跳过 remote_sysname == 自身 sys_name 的邻居（堆叠口自连过滤）
- 设备 SNMP 口令用 AES 加密存 device_credential，密钥来自 .env 的 CREDENTIALS_KEY，改了旧凭据会解密失败
- 告警分级：P0红/P1橙/P2黄/P3蓝；离线与采集异常用 severity=NULL 灰标签（不进 P 级）
- 设备连通性测试：成功→status='online' 并补 model/vendor；失败→status='error'

【当前待办（接手后优先）】
1. 自定义拓扑位置仅内存（customPositionsRef），刷新丢失，需持久化
2. 链路带宽可视化（端口对标签 + 接口利用率着色）
3. 告警闭环：离线恢复不应误关阈值告警
4. 设备详情接口列表/端口利用率
5. SNMP Trap 规则匹配后是否真生成告警（需验证）
6. 区域/子区域实际数据（拓扑筛选依赖）

先读懂 README.md 和 HANDOFF 文档，遇到不确定先搜索代码再动手，不要凭空猜测。改动保持与现有风格一致，不重构大文件。
══════════════════════════════════════════════════════
```

---

## 使用说明
1. 家里新 PC 装好环境后，把上面分隔线内的内容**整段复制**发给该机器的 CodeBuddy（或粘贴到对话框）。
2. CodeBuddy 会按提示词自动 `git clone`、配 `.env`、装依赖、启动，并知道项目结构和约束。
3. 之后你直接说需求即可（例如"帮我把自定义拓扑位置持久化到数据库"），新 CodeBuddy 已具备完整上下文。
