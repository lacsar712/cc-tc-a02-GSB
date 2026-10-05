# 隧道收敛测缝台

测量员登记里程桩号、点选围岩等级与收敛毫米值。软岩、硬岩各有一套**合格闭区间**（不设全线统一门槛），接口进程内后台线程认领待判行（不另起 worker 容器）：认领那一刻把当时档位的上下限**抄进单据快照**，判定只吃快照，事后改档不影响已领走的单据。页面是 Svelte。

## 规则口径

- 档位字典：`soft`=软岩（初始闭区间 [-3.0, 3.0] mm）、`hard`=硬岩（初始 [-2.0, 2.0] mm），闭区间端点算合格。
- 新单**必须点选围岩等级**，漏选或口径与字典对不上，整份 400 退回、不落库。
- 改档（上下限）只允许测量员操作，每次改动写一条改档履历；只影响改档之后认领的单据。
- 巡检员只能翻单据表和改档履历，不能改档也不能报数。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16（`Base.metadata.create_all` 建表，旧库自动幂等补列）

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可报数、可改档 |
| inspector | insp123456 | 只读（翻表、翻履历） |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 接口

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/zones` | 登录 | 当前档位（专页上块） |
| PUT | `/api/zones/<grade>` | 测量员 | 改上下限，body：`lower_limit_mm`、`upper_limit_mm`，自动写履历 |
| GET | `/api/zones/history?grade=` | 登录 | 改档履历（专页中块） |
| GET | `/api/logs` | 登录 | 单据列表（含等级与认领快照，专页下块同源） |
| POST | `/api/logs` | 测量员 | body 必须含 `chainage`、`delta_mm`、`rock_grade` |

## 种子

| 桩号 | 等级 | 收敛 | 结论 |
|------|------|------|------|
| K12+180 | 软岩 | 1.2 mm | 合格 |
| K18+040 | 硬岩 | 5.6 mm | 超限 |
