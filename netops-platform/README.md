# NetOps 网络 AI 运维监控平台

基于 **SNMP + LLDP** 的网络设备自动化运维平台（华为交换机为主）。
前后端分离：**FastAPI（Python）** + **React + Vite + TypeScript（前端）**，指标存储用 **VictoriaMetrics**。

---

## 一、环境依赖（新机器必装）

| 工具 | 版本 | 下载 |
|------|------|------|
| Git | 新版 | https://git-scm.com/download/win |
| Node.js + npm | ≥ 18（建议 20 LTS） | https://nodejs.org |
| Python | 3.9 ~ 3.11 | https://www.python.org/downloads/ （装时勾 Add to PATH） |
| VictoriaMetrics | 单机版 | https://github.com/VictoriaMetrics/VictoriaMetrics/releases （找 `victoria-metrics-windows-amd64.exe`） |

> 安装完请**重启终端**，确保 `git` / `node` / `python` 在 PATH 中。

---

## 二、克隆项目

```powershell
git clone https://github.com/Jericho521/Agent_NetOps.git
cd Agent_NetOps/netops-platform
```

---

## 三、配置后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1              # 激活虚拟环境（Linux/Mac 用 source .venv/bin/activate）
pip install -r requirements.txt
```

### 创建 `backend/.env`（必须，没有它后端起不来）

新建文件 `backend/.env`，内容：

```ini
SECRET_KEY=请换成任意随机字符串例如netops-secret-2026
CREDENTIALS_KEY=请换成32字节hex，例如00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff
DATABASE_URL=sqlite:///./netops.db
VICTORIA_METRICS_URL=http://localhost:8428
```

生成 `CREDENTIALS_KEY` 的命令：
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

> ⚠️ `.env` 已在 `.gitignore` 中，**不会入库**。换机器必须自己重建。
> ⚠️ `CREDENTIALS_KEY` 用于 AES 加密设备 SNMP 口令，改了会导致旧设备凭据解密失败（需重新录入设备凭据）。

---

## 四、配置前端

```powershell
cd ..\frontend
npm install
```

---

## 五、启动（顺序很重要：先 VictoriaMetrics → 后端 → 前端）

### 终端 A：VictoriaMetrics（指标库，必须先起）
把下载的 `victoria-metrics-windows-amd64.exe` 放到 `netops-platform/victoria-metrics/` 目录，然后：
```powershell
cd netops-platform\victoria-metrics
.\victoria-metrics-windows-amd64.exe     # 默认监听 8428
```

### 终端 B：后端
```powershell
cd netops-platform\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 终端 C：前端
```powershell
cd netops-platform\frontend
npm run dev
```
前端开发服务器默认 http://localhost:5173

### 访问
- 前端页面：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- **默认管理员账号：`admin` / `admin123`**

> 提示：前端 `npm run build` 后也可由后端静态托管，直接用 http://localhost:8000 访问。

---

## 六、端口被占用怎么办
```powershell
netstat -ano | findstr :8000
taskkill /PID <占用PID> /F
```

---

## 七、目录结构

```
netops-platform/
├─ backend/                # FastAPI
│  ├─ app/
│  │  ├─ main.py           # 入口
│  │  ├─ config.py         # 配置读取（来自 .env）
│  │  ├─ db.py             # 数据库引擎 + 建表
│  │  ├─ models.py         # ORM 模型
│  │  ├─ schemas.py        # Pydantic
│  │  ├─ collector/        # SNMP 采集 / 拓扑发现 / 调度 / VictoriaMetrics
│  │  ├─ routers/          # 按功能分模块路由
│  │  ├─ alerting/         # 告警规则引擎
│  │  ├─ security/         # JWT + 凭据加解密
│  │  └─ mcp/              # MCP 服务（AI 助手用）
│  └─ requirements.txt
├─ frontend/               # React + Vite + TS
│  ├─ src/
│  │  ├─ App.tsx           # 路由
│  │  ├─ api.ts            # 后端接口封装（前端只在这里拼 URL）
│  │  ├─ components/Layout.tsx  # 侧边栏导航
│  │  └─ pages/            # 每个功能一个文件
│  └─ public/              # 静态资源（logo.ico / logo-512.png）
└─ victoria-metrics/       # 时序数据库可执行文件
```

---

## 八、开发约定速查

- **加新页面**：写 `src/pages/Xxx.tsx` → `App.tsx` 加 `<Route>` → `Layout.tsx` 加菜单 → `api.ts` 加接口封装
- **告警分级**：P0 红 / P1 橙 / P2 黄 / P3 蓝；离线/采集异常用 severity=NULL 灰标签（不进 P 级）
- **重要链路**：`Link.is_critical`，中断生成 P0
- **拓扑自连过滤**：`discover_topology()` 跳过 `remote_sysname == 自身` 的邻居（堆叠口自连）
- **SNMP 采集**：优先 v3，默认 v3；云汉核心需设备端放行 LLDP 子树 `1.0.8802`
- **`_snmp_walk` 保留 `return_full_oid=True`**（LLDP 三段索引依赖）

---

## 九、详细说明
更完整的开发/交接记录见仓库根目录：
- `HANDOFF_2026-08-27.md`（多机同步、环境、最近改动）
- `HANDOFF_2026-08-25.md`（详尽功能开发史）
- `NetOps平台开发进度.md`（最早项目计划）
