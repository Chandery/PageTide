# ADR 0041：检查更新（GitHub Release + 应用内下载安装包）

2026-10-24。owner 原话：

> “检测更新功能，要在 app 里提醒用户可以更新了，在 app 里可以点击更新键。”

owner 在备选方案里选了“检查 GitHub 最新 Release + 下载对应平台安装包并打开”，不用 `tauri-plugin-updater`（它要签名密钥与更新清单，当前两个平台都未签名）。**这是 owner 的请求记录；变更记录里的 `owner_approved` 仍是 false，不由 agent 自填。** 这是一个新的对外网络请求，按 AGENTS.md 边界 1 登记如下；其余边界不变。

## 决定

1. **版本来源**：Rust 外壳启动后端时设环境变量 `PDH_APP_VERSION`（`app.package_info().version`，即 `tauri.conf.json` 的 version）。源码运行没有它，视为开发版：`GET /api/update` 返回 `reason_code: dev_build`，不发请求。
2. **请求范围**：只有 `https://api.github.com/repos/Chandery/PaperDigHelper/releases/latest`（GET，无请求体、无凭据、无 Cookie，User-Agent 仅 `PaperDigHelper/<版本>`）与所选资产的下载（`github.com` 及 GitHub 重定向到的 `*.githubusercontent.com`，重定向到其他主机即拒绝）。资产链接必须以 `https://github.com/Chandery/PaperDigHelper/releases/download/` 开头。不含论文、画像、笔记、路径、设备标识、用量。
3. **频率与静默**：结果缓存在 `<数据目录>/update-check.json`，6 小时内不重复请求；失败（断网、超时、坏 JSON、草稿/预发布）静默为“未知”，15 分钟内不重试，沿用上次已知的 release。设置项 `autoCheckUpdates`（默认 true）关闭后不再自动请求；设置页“检查更新”按钮是显式操作，忽略缓存与开关，并清掉“已关闭提示”的记录（让主页的提示条重新出现）。开关关闭时主页仍会显示显式检查已存下的结果，但不发请求。
4. **什么算“有更新”**：tag 严格为 `vX.Y.Z`，数值比较大于当前版本，**并且**该 release 里有本平台的安装包与同名 `.sha256`：Windows 文件名必须正好是 `PaperDigHelper_<tag 版本>_x64-setup.exe`，macOS（仅 arm64）`PaperDigHelper-macos-arm64.zip`；每个资产的 `browser_download_url` 必须严格等于 `https://github.com/Chandery/PaperDigHelper/releases/download/<tag>/<资产名>`。缺资产时不提示（例如 macOS 包还没上传，或 Intel Mac），设置页的检查按钮会说“新版本暂无适用于本机的安装包”，而不是“已是最新”。因此发布流程必须先传齐资产再把草稿发布（[RELEASE](../RELEASE.md)），仓库需公开。
5. **提示**：主页顶部一条安静的细条“有新版本 vX.Y.Z · [更新] ×”；关闭后同一版本不再提示，记在后端（`update-check.json` 的 `dismissed`；WebView 的来源每次启动端口随机，localStorage 会丢）。
6. **下载与校验**：`POST /api/update/download` 起后台线程，下载到 `<数据目录>/updates/`（每次先清空该目录，只留当前这一个），文件名只接受上述两种固定模式，路径解析后必须在 `updates/` 内；大小上限 600 MB；`.sha256` 的首个字段必须是 64 位十六进制，与文件 SHA-256 不符则删除并报错。页面轮询进度。
7. **交接（退出之后才发生）**：`POST /api/update/apply` 再校验一次文件哈希，只对 `updates/` 内的文件工作，在后端内存里登记“待执行”并返回模式；页面随后调用现有的 `PDHPrepareQuit`（草稿保护、`complete_quit`、实例锁与后端释放都复用）。外壳退出时关闭后端的 stdin，后端读到 EOF 后**先**启动待执行项，再停 worker 和服务（外壳 2 秒后会杀后端；辅助脚本不依赖后端，所以提前启动安全）。
   - **退出被取消**：`PDHPrepareQuit` 没有返回值，所以页面在请求退出 1.5 秒后若自己还活着，就视为取消（草稿保存失败、确认对话框还开着等），调用 `POST /api/update/cancel` 清掉待执行，并恢复“更新”与“×”按钮。待执行另有 10 分钟失效。代价：用户在退出确认对话框里想得超过 1.5 秒再确认时，应用会照常退出而不更新，下次再点“更新”即可（安全优先于便利）。
   - **Windows**：后端在上述时机直接启动已校验的 `PaperDigHelper_X.Y.Z_x64-setup.exe`（`DETACHED_PROCESS`、`close_fds`），不经 PowerShell；NSIS 模板自带“应用正在运行”检查。当前用户安装，可能出现 SmartScreen。
   - **macOS**：先用 `ditto -x -k` 把 zip 解到 `updates/extracted/`，要求恰好一个含 `Contents/MacOS` 的 `.app`，其 `Info.plist` 的 `CFBundleShortVersionString` 必须等于 release 版本（否则拒绝并报错），且当前 `.app` 及其父目录可写；然后 `/bin/sh apply-update.sh`：等外壳进程退出（最多 60 秒，否则什么都不动）→ `ditto` 复制新 app 到旧 app 同目录的临时名 → 旧 app 移到备份名 → 新 app 改名到位（任一步失败则回滚）→ `xattr -dr com.apple.quarantine` → 删备份 → `open` 新 app（失败时 `open` 的是旧 app）。脚本把结果写到 `updates/result`（`ok`、`failed`、`rollback-failed <备份路径>`）。**下次启动**（无论新旧版本）`GET /api/update` 读一次并删除它：失败时主页提示“更新未完成”，并在访达里显示已下载的 zip；回滚也失败时显示旧版本的备份。这样 App Management/TCC 拦截、root 所有的 app 等导致的失败不会静默，也不会反复尝试。**不可写或解压失败**时不退出应用，直接在访达里显示已校验的 zip，提示手动替换。
   - 启动时若当前版本不低于已下载的版本，清空 `updates/`（保留 `apply-update.log` 与 `result`）。
   - 选择在 Python 后端而不是 Rust 做：Rust 侧只多一行环境变量，不新增 Tauri command / crate / 权限，“只启动 `updates/` 内校验过的文件”由后端一处强制。
8. **没有选的**：`tauri-plugin-updater`（要签名密钥、更新清单与 `latest.json`）；静默自动安装（owner 要的是“提醒 + 点击更新”）；检查预发布版。

## 信任边界

`.sha256` 来自同一个 release，**只保证下载完整、与发布者上传的文件一致，不保证发布者真实**：两个平台都未签名，谁能改 release 资产就能同时改文件和校验和。这是已接受的风险；要改变它需要代码签名（macOS 开发者证书/公证，Windows 证书），不在本次范围。

## 没有验证

GitHub API 在开发沙箱里被拒绝访问，**从未对真实 GitHub 发过请求**；下载、重定向白名单、`browser_download_url` 的真实形状按文档与假传输层测试。Windows 安装程序在后端读到 EOF 时直接启动、NSIS 的“应用正在运行”检查在此场景的表现、macOS 脚本在真实 `.app`（含 Gatekeeper/translocation：从 DMG 或下载目录直接运行的 app 目录不可写，会走手动回退）上的行为都没有真机运行；macOS 脚本的“等待-替换-回滚-结果文件”逻辑只用假 `.app` 目录（含用假 `mv` 触发的回滚与回滚失败分支）在 macOS 上单元测试过。未签名的应用被替换后首次打开的 Gatekeeper 提示未验证。
