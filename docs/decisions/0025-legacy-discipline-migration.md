# ADR0025：兼容旧 discipline 字段的语言升级

2026-10-07；实际默认库在版本8已经有discipline TEXT。Route语言升级009重复添加，初始化异常导致原生首页Load failed。临时干净v8验收没有覆盖这条真实旧结构。

只在旧projects已有discipline时跳过这一个字段添加，保留原列和原值，其余新字段和语言证据表仍原子创建。旧字段不等于用户选过语言：policy_from_row须language_policy_revision>0才ready。保留pending、原数据、迁移备份和失败回滚/重试；不猜语言，不删除旧列，不直接改用户数据库版本。

独立审查发现历史字段还带NOT NULL DEFAULT 'cs_ai'，未提供策略的创建若显式插NULL会失败，包括删空库后的默认项目重建。ProjectManager在没有策略时省略discipline列，让原约束和默认值继续生效；revision0仍pending。显式语言策略才写validated discipline/revision1，不重建旧表或删除约束。

新增真实结构的合成失败回归、保存旧值/论文/备份/重复启动，以及版本登记失败时原列保留、新列回滚/重试；历史非空结构覆盖兼容创建、明确选择语言和默认项目重建。独立审查和新包/native默认启动结果见[检查](../evidence/2026-10-07-legacy-language-launch-checks.txt)。没有模型、预算或外发范围变化。
