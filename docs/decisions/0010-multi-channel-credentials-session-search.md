# ADR 0010：多学科论文渠道、凭据保险箱与登录渠道后台检索

## 状态

已决定（owner，2026-10-01），分 CHAN-01…CHAN-11 逐步实施；本 ADR 落地时尚无任何渠道代码或实测。

## 背景

此前元数据入口只有 OpenAlex，而且被写死为只查 arXiv 来源、检索词写死为 "world model"，PDF 只认 `arxiv.org/pdf/<id>`。owner 要求让理工科和文科（含中文）的其他人也能用：接入主流渠道；需要登录的站点登录一次后保存会话继续使用；每条链路都要测试。调研同时发现几个阻断问题：中文标题经 `normalize_title` 全部变成空串，没有 DOI 的中文论文会被去重成一篇；`ranking.tokenize` 切不出中文词；`/api/refresh` 不使用项目关键词；Rust 外壳只读 Python stdout 的第一行。

## 决策

**1. 渠道分四级。** 每个渠道在 `harness/sources.json` 中有条目和复查日期。
- A 级，公开 API：arXiv、OpenAlex（自 2026-02-13 起需要用户自己的 key）、Semantic Scholar、Crossref、PubMed、Europe PMC、bioRxiv/medRxiv、DBLP、OpenReview、CORE、DOAJ、HAL、Zenodo、OSF、ERIC；Unpaywall 只用来找 PDF。
- B 级，用户自己的 API key（各家条款要求一人一 key）：WoS Starter、IEEE Xplore、Springer Nature、Elsevier Scopus。万方开放 API 和 PhilPapers 条款不明，暂缓。
- C 级，登录会话：知网、万方、维普、国家哲社文献中心（NCPSSD）、CSSCI。WoS、Scopus 的网页版只做登录、导入当前页和按需下载 PDF，后台检索改走它们的 B 级 API。
- D 级，只给外链：Google Scholar、百度学术、SSRN、ACM DL、JSTOR、RePEc、ChemRxiv（直连）。它们的条款禁止自动化，或者没有可用接口。

**2. 按项目选渠道，凭据全局共享。** 建项目时选择学科预设（cs_ai、biomed、physics_chem、econ_mgmt、humanities_social_cn、education、custom），之后可以逐个开关渠道。已有项目迁移为 `cs_ai`，默认启用 arxiv、openalex、crossref。检索词按文字种类分发：中文渠道只收到含中文的关键词。每个渠道实际发出的检索词都会在结果里列出。

**3. 凭据保险箱。** API key 和登录会话存在 macOS 钥匙串中：service 为 `com.paperdighelper.desktop`，account 为 `<channel>:<field>`。写入时通过 `security -i` 从 stdin 传入，密钥不会出现在进程参数里。测试环境和非 macOS 环境使用 0600 权限的文件。任何 API 响应、日志、导出、备份、缓存和 fixture 都不包含密钥或 cookie，接口只返回“已配置 / 过期 / 最近验证时间”。
- 威胁模型如实说明：钥匙串条目信任 `/usr/bin/security`，同一用户下运行的其他进程可以不经提示读取。保险箱防的是明文文件、Git/Time Machine 泄漏和误导出，防不住以当前用户身份运行的恶意程序。
- 只使用用户本人的凭据和会话。不共享会话、不导出会话，也不使用他人的账号（延续 R-PDF）。

**4. 登录桥接。** 复用 Tauri 外壳与 Python 之间已有的两根管道，不新增网络端口：Python 向 stdout 写 `PDH_SHELL {json}`，Rust 向子进程 stdin 按行写 JSON；stdin 读到 EOF 仍表示退出。
- 登录窗口使用独立的 `data_store_identifier`，与主窗口隔离；所有登录窗口共用这一个 store，因此学校 CARSI 单点登录可以跨站复用。
- 登录窗口禁止访问 loopback 和私网地址。
- 不新增任何 Tauri command 或 capability。
- 在浏览器或开发模式下没有外壳，改为提供“粘贴 Cookie 请求头”。

**5. 登录渠道后台自动检索（owner 明确选择，风险由 owner 承担）。** 这一功能每个项目单独开启，开启前必须确认风险提示（`acknowledged_risk`）。防护措施：
- 只在 app 运行期间、常规刷新之后执行，每个项目每个渠道每天最多一次；
- 全进程同一时间只跑一个会话渠道，请求串行，间隔 8–15 秒随机；
- 默认每渠道每天 10 次检索、30 次请求（CSSCI 为 5/15），代码中硬上限为 30/100。**这些上限是临时值，需要 owner 批准，agent 不能自行批准**；
- 每个响应都检测验证码和登录墙，命中一次就中止整轮，并停用该渠道，直到重新登录并验证通过；
- 每轮结束后把会话写回保险箱。

**6. PDF 解析链。** 依次尝试：本地文件 → arXiv → 记录自带的开放获取链接 → Unpaywall（按 DOI）→ 登录渠道（仅在用户点击时）→ 返回落地页链接。只允许 https；每次重定向后都拒绝 loopback 和私网地址；文件上限 100MB；文件头必须是 `%PDF`；原子写入。不绕过付费墙。

**7. 中文支持。** 分词对中文连续片段生成字二元组，ASCII 部分规则保持不变。`normalize_title` 保留中文字符。跨渠道去重顺序为：已知标识 → 规范化 DOI → (title_norm, year)。

**8. Zotero translators_CN** 只作为端点和选择器的参考阅读，不打包、不复制代码（许可可能是 AGPL）。

## 风险

- 后台会话检索可能违反知网等站点的服务条款，导致个人账号乃至学校 IP 段被封。防护措施只能降低概率，不能消除风险。
- 未公开的接口会变化，失败必须在 UI 上可见（“页面结构变化”），并需要持续维护。
- 隐私边界变了：项目关键词会发送给每个已启用的渠道；联系邮箱会发送给 Crossref、OpenAlex、Unpaywall 和 PubMed 的 polite pool。私有种子和画像 ID 仍然不外发。
- WKWebView 通常在退出时丢弃会话 cookie，跨重启依靠的是 Python 侧保存的 cookie jar，有效期取决于站点，过期后需要重新登录。

## 不采用

- 代用户抓取 Google Scholar 等 D 级站点：条款禁止自动化。
- 使用本地端口作为登录桥接：任何本地进程以及登录页里的网页都能访问它。
- 打包 translators_CN：许可不兼容，只能参考。
