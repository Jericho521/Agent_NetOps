# 网络 AI 运维监控平台 (NetOps Platform)

> MVP 版本 - 最小可用系统

## 快速启动（本机 Windows，无需 PostgreSQL）

### 前置条件

- Python 3.11+（本机已确认: 3.13.13）
- Node.js 18+（用于前端）
- VictoriaMetrics（时序库，下载 exe 双击启动）

---

### 第一步：准备密钥

在 `netops-platform` 目录下打开 PowerShell：

```powershell
cd "d:/Agent_NetOps/netops-platform"
Copy-Item .env.example .env
python -c "import base64,os; print('CREDENTIALS_KEY='+base64.urlsafe_b64encode(os.urandom(32)).decode()); print('JWT_SECRET='+base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

把输出的两行复制，打开 `.env` 文件填到对应位置：
- `CREDENTIALS_KEY=` 后面粘贴第一个值
- `JWT_SECRET=` 后面粘贴第二个值
- `DATABASE_URL` 保持默认 SQLite（无需改动）
- `VM_URL` 保持默认 `http://localhost:8428`

### 第二步：启动 VictoriaMetrics（一次性）

1. 下载 [VictoriaMetrics](https://github.com/VictoriaMetrics/VictoriaMetrics/releases) 的 `victoria-metrics-windows-amd64.exe`
2. 放到如 `d:/tools/vm/` 目录
3. 新开 PowerShell 窗口运行：

```powershell
cd d:/tools/vm
.\victoria-metrics-windows-amd64.exe -retentionPeriod=90d -storageDataPath=.\vmdata
```

窗口保持开着（这是时序库服务）。

### 第三步：启动后端

新开 PowerShell 窗口：

```powershell
cd "d:/Agent_NetOps/netops-platform/backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 第四步：启动前端

再新开 PowerShell 窗口：

```powershell
cd "d:/Agent_NetOps/netops-platform/frontend"
npm install
npm run dev
```

### 第五步：访问

- 前端页面：http://localhost:3000
- 后端 API 文档：http://localhost:8000/docs
- 默认账号：`admin` / `admin123`

---

## 项目结构

```
netops-platform/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py         # FastAPI 入口
│   │   ├── config.py       # 配置读取
│   │   ├── db.py           # 数据库引擎
│   │   ├── models.py       # SQLAlchemy 模型
│   │   ├── schemas.py      # Pydantic 模型
│   │   ├── routers/        # API 路由
│   │   ├── collector/      # SNMP 采集器
│   │   ├── alerting/       # 告警引擎
│   │   ├── mcp/            # MCP Server
│   │   └── security/       # 安全模块
│   └── requirements.txt
├── frontend/               # React 前端
│   └── src/
├── docker-compose.yml      # 可选生产部署
├── .env.example            # 环境变量模板
└── README.md
```

## 核心功能（MVP）

| 模块 | 功能 |
|------|------|
| 设备管理 | CRUD、批量 CSV 导入、按厂商/角色筛选 |
| 凭据管理 | SNMP v2c/v3 凭据 AES-256-GCM 加密存储 |
| SNMP 采集 | pysnmp 异步轮询 CPU/内存/接口流量 |
| 时序存储 | VictoriaMetrics（PromQL 兼容） |
| 告警系统 | 阈值规则 + 周期评估 + 告警台展示 |
| 前端仪表盘 | 登录、设备列表、设备详情（ECharts 曲线） |
| MCP Server | list_devices / get_device_metrics 工具 |

## 如何添加第一台设备

1. 登录前端页面（admin/admin123）
2. 进入「设备管理」→「添加设备」
3. 填写：
   - 名称：如 `边界交换机-S620`
   - IP：`192.168.10.1`（或你的设备 IP）
   - 厂商：`huawei`
   - SNMP 版本：`3`
   - SNMP 用户名/认证密码/加密密码（根据你的设备配置）
4. 保存后等待 1-2 分钟，进入「设备详情」查看实时曲线

## 验证 SNMP 采集成功

- 设备列表中状态显示为「在线」（绿色）
- 设备详情页能看到 CPU、内存、接口流量的实时曲线图
- 或访问 http://localhost:8000/devices 查看 API 返回的数据

## 常见排错

| 问题 | 解决方案 |
|------|----------|
| 后端启动报 `KeyError` | 检查 `.env` 文件是否存在且填写了 CREDENTIALS_KEY 和 JWT_SECRET |
| 设备状态一直是「不可达」 | 检查设备 IP 是否可达、SNMP 服务是否开启、凭据是否正确 |
| 前端图表无数据 | 确保 VictoriaMetrics 已启动且后端日志无写入错误 |
| `aiosqlite` 安装失败 | 升级 pip：`python -m pip install --upgrade pip` 再重试 |

## 环境变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| DATABASE_URL | 数据库连接（SQLite/PostgreSQL） | `sqlite+aiosqlite:///./netops.db` |
| CREDENTIALS_KEY | 凭据加密密钥（Base64 编码的 32 字节随机值） | **必须设置** |
| JWT_SECRET | JWT 签名密钥（Base64 编码的 32 字节随机值） | **必须设置** |
| VM_URL | VictoriaMetrics 地址 | `http://localhost:8428` |

## 可选：Docker Compose 生产部署

```bash
docker compose up -d
```

详见 `docker-compose.yml`。生产模式使用 PostgreSQL + Docker 化的所有组件。
