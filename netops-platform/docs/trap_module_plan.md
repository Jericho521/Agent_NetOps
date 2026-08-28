# SNMP Trap 接收器开发计划

## 背景
当前平台已通过主动 SNMP 轮询采集指标，但缺少被动告警通道。设备在链路抖动、CPU 突增、配置变更等事件发生时，会主动发送 SNMP Trap。本模块实现 Trap 接收、解析、归一化并接入现有告警系统。

## 目标
1. 在后台持续监听 UDP 162 端口（可配置）。
2. 支持 SNMP v1 / v2c / v3 Trap。
3. 将 Trap 映射为平台告警（Alert），在告警中心展示。
4. 提供配置入口：Community / v3 用户 / 监听端口。
5. 保留原始 Trap 日志，供审计与排错。

## 技术选型
- Python 库：`pysnmp`（>= 4.4 且 < 5，稳定版） 或 `pysnmp-carnegie`。
- 架构：FastAPI startup 时启动独立 asyncio 任务，持续监听 UDP socket。
- 解析：使用 pysnmp 的 `ntforg` / `hlapi` 把 BER 报文解析为 OID → 值列表。

## 数据模型

### `snmp_trap_log` 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str PK | UUID |
| source_ip | str | Trap 来源 IP |
| source_port | int | 来源端口 |
| version | str | v1/v2c/v3 |
| community | str | v1/v2c community（明文或 alias） |
| security_level | str | v3 安全级别 |
| received_at | datetime | 接收时间 |
| pdu_type | str | Trap / Inform / TrapV2 |
| variables | JSON | OID-Value 列表 |
| raw_hex | str | 原始报文 hex（调试） |
| mapped_alert_id | str | FK → alert.id（已生成告警则填） |

### 规则映射表 `trap_rule`（可选本期不做复杂 UI）
| 字段 | 说明 |
|------|------|
| id | UUID |
| oid_prefix | 匹配的 OID 前缀，如 `1.3.6.1.4.1.2011` |
| severity | 1/2/3 |
| message_template | 告警标题模板，支持 `{oid}`、`{value}` |
| enabled | bool |

本期先做**硬编码的常用 Trap 映射表**（华为/H3C/Cisco 常见 Trap OID），后续再开放规则管理 UI。

## 后端任务
1. 安装 `pysnmp` 依赖。
2. 新增 `app/trap_listener.py`：
   - `start_trap_listener(port=162)` 启动监听。
   - 解析报文，提取 OID-Value。
   - 根据来源 IP 找到设备（device.ip）。
   - 根据 OID 匹配规则，生成 `Alert`。
3. 在 `app/main.py` lifespan/startup 中启动监听任务。
4. 新增 `app/routers/trap.py`：
   - `GET /traps`：查询 Trap 日志
   - `GET /traps/rules`：查询映射规则
   - `POST /traps/rules`：新增规则
   - `DELETE /traps/rules/{id}`：删除规则
5. 提供默认规则数据（migration 或 startup 初始化）。

## 前端任务
1. 在设备详情页或全局设置中展示 Trap 监听状态。
2. 告警中心展示 Trap 来源告警（已有 Alert 表，无需新页面）。
3. 新增独立页面 `/traps`：Trap 原始日志列表（可选，如果告警中心已足够可延后）。

## 验证步骤
1. 后端启动后，日志出现 `SNMP Trap listener started on 0.0.0.0:162`。
2. 在华为设备上执行：
   ```
   snmp-agent target-host trap address udp-domain 10.1.100.1 params securityname public v2c
   ```
   （IP 换成后端所在服务器）
3. 触发事件：如 `interface GigabitEthernet1/0/1 shutdown`。
4. 平台告警中心出现对应告警。

## 风险与注意事项
- Windows 下非管理员无法绑定低端口，开发/测试阶段建议监听 `1620` 或运行后端时提升权限。
- Trap 解析可能因厂商私有 OID 失败，需保留 raw_hex 便于排错。
- 同一台机器已有 SNMP 服务占用 162 端口时会报错。

## 优先级
1. 后端监听 + 解析 + 生成告警（核心）
2. 默认 Trap 规则库
3. 前端日志查询页面
4. 设备上配置 Trap target-host 验证
