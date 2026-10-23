# 论文来源：要不要密钥、去哪拿、能得到什么

这是将来写给用户的“数据源”文档的骨架。事实只来自代码里的 `SourceInfo` 常量（`app/source_adapters.py`、`app/baidu_scholar.py`）和 `harness/sources.json` 里登记的外部事实；`tests/test_source_adapters.py` 会检查每个已注册来源在本文件里都有一节，且“要不要密钥”与 `SourceInfo.key` 一致。新增来源时先写 `SourceInfo`，再补一节；不要只改这里。

设置页“数据源”里每个来源一行：开关、密钥输入、一个状态词、测试、清除、获取。密钥只存在数据目录里该来源自己的 0600 文件，不进 `settings.json`，不出现在网址、缓存、日志和错误信息里，也只会作为请求头发给该来源自己的 https 主机。

接入状态（2026-10-23，单元 A）：百度学术的适配器、密钥、设置页和测试按钮已接入，**应用不会自动向百度发请求**；每日推荐、创建项目/种子检索和 PDF 路线分别由后续单元 B、C 接入，下面写的是整个功能完成后的行为。

## `arxiv` arXiv

- 密钥：无需密钥。
- 怎么用：随“arXiv”开关一起，经 OpenAlex 的索引检索（与下一节共用额度）。
- 会发送什么：英文检索词与日期范围（公开元数据查询）；不含画像、笔记、论文库和私有 ID。
- 怎么拿 PDF：arXiv 论文直接下载 arXiv 的 PDF（两次请求之间等待 arXiv 要求的间隔）。
- 外部事实：`harness/sources.json` 的 `ARXIV`、`ARXIV-PDF`。

## `openalex` 期刊与会议论文（OpenAlex）

- 密钥：密钥可选。不填也能用；填一个免费密钥把每日额度提高约 10 倍。
- 去哪拿：<https://help.openalex.org/api-reference/authentication>（注册账号后在 API 设置里复制）。
- 环境变量：`OPENALEX_API_KEY`（优先于密钥文件）；密钥文件 `openalex.key`。
- 密钥带来什么：免费密钥把每天 1000 点（约 0.1 美元）提高到 10000 点（约 1 美元）；邮箱参数已被 OpenAlex 忽略，应用不发用户邮箱。
- 会发送什么：检索词、DOI 与标题（公开元数据查询）；不含画像、笔记、论文库和私有 ID。
- 怎么拿 PDF：OpenAlex 报告的开放获取 PDF 链接（只取 https）；没有时给出原文页面链接。
- 外部事实：`harness/sources.json` 的 `OPENALEX`、`OPENALEX-AUTH`、`OPENALEX-OA`。

## `baidu_scholar` 百度学术（百度千帆 API）

- 密钥：必须有密钥（你自己的百度千帆 API Key）。默认关闭；第一次打开时有一次确认。
- 去哪拿：<https://console.bce.baidu.com/qianfan/ais/console/apiKey>（地址未核实，以百度智能云千帆平台为准）。
- 环境变量：`BAIDU_SCHOLAR_API_KEY`（优先于密钥文件）；密钥文件 `baidu_scholar.key`。密钥格式未核实，应用接受字母、数字和 `. _ ~ + / = : -`。
- 密钥带来什么：中文论文的检索（题名、原文摘要、DOI、关键词、年份、期刊、百度学术页面）。没有作者、引用数、PDF 链接和具体日期，也没有按日期排序。
- 额度：百度免费每天约 50 次，超出需向百度提工单（未验证）；应用本地每天最多 40 次（北京时间 0 点换日，未验证），用完前不会发出新请求；24 小时内相同检索直接用本地缓存，不占额度。是否超额拒绝而不是计费，需要在千帆控制台确认（待办）。
- 会发送什么：含中文的项目关键词（每个项目每次刷新最多 3 个）、创建项目时勾选中文后的检索词、种子论文的中文标题检索，以及设置页“测试”按钮的一个固定词；用你自己的密钥发给百度。不发画像、笔记、论文库和私有 ID。百度返回的 DOI 会交给 OpenAlex 查开放获取 PDF 和语言。
- 不存什么：百度的 AI 摘要（`aiAbstract`）从不请求、从不保存。
- 怎么拿 PDF：百度学术没有 PDF。有 DOI 时去 OpenAlex 找开放获取 PDF；找不到时在阅读器里给出百度学术页面、原文页面和出版方页面三个入口，由你在浏览器里登录后下载，再把 PDF 拖进阅读器附上。
- 外部事实：`harness/sources.json` 的 `CH-BAIDU-SCHOLAR`（含未核实项）。
