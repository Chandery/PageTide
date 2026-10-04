# ADR 0011：PDF 获取与开放获取来源策略

## 状态

已实现（2026-10-04），待独立审查。真实下载（arXiv、非 arXiv 开放获取、付费论文各一篇）尚未实测，E-PDF-ARCHIVE 仍是 `not_run`。

## 背景

`App.download_pdf` 只会抓 `https://arxiv.org/pdf/<arxiv_id>`：没有开放获取回退、没有速率间隔、大小上限、重试或哈希，也没有测试；失败原因被阅读器吞掉，用户看不到为什么没有 PDF。OpenAlex 的 `open_access` / `best_oa_location` / `locations[]` 被 `slim()` 丢弃。

## 决策

1. **来源与顺序。** 先 arXiv PDF（有 arXiv 编号时），再 OpenAlex 报告的 https PDF 链接。OpenAlex 链接只是候选，不代表允许自动下载。旧论文没有保存开放获取数据时，下载前向 OpenAlex 按编号补查一次（公开元数据）。
2. **只在用户要读时下载**，一次一篇；不批量、不后台预取。
3. **守规矩。** 每个主机先读 robots.txt（4xx 视为没有限制；5xx 或不可达按不可用处理，不当作允许）；被禁止就报告 `robots_disallowed`，不绕过。请求间隔取我们的下限（arXiv 3 秒，其他 1 秒）与 robots 的 Crawl-delay 中较大者（上限 60 秒）；arXiv 当前 Crawl-delay 为 15 秒。403/401 报告 `paywalled_or_blocked` 且不重试，不使用凭证；429/5xx 只重试一次并遵守 Retry-After（等待上限 10 秒）。
4. **安全限制。** 只接受 https（含重定向）；流式读取并限制 60 MB；开头必须有 `%PDF-`；先写临时文件再原子改名，失败不留半截文件。
5. **归档语义。** 文件名为 `<规范ID>-<sha256 前 12 位>.pdf`。相同内容幂等复用；内容变化时旧文件保留（保留原件），`pdfs` 表指向最新。`pdfs` 新增 `sha256`、`bytes`、`source_kind`（`arxiv|openalex_oa|user_import`）和 `license`（许可线索）；`papers.oa_json` 保存最近一次开放获取信息。迁移 005，迁移前自动备份沿用 `.pre-vN.bak`。
6. **失败可见。** 返回 `{ok:false, reason, attempts[]}`，原因为 `no_oa_source`、`not_found`、`paywalled_or_blocked`、`robots_disallowed`、`rate_limited`、`not_pdf`、`too_large`、`network_error`、`invalid_url`；阅读器显示对应说明。下载失败不影响推荐和反馈。
7. **联系邮箱。** 设置页新增 `contactEmail`，只作为 OpenAlex 的 `mailto` 发送，不进入 PDF 来源站点的请求或 User-Agent。未设置时沿用占位地址。OpenAlex 缓存键按占位地址计算，设置真实邮箱不会让现有缓存失效。

8. **OpenAlex API 密钥（可选）。** 免费密钥可提高 OpenAlex 每日额度。单独存放在数据目录的 `openalex.key`（0600），环境变量 `OPENALEX_API_KEY` 优先；不进 `settings.json`、不回显。密钥只以 `Authorization: Bearer` 请求头发给 `https://api.openalex.org`（用 unredirected header，重定向不会带到别处），不放进 URL，因此不会进入缓存键、错误信息或日志；PDF 来源站点的请求永远不带它。`tools/data_probe.py` 同样只从环境变量读取。

## 隐私与预算

- 不新增模型操作，零模型 token，不改 `harness/budget.json`。
- 外发请求：OpenAlex 按已存在论文的编号补查（公开元数据）；PDF 来源站点的 robots.txt 与 PDF 本身。私人种子、画像、笔记、全文不外发。
- 不接 Unpaywall：它需要把 DOI 和真实邮箱发给第三方，留作第二阶段，须先量出覆盖率并经 owner 批准。

## 已知限制

- 没有为已有论文手动附加 PDF 的入口（目前只有创建项目时拖入）；付费论文只能显示原因。
- 全文提取仍在浏览器 pdf.js 中、打开阅读器后才发生。
- arXiv 的批量/自动访问帮助页没有读到（请求超时），除 robots.txt 外的访问政策未核实。
- 开放获取链接在真实记录上的命中率未测量；`tools/data_probe.py` 现在会输出该数字（候选池偏向 arXiv，不能代表非 arXiv 论文）。
- 实测（2026-10-04）：Nature 的 DreamerV3 论文在 OpenAlex 中是 `is_oa=true`、`cc-by`，但只有 DOI 落地页、没有 `pdf_url`，应用因此报 `no_oa_source`，阅读器文案“没有找到可合法下载的来源”对开放获取论文有误导。后续可显示落地页链接，或在第二阶段评估 Unpaywall。
