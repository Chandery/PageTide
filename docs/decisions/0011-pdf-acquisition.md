# ADR 0011：PDF 获取与开放获取来源策略

## 状态

已实现（2026-10-04），待独立审查。真实下载、离线打开、付费拒绝和手动附加已在 owner 机器上实测（自测，见 `docs/evidence/2026-10-04-pdf-acquisition-checks.txt`），E-PDF-ARCHIVE 为 `passed`；PDF-01 为 `review`。

## 背景

`App.download_pdf` 只会抓 `https://arxiv.org/pdf/<arxiv_id>`：没有开放获取回退、没有速率间隔、大小上限、重试或哈希，也没有测试；失败原因被阅读器吞掉，用户看不到为什么没有 PDF。OpenAlex 的 `open_access` / `best_oa_location` / `locations[]` 被 `slim()` 丢弃。

## 决策

1. **来源与顺序。** 先 arXiv PDF（有 arXiv 编号时），再 OpenAlex 报告的 https PDF 链接。OpenAlex 链接只是候选，不代表允许自动下载。旧论文没有保存开放获取数据时，下载前向 OpenAlex 按编号补查一次（公开元数据）。
2. **只在用户要读时下载**，一次一篇；不批量、不后台预取。
3. **守规矩。** 每个主机先读 robots.txt（4xx 视为没有限制；429、5xx 或不可达按不可用处理，不当作允许）；被禁止就报告 `robots_disallowed`，不绕过。请求间隔取我们的下限（arXiv 3 秒，其他 1 秒）与 robots 的 Crawl-delay 中较大者（上限 60 秒）；arXiv 当前 Crawl-delay 为 15 秒。robots.txt 本身的读取不计入间隔（常见爬虫做法），所以第一次下载不会被它拖慢。403/401 报告 `paywalled_or_blocked` 且不重试，不使用凭证；429/5xx 只重试一次并遵守 Retry-After（等待上限 10 秒）。**抓取器是进程内共享的**（`shared_fetcher`，按数据目录一个）：桌面服务每个请求都会新建 `App`，如果每个 App 一个抓取器，间隔、Crawl-delay 和 robots 缓存都会在请求之间丢失；主机级锁保证并发请求也被隔开。
4. **安全限制。** 只接受 https 且主机必须是公网地址（字面量私有/回环地址和 localhost、.local 等本地名称被拒绝）；每一次重定向都同样检查，并且对新主机再做 robots 与间隔；流式读取并限制 60 MB；开头必须有 `%PDF-`；先写临时文件再原子改名，失败不留半截文件。
5. **归档语义。** 文件名为 `<规范ID>-<sha256 前 12 位>.pdf`。相同内容幂等复用；内容变化时旧文件保留（保留原件），`pdfs` 表指向最新。`pdfs` 新增 `sha256`、`bytes`、`source_kind`（`arxiv|openalex_oa|user_import`）和 `license`（许可线索）；`papers.oa_json` 保存最近一次开放获取信息；迁移 007 的追加式 `pdf_versions` 表记录每一份归档副本的来源，替换 PDF 时旧副本的来源不会丢。迁移 006/007（编号 5 留给 channels 分支，见下），迁移前自动备份沿用 `.pre-vN.bak`；迁移只忽略“列已存在”，数据库被锁或只读会让迁移失败而不是被记为已完成。每个迁移在事务里执行，中途失败会整体回滚（含建表），下次启动从干净状态重试。
6. **失败可见，并给出出路。** 返回 `{ok:false, reason, attempts[]}`，原因为 `no_oa_source`、`not_found`、`paywalled_or_blocked`、`robots_disallowed`、`rate_limited`、`not_pdf`、`too_large`、`network_error`、`invalid_url`；阅读器显示对应说明；论文是开放获取但 OpenAlex 只给了落地页时，原因为 `landing_page_only`，并显示“打开原文页面”链接。每次失败都提供“附加本地 PDF”：先走原有的 `/api/seeds/pdf` 上传（原样存入 `imports/`），再由 `POST /api/pdf/attach` 通过 `take_imported_pdf` 移入 `pdfs/` 并以 `source_kind=user_import` 记录；已有的下载文件不会被删除。下载失败不影响推荐和反馈。
7. **没有联系邮箱设置。** 最初计划让用户填联系邮箱作为 OpenAlex 的 `mailto`。官方弃用页写明礼貌访问通道（polite pool）在 2026 年 2 月被 API 密钥取代，“`mailto` 参数被忽略”；2026-10-04 实测同一请求在有/无 `mailto`、有/无密钥四种组合下额度完全一致（1000 vs 10000 credits/天）。因此不再收集或发送用户邮箱，设置项已移除；请求里只保留占位 `owner@example.invalid`，仅为让已有缓存的 URL 继续命中。
8. **OpenAlex API 密钥（可选）。** 免费密钥可提高 OpenAlex 每日额度。单独存放在数据目录的 `openalex.key`（0600），环境变量 `OPENALEX_API_KEY` 优先；不进 `settings.json`、不回显。密钥只以 `Authorization: Bearer` 请求头发给 `https://api.openalex.org`（用 unredirected header，重定向不会带到别处），不放进 URL，因此不会进入缓存键、错误信息或日志；PDF 来源站点的请求永远不带它。`tools/data_probe.py` 同样只从环境变量读取。

9. **同源检查。** 所有 POST/DELETE 路由都拒绝带有他站 `Origin` 的请求（此前只有两条路由检查）。

10. **迁移按编号记录，不按最大值。** 事故：`worktree-channels` 分支的迁移 005（channels）已在 owner 的真实数据库上运行并记为版本 5，而本分支原先的迁移也叫 005，被当成“已完成”而跳过，随后的迁移 006 引用不存在的 `sha256` 列，应用启动即崩溃（界面显示“项目加载失败”）。现在 `apply_migrations` 对每个编号单独判断是否已记录，本分支的迁移改为 006/007，编号 5 是一个永不运行、永不记录的保留位（`migrate_005_reserved_for_channels`），两个分支合并时用真正的 005 替换它，各自的数据库都不会漏掉对方的迁移。

## 隐私与预算

- 不新增模型操作，零模型 token，不改 `harness/budget.json`。
- 外发请求：OpenAlex 按已存在论文的编号补查（公开元数据）；PDF 来源站点的 robots.txt 与 PDF 本身。私人种子、画像、笔记、全文不外发。
- 不接 Unpaywall：它需要把 DOI 和真实邮箱发给第三方，留作第二阶段，须先量出覆盖率并经 owner 批准。

## 已知限制

- 附加本地 PDF 的上传是一次性的（`take_imported_pdf` 会移动文件），同一次上传不能再附加到另一篇论文；不支持断点续传：失败的下载不留半截文件，重试是受限的第二次请求；文件上限 60 MB，普通论文足够。
- 全文提取仍在浏览器 pdf.js 中、打开阅读器后才发生。
- arXiv 的批量/自动访问帮助页没有读到（请求超时），除 robots.txt 外的访问政策未核实。
- 开放获取链接在真实记录上的命中率未测量；`tools/data_probe.py` 现在会输出该数字（候选池偏向 arXiv，不能代表非 arXiv 论文）。
- 实测（2026-10-04）：Nature 的 DreamerV3 论文在 OpenAlex 中是 `is_oa=true`、`cc-by`，但只有 DOI 落地页、没有 `pdf_url`，应用因此报 `no_oa_source`，阅读器因此改为说明“开放获取但没有直链”并给出落地页链接。这类论文能否自动下载，留给第二阶段评估 Unpaywall（样本只有 1 个）。
