# 网络 AI 运维监控平台 — 开发进度（MVP）

> 基础环境文档更新时间：2026-08-24
> **最新进展与交接见同目录 `HANDOFF_2026-08-25.md`（告警分级、区域/子区域、拓扑管理、MIB 修复等）**
> 项目目录：`d:\Agent_NetOps\netops-platform\`
> 对话助手：CodeBuddy（关闭后可从历史会话恢复，本文件为离线备份）

---

## 一、总体状态

代码已全部写完，后端已验证可加载（24 个路由）。**端到端联调尚未跑通**，本次已补齐环境：Node.js 已安装，VictoriaMetrics 已就绪。

| 模块 | 状态 |
|------|------|
| 后端基础 / 凭据加密 / 设备API / SNMP / VM客户端 / 调度器 / 指标API / 告警 / 前端三页 / MCP | ✅ 完成 |
| 端到端联调（启服务 + 浏览器验证） | ⏳ 待做（见下方步骤） |

---

## 二、环境状态（2026-08-24 实测）

- **Python**：`C:\Users\Jericho\AppData\Local\Programs\Python\Python313\python.exe`（3.13）
- **后端虚拟环境**：`d:\Agent_NetOps\netops-platform\backend\.venv`（依赖已装）
- **Node.js**：✅ 已装 `C:\Program Files\nodejs\node.exe` v24.19.0
- **VictoriaMetrics**：✅ 已就绪 `d:\Agent_NetOps\victoria-metrics\victoria-metrics-windows-amd64-prod.exe`（注意带 `-prod` 后缀）
- **默认管理员**：`admin` / `admin123`

---

## 三、启动步骤（按顺序，每个开独立窗口）

### 第 1 步：启动 VictoriaMetrics（先开，别关）
```powershell
cd d:\Agent_NetOps\victoria-metrics
.\victoria-metrics-windows-amd64-prod.exe -storageDataPath=./data
```
> exe 名带 `-prod`；`-storageDataPath=./data` 复用已有 data 目录。

### 第 2 步：启动后端（新窗口）
```powershell
cd d:\Agent_NetOps\netops-platform\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
> 首次启动自动建 SQLite 表 + 创建 admin 账号。改过 config.py 后需重启。

### 第 3 步：启动前端（**必须新开 PowerShell 窗口**让 Node 的 PATH 生效）
```powershell
cd d:\Agent_NetOps\netops-platform\frontend
npm install   # 第一次需要，之后可跳过
npm run dev
```

### 第 4 步：访问
浏览器开 http://localhost:3000 ，登录 `admin` / `admin123`。
创建设备验证不再报 `CREDENTIALS_KEY` 错误；设备详情看 ECharts 曲线需 VM 在跑且调度器已采集至少一轮（60s）。

---

## 四、已修复的关键问题

1. pysnmp 版本改为 `>=5.1.0`（实测 v7.1.29）。
2. `devices.py`：`test_connectivity` 的 `Depends` 多逗号；`_save_credentials` 缺 `async` + 调用缺 `await`，已修。
3. `models.py`：加 `from __future__ import annotations`，`Mapped[X|None]` 改 `Mapped[Optional[X]]`。
4. **`.env` 读取路径**：`config.py` 改为 `Path(__file__).resolve().parent.parent.parent / ".env"` 绝对路径（修复「创建设备报 CREDENTIALS_KEY 未设置」）。

---

## 五、项目结构速查

```
netops-platform/
├── .env                      # 密钥（根目录）
├── README.md / docker-compose.yml
├── backend/
│   ├── .venv/  netops.db(自动生成)
│   ├── requirements.txt
│   └── app/{main,config,db,models,schemas}.py
│       ├── security/  credentials.py(AES) jwt_auth.py
│       ├── routers/   auth devices metrics alerts
│       ├── collector/ snmp victoriametrics scheduler templates
│       ├── alerting/  rules evaluator
│       └── mcp/       server.py
└── frontend/
    ├── package.json vite.config.ts index.html
    └── src/ main App api components pages
```

---

*关闭 CodeBuddy 不丢文件/对话历史；关 uvicorn/VM/npm 窗口只是停进程，数据都在磁盘上，重启即可。*
