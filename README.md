# 02-batchgate（闸序）

Batchgate — 离线作业依赖编排：作业定义 → 依赖就绪检查 → 执行/失败重试 → 产出水位与对账。

与 Feedstitch（多源 Feed 归并）主链路不同，禁止做成 Feed 解析/冲突/回看换皮。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5200 |
| API | http://localhost:10200 |

## 主链

配置作业与依赖 → 触发一次编排 Run → 按依赖层执行夹具作业 → 写入尝试记录与产出水位 → 报告对账

## 依赖边：硬 / 软

每条依赖边带类型：

| 类型 | 上游未就绪时 | 尝试状态 |
| --- | --- | --- |
| `hard` | 下游**不得执行** | `skipped_hard`（报告计入「硬阻断」） |
| `soft` | 下游**照常执行**，可降级 | `degraded`（报告计入「软降级」） |

- 依赖边在「作业」页可增删改（上游 + 硬/软），保存后写入 SQLite，刷新/重启后仍在。
- 报告中的 `succeeded / failed / hard_skipped / soft_degraded` 全部由尝试记录推导，
  `reconciliation.balanced=true` 表示四项之和等于 `attempt_count`；
  `GET /api/orchestrations/{id}/reconcile` 可随时用尝试记录重算并比对。
- 水位页只显示真正执行成功的作业；软降级的输出不推进水位（可能不完整），但在尝试记录里保留降级标记与结果。

### 复现两条路径（编排台/作业页即可操作）

1. **硬阻断**：作业页把 `ingest_orders` 夹具切到 `ingest_orders_fault.json` → 执行编排。
   结果：`ingest_orders` failed、`dim_customer` success、`fact_order_daily` skipped_hard（`blocked_by` 指向失败上游）。
2. **软降级仍执行**：作业页把 `fact_order_daily` 的 `dim_customer` 边改成「软」并停用 `dim_customer` → 执行编排。
   结果：`fact_order_daily` 仍被执行（状态 `degraded`，`detail.soft_missing` 标出缺失上游），未被跳过。

## 种子说明

- **ingest_orders**：无依赖，写出订单水位。
- **dim_customer**：无依赖，写出客户维表水位。
- **fact_order_daily**：两条硬依赖，上游成功后才执行。

## 尝试状态

| 状态 | 含义 |
| --- | --- |
| `success` | 正常执行成功 |
| `failed` | 执行报错 |
| `skipped_hard` | 硬依赖未就绪，被阻断跳过（旧数据 `skipped_dep` 同样计入硬阻断） |
| `degraded` | 软依赖未就绪，降级执行 |

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现）

`retry_budget` / `watermark_reconcile`（严格水位闸）/ `sla_breach`
（`dep_gate` 的硬/软分流已落地，见上）
