# 森井地暖·并行巡检规程工时等效复核

针对同一区段配对的旧/新规程工时差跑 TOST，按可接受分钟差给区间和裁决，分开显示差异方向与证据不足。新旧规程计时工单分开提交，同批区段的补测、更正与撤回可按任意顺序到达。

## 模拟场景

[业务剧本](yangyang-business.md)记录模拟团队、上游观测、统计口径和交接去向。四个工作模块包括批次台账、分析任务、结果与复核、报表分发。调度员分别为旧、新规程导入 UTF-8 CSV 计时工单，缺一侧的区段先列为缺单，不混入比较。分析员提交后，Python worker 对固化工单快照计算；同一区段若有补测，会形成多种新旧配法，只有全部配法裁决一致时才给出结论。负责人签核，随后可以下载结果或把报告定时投递到本地收件箱。

## 启动

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

浏览器打开 `http://127.0.0.1:18384`。API 健康检查位于 `http://127.0.0.1:19384/api/health`，数据库本地端口 `17884`。停机用 `docker compose down`。只有要重做演示数据时才加 `-v` 清除命名卷。

## 演示账号

| 角色 | 邮箱 | 演示密码 | 可执行动作 |
|---|---|---|---|
| 业务分析员 | `analyst@demo.local` | `Analyst-2026!` | 登记批次、分开导入新旧计时、补测/更正/撤回、提交分析、下载内部结果 |
| 复核负责人 | `supervisor@demo.local` | `Supervisor-2026!` | 导入资料、签核或退回、安排或停止分发、查审计 |
| 只读查看 | `viewer@demo.local` | `Viewer-2026!` | 查看台账、已签核结果和本地收件箱 |

`.env` 以 `.env.example` 为模板。`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 可做本机端口调整。Docker 私有子网可通过 `NETWORK_SUBNET` 覆盖。`JWT_SECRET` 和 `DB_PASSWORD` 为本地演示配置。`SEED_DEMO=false` 可跳过自动种子。所有公开端口绑定在回环地址。首次执行种子后，后续种子只补一个演示批次，不覆盖已录入数据。

## 模块和本地开发

| 服务 | 技术 | 用途 |
|---|---|---|
| frontend | HTML、CSS、ES Modules、Nginx | 工作台、批次台账与报告 |
| backend | Python 3.12、FastAPI、SQLAlchemy | 校验、工单快照、业务 API 和 JWT |
| worker | Python 3.12、Redis | 计算排队、心跳和到时导出 |
| db | PostgreSQL 16 | 批次、工单、快照、签核、分发计划和审计 |
| redis | Redis 7 | 唤醒、心跳和登录限流 |

在 `backend` 中可用 `pip install -r requirements.txt` 安装本地依赖，设置 `DATABASE_URL`、`REDIS_URL` 和可写 `ARTIFACT_ROOT` 后运行 `uvicorn src.main:app --port 8000`，计算进程运行 `python -m src.worker`。前端修改在 `frontend/src`，用 `docker compose up -d --build frontend` 通过 Nginx 检查同源代理。业务输入定义在 `backend/src/domain/spec.json`，工单解析在同目录的 `tickets.py`，算法在 `analysis.py`。角色、任务状态和工单状态在后端 `backend/src/constants/enums.py` 和前端 `frontend/src/constants/enums.js` 共同定义。数据库表在 `backend/src/models/workflow.py`。后端测试用 `python -m pytest tests`（测试库为临时 SQLite，不依赖 Docker）。

批次内工单按区段解析：更正与撤回用 `target_code` 引用目标工单，因此到达顺序不影响结果；撤回一条更正会恢复它原先替换的计时。每个区段旧、新各取一张有效工单形成一种配法，全部配法裁决一致才给结论；不一致时列出卡住裁决的配法。并发更正后待复核结论会作废并重算，重算期间仍可按当时快照复现旧结论，但旧结论不能再签核。失败或受阻的分析重试不新增版本。已签核结论保留在原版本，后续工单另开新版本。

分发计划锁定特定已签核快照，按北京时间显示。收件箱可下载真实 CSV，当前收件组是本地交接标签。停机跨过多个周期时补送最早未投递的一期，然后追到下一个将来的周期。新快照需重新签核并建新计划。

许可证为 [MIT](LICENSE)。
