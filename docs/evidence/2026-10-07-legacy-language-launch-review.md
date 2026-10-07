# 旧库加载失败迁移修复独立审查

2026-10-07；reviewer /root/route_logic，基线a0cb9e2。只审代码、历史已发布DDL和纯合成旧库；未读取默认真实库、密钥、外部来源或模型。

初审107Python/28Node通过；四种nullable旧值(NULL/stem/humanities/任意旧学科)均能升级并保留论文/反馈/曝光/note，pre-v8备份复制后真实重开升级integrityOK，pending时build/maintenance禁止生成、旧卡仍可读，明确保存后revision1ready/重复保存幂等（54e2ea）。两个实际源码desktop隔离子进程也通过（657220），不是native验收。

找到P2：历史提交377d126的discipline为TEXT NOT NULL DEFAULT 'cs_ai'。迁移保留原约束后，ProjectManager无策略显式插None，create_project与空项目get_default重建IntegrityError（e544a6/7c1e43）。已补失败回归并修复为无策略省略列，用旧默认值但revision0仍pending；明确策略只写validated值。

最终独立129Python通过（ba08f0）；三种旧结构/显式策略/空项目/重启/原约束保留探针通过（54362c）；实际源码desktop的NOTNULL、默认路径和空项目启动3项通过（b30cfe）。其他写入入口均用修复创建方法或显式策略保存。budget/diff通过，P2闭合，无剩余P1/P2。

没有另存独立原始日志，引用的是实际工具输出。最终全量、新构建、新包、真实默认原生窗口和原表数据保留由实施者另做，不以源码子进程探针替代；最终11文件记录/证据差异复核通过，无剩余P1/P2；任务验收和评估method/status/blocks_release未降低，预算文件逐字节不变。harness/budget/i18n/diff通过，整体release检查仍exit1，保留原19项门槛和两个预算标志（6f0370）。真实默认窗口、新包构建及原数据比对属于实施者证据。
