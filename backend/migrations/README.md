# 数据表初始化

本版通过 `src.models.base.Base.metadata.create_all` 创建首次运行所需的六张表：`batches`、`tickets`、`analysis_runs`、`reviews`、`schedules`、`deliveries`，另加 `audit_events`。模型在 `src/models/workflow.py`。分析运行按 `batch_id + version` 唯一，`ticket_snapshot` 冻结参与计算的全部工单，`superseded_by` 指向取代它的新版本。工单以 `batch_id + code` 唯一，更正与撤回通过 `target_code` 引用目标工单。

本版是一次结构重置：旧版 `observations` 表不再使用，如需保留旧数据请在升级前导出。`python -m scripts.seed_demo` 只在演示批次缺失时补全 64 张工单，保留现有分析及签核。数据库端口只发布到本机。
