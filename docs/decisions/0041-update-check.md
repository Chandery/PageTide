# ADR 0041：检查更新（GitHub Release + 应用内下载安装包）

2026-10-24。owner 原话：

> “检测更新功能，要在 app 里提醒用户可以更新了，在 app 里可以点击更新键。”

owner 在备选方案里选了“检查 GitHub 最新 Release + 下载对应平台安装包并打开”，不用 `tauri-plugin-updater`（它要签名密钥与更新清单，当前两个平台都未签名）。**这是 owner 的请求记录；变更记录里的 `owner_approved` 仍是 false，不由 agent 自填。** 这是一个新的对外网络请求，按 AGENTS.md 边界 1 登记如下；其余边界不变。

## 决定

1. **版本来源**：Rust 外壳启动后端时设环境变量 `PDH_APP_VERSION`（`app.package_info().version`，即 `tauri.conf.json` 的 version）。源码运行没有它，视为开发版：`GET /api/update` 返回 `reason_code: dev_build`，不发请求。
2. **请求范围**：只有 `https://api.github.com/repos/Chandery/PaperDigHelper/releases/latest`（GET，无请求体、无凭据、无 Cookie，User-Agent 仅 `PaperDigHelper/<版本>`）与所选资产的下载（`github.com` 及 GitHub 重定向到的 `*.githubusercontent.com`，重定向到其他主机即拒绝）。资产链接必须以 `https://github.com/Chandery/PaperDigHelper/releases/download/` 开头。不含论文、画像、笔记、路径、设备标识、用量。
3. **频率与静默**：结果缓存在 `<数据目录>/update-check.json`，6 小时内不重复请求；失败（断网、超时、坏 JSON、草稿/预发布）静默为“未知”，15 分钟内不重试，沿用上次已知的 release。设置项 `autoCheckUpdates`（默认 true）关闭后不再自动请求；设置页“检查更新”按钮是显式操作，忽略缓存与开关。
4. **什么算“有更新”**：tag 严格为 `vX.Y.Z`，数值比较大于当前版本，**并且**该 release 里有本平台的安装包与同名 `.sha256`：Windows `PaperDigHelper_X.Y.Z_x64-setup.exe`，macOS（仅 arm64）`PaperDigHelper-macos-arm64.zip`。缺资产时不提示（例如 macOS 包还没上传）。因此发布流程必须先传齐资产再把草稿发布（[RELEASE](../RELEASE.md)），仓库需公开。
5. **提示**：主页顶部一条安静的细条“有新版本 vX.Y.Z · [更新] ×”；关闭后同一版本不再提示，记在后端（`update-check.json` 的 `dismissed`；WebView 的来源每次启动端口随机，localStorage 会丢）。
6. **下载与校验**：`POST /api/update/download` 起后台线程，下载到 `<数据目录>/updates/`（每次先清空该目录，只留当前这一个），文件名只接受上述两种固定模式，路径解析后必须在 `updates/` 内；大小上限 600 MB；`.sha256` 的首个字段必须是 64 位十六进制，与文件 SHA-256 不符则删除并报错。页面轮询进度。
7. **交接（退出之后才发生）**：`POST /api/update/apply` 再校验一次文件哈希，只对 `updates/` 内的文件工作，登记“待执行”并返回模式；页面随后调用现有的 `PDHPrepareQuit`（草稿保护、`complete_quit`、实例锁与后端释放都复用）。后端在 HTTP 服务停止后（外壳退出时关闭其 stdin）才启动一个脱离的小脚本，所以退出被取消（有未保存草稿）时什么都不会发生；待执行 10 分钟后失效。
   - **Windows**：`powershell.exe -File apply-update.ps1 -ProcessId <外壳 pid> -Installer <setup.exe>`，脚本等外壳进程结束（最多 60 秒）再启动安装程序（NSIS 安装包，当前用户，可能出现 SmartScreen）。
   - **macOS**：先用 `ditto -x -k` 把 zip 解到 `updates/extracted/`，要求恰好一个含 `Contents/MacOS` 的 `.app`，且当前 `.app` 及其父目录可写；然后 `/bin/sh apply-update.sh`：等外壳进程退出（最多 60 秒，否则什么都不动）→ `ditto` 复制新 app 到旧 app 同目录的临时名 → 旧 app 移到备份名 → 新 app 改名到位（任一步失败则回滚）→ `xattr -dr com.apple.quarantine` → 删备份 → `open` 新 app。**不可写或解压失败**时不退出应用，只用 `/usr/bin/open -R` 在访达里显示已校验的 zip，提示手动替换。
   - 选择在 Python 后端而不是 Rust 做：Rust 侧只多一行环境变量，不新增 Tauri command / crate / 权限，“只启动 `updates/` 内校验过的文件”由后端一处强制。
8. **没有选的**：`tauri-plugin-updater`（要签名密钥、更新清单与 `latest.json`）；静默自动安装（owner 要的是“提醒 + 点击更新”）；检查预发布版。

## 没有验证

GitHub API 在开发沙箱里被拒绝访问，**从未对真实 GitHub 发过请求**；下载、重定向白名单、`browser_download_url` 的真实形状按文档与假传输层测试。Windows 的 PowerShell 辅助脚本、NSIS 安装程序在应用退出后的接管、macOS 脚本在真实 `.app`（含 Gatekeeper/translocation：从 DMG 或下载目录直接运行的 app 目录不可写，会走手动回退）上的行为都没有真机运行；脚本的“等待-替换-回滚”逻辑只用假 `.app` 目录在 macOS 上单元测试过。未签名的应用被替换后首次打开的 Gatekeeper 提示未验证。
