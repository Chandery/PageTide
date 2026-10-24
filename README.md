# PageTide

**本地优先的论文推荐与可解释用户画像。** PageTide 每天从论文来源里挑出值得看的几篇，按你明确的反馈（收藏、不感兴趣、太难）改进下一批推荐，并把画像做成你能检查、修改、撤销的数据。论文库（列表、图谱、分类整理）、阅读器里的划词翻译与追问、AI 速览和周报建立在这之上。

数据都存在你的电脑上。没有托管后端、云同步或遥测；只有你配置并启用的 AI 和论文来源会联网。

## 下载

在 [Releases](https://github.com/Chandery/PageTide/releases) 下载：

- macOS（Apple Silicon）：`PageTide-macos-arm64.zip`
- Windows x64：`PageTide_<版本>_x64-setup.exe`

两个平台都是**未签名**构建。macOS 第一次打开：把应用拖进“应用程序”，右键 → 打开 → 再点“打开”。Windows 的 SmartScreen 提示里选“更多信息 → 仍要运行”。细节见 [RELEASE](docs/RELEASE.md)。

应用会在启动时查一次新版本（可在设置里关闭），有新版时在主页提示，点“更新”即可下载、校验并安装。

## 第一次使用

1. 打开后先选界面语言和外观。
2. 新手指引会在一个只读的演示项目里走一遍完整流程：项目入口、设置、生成今日推荐与 AI 速览、收藏、划词提问、论文库与导入、图谱、画像、周报。演示离线运行、不花 token，也不写入你的数据。
3. 指引结束后创建你自己的项目。

需要的配置（都在设置里）：

| 用途 | 需要什么 |
|---|---|
| AI 速览、追问、翻译 | DeepSeek API 密钥（设置里有“获取”链接） |
| arXiv | 不需要密钥 |
| 期刊与会议论文（OpenAlex） | 密钥可选 |
| 中文论文（百度搜索） | 千帆密钥 |

不配 AI 密钥也能用：推荐、画像、论文库和图谱都在本地完成，不花 token。

数据位置：macOS `~/Library/Application Support/PageTide`，Windows `%LOCALAPPDATA%\PageTideData`。

## 原则

- 推荐、画像、论文库和数据库的默认路径离线可用、零模型 token；AI 只是经过一个有预算的网关的可选增强。
- 没选、没空、看不懂都不等于不喜欢；画像只从明确的操作里学习。
- 论文原文、来源和文件版本都保留；AI 生成的文字不算你写的笔记。

## 开发

需要 Python 3.9+（应用代码只用标准库）和 Node LTS（前端测试）。

```sh
python3 -m app.server            # 本地网页界面 http://127.0.0.1:8765，数据在 .local/app（可用 PAGETIDE_DATA 改）
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests
node --test tests/*.cjs
```

桌面构建（macOS，需要 `.local/desktop-build-env` 构建环境与 Rust / tauri-cli）：

```sh
.local/desktop-build-env/bin/python scripts/build_desktop.py
cargo tauri build --bundles app      # 输出 src-tauri/target/release/bundle/macos/PageTide.app
```

Windows 安装包由 GitHub Actions 构建，发布流程见 [RELEASE](docs/RELEASE.md)。

## 文档

- [AGENTS](AGENTS.md)：给编码 agent 的入口与边界。
- [PRODUCT](docs/PRODUCT.md)、[ARCHITECTURE](docs/ARCHITECTURE.md)：产品范围、架构与隐私。
- [BUDGET](docs/BUDGET.md)：零 token 核心与 AI 层预算。
- [HARNESS](docs/HARNESS.md)、[HANDOFF](docs/HANDOFF.md)：变更记录、审查与交接。
- [decisions/](docs/decisions/)：架构决策记录。
