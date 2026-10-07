# ADR 0026：一次点击判断当前全部论文

2026-10-07。用户明确要求一次点击看完当前全部待判断论文，此前整体授权持续有效。该指令授权多篇公开元数据的整队列任务，不提高原每请求或全局预算。

本地推荐、搜索、反馈、归档和维护每天最低0模型token。只有显式点击有模型开销。冻结点击时有效Useful/主动种子队列，串行每批最多3篇、完整40节点/120边Map与最多3条当前提议；每批经同一网关8000/1000预留，使用临时p/c/d别名，标题80/摘要180字。没有笔记、画像、全文、私人ID、其他项目或反馈文本外发。

每日10次现在指完整判断任务，沿用旧计数不清零；每个HTTP请求对应一个完整任务，跨进程claim覆盖全部批次。每批不同论文，各自一次，无重试、后台自动继续或模型替换。批间按本批公开元数据词汇相关度取最多3条有效提议，新近提议用于同分排序；词汇比较仅决定有界上下文，不代替学习价值或自动合并。模型可将后来论文并入先前方向。理论N篇ceil(N/3)次请求，20篇7次最坏63000token/$0.0252：超过55000日token上限，准入可能中途停止，不保证10次或所有论文获准。已reconciled实际usage用于后续网关准入，计费未知保留reservation并停止。

开始前校验完整请求、冻结图和所有本次证据/拒绝策略；新加入兴趣不追逐、不使本次过期。图、已选证据或本批可见提议的证据撤销/元数据变更冲突停止；可见提议证据有独立快照核对，不能重新激活过期意见。每批事务只存当前有效意见，前批成功不回滚；崩溃释放锁，重启后已判断记录仍在，下次只处理剩余。未发送/明确4xx且此前无已收费或未知请求才退整次任务；之后拒绝不退第一次。

响应明确requested/processed/complete/pending/model_calls；缺引用、重复/非法引用、坏JSON、输出截断、容量满等保留未完成论文，停止后续支出，不把遗漏论文推断为不确定。UI区分快照全部完成、运行期新增论文和中途停止。AI判断为已覆盖/不确定的论文有明确意见，可离开待判断；新方向需要用户预览确认才入Map。

验证计划：失败回归20篇、多个方向、第一次/后续拒绝、未知usage、partial/length、新兴趣与撤销竞争、整任务锁、重启与计数；Node按钮/提示/跨卡锁；独立审查、全量、fresh backend/Tauri/sign/new-package。真实多批模型质量不以fixtures冒充，整体19门槛和两项预算实测false保留。

Independent review also reproduced the old process-only ledger admission race:45000 base + two9000 reservations=63000. Canonical ledger kernel serialization now spans admit/reserve, read and reconcile append; same-thread nesting is reentrant, fork resets state, network stays outside. Synthetic race now permits one request/54000. Prices/caps/provider/default-off remain unchanged; original broad runtime/tokenizer flags remain false.

Complete describes paper judgments only:unknown billing still warns and retains reservation. Today prompt generations protect renewed same-card interest. Job charged on starting local day; terminal quota reads completion day. Synchronous HTTP runs the whole job;busy shows all N and terminal counts. No automatic background model continuation. Completed batches persist; later click after failure/restart visits only pending papers. Actual served UI used20synthetic papers and mocked replies,not real model quality.
