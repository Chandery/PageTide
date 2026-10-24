# ADR 0044：产品改名 PageTide，新图标与字标

2026-10-24。owner 原话：

> “logo 和新名字做好了，改掉。app 的左上角不用放 logo 了，就放名字的设计稿。dock 再放 logo。仓库名字一会再说，后面伴随着 readme 一起改。”
> “没有老用户，别担心，还没发布。”
> “不要原来的 PaperDigHelper 这个名字了，全部都改掉。”

## 决定

1. **名字**：产品叫 **PageTide**。尚未发布过，没有老用户，所以内部名一起改，不留兼容层：
   - 打包：`productName` 与 Cargo 包名/可执行名 `pagetide`、bundle identifier `com.pagetide.desktop`、后端可执行 `pagetide-server`（`build_desktop.py`、`tauri.conf.json` resources、`main.rs`、CI、冒烟脚本）、窗口标题、安装包/zip 名。
   - 数据：macOS `~/Library/Application Support/PageTide`，Windows `%LOCALAPPDATA%\PageTideData`（仍刻意不与 NSIS 安装目录 `%LOCALAPPDATA%\PageTide` 同名），Linux `~/.local/share/PageTide`；SQLite 文件 `pagetide.sqlite`；本地快照/组织导出的格式标识 `pagetide.local-snapshot`、`pagetide-organization-v1`。
   - 环境变量：`PAPERDIGHELPER_*` 与 `PDH_*` 全部改为 `PAGETIDE_*`（如 `PAGETIDE_DATA`、`PAGETIDE_APP_VERSION`、`PAGETIDE_READY` 握手行）。
   - 界面与消息：所有页面 `<title>`、欢迎卡、`en-US.json` 键与值、导出文件名、后端消息、User-Agent、`robots.txt` 代理名。
   - **不做数据目录搬迁代码**：代码里不留旧名。owner 本机原有数据由 owner 手动搬到新目录。
2. **发布资产名**：Windows `PageTide_<版本>_x64-setup.exe`（Tauri NSIS 按 `productName` 命名，工作流不重命名）；macOS `PageTide-macos-arm64.zip` 与各自的 `.sha256`。`app/updater.py` 的 `MACOS_ASSET`、`installer_name`、`SAFE_ASSET`、更新检查 User-Agent `PageTide/<版本>` 同步。
3. **macOS 更新替换**：不变——把当前运行的 `.app`（不论叫什么）移到备份，把校验过的新包落在**同一路径**，失败则回滚；新包是 `PageTide.app`，正常安装的当前包也叫它。临时/备份名改为 `.PageTide-update-new.<pid>` / `.PageTide-update-old.<pid>`。没有为“旧名老包”做改名逻辑（没有老用户）。
4. **左上角只放字标**：`index.html` 头部不再放图标，只放字标图片（高 24px × 屏幕缩放，`alt="PageTide"`）。字标从 `PageTide-wordmark.png` 按可见边界裁切、缩到 96px 高（4x 余量），放 `app/static/wordmark.png`；深色主题用 `wordmark-dark.png`（深蓝 Page 映射为 `#ecf1fa`，亮蓝 Tide 提亮为 `#3888ff`，两色之间的抗锯齿像素按位置插值），由 `html[data-mode="dark"] .wordmark { content:url(...) }` 切换。项目切换器的占位页同样改用字标。
5. **Dock 与文件图标**：由 `docs/design/brand/pagetide/PageTide-icon.png`（owner 选定）经 `docs/design/brand/pagetide/build_icons.py` 生成 `src-tauri/icons/*`（PNG、icns、ico）。macOS/Tauri PNG 与 icns 按 Apple 图标网格把图形缩到画布的 82% 并居中（原图几乎贴边，直接用会在 Dock 里偏大）；ico 与网页 `favicon.png` 用 94%。icns 的 1x 16/32 槽仍写 `ic04/ic05` ARGB（旧缺陷：PNG 放在 `icp4/icp5` 下会在非 Retina 屏变成噪点）。旧海狮设计稿 `docs/design/logo/` 保留作历史，不再被构建使用。`favicon.svg`、`brand-mark.svg` 删除，页面改用 `favicon.png`。
6. **仓库地址例外**：GitHub 仓库仍叫 `Chandery/PaperDigHelper`，owner 说稍后随 README 一起改。代码里只有 `app/updater.py` 的 `REPO` 一处（API 地址、下载前缀、`html_url` 校验都由它派生；`release.yml` 用 `github.repository`）。仓库改名后要改：`app/updater.py` 的 `REPO`，`docs/RELEASE.md` 开头那句。`tests/test_brand_name.py` 的白名单只有这一行。

## 缩写前缀也改（owner：“全部都改掉”）

`pdh-*` CSS 类与 data 属性、`pdh-mode` / `pdh-tour` / `pdh-current-project` 等 localStorage 键、`window.PDH*`（`PDHTour`、`PDHDialogs` 等）、`pdh_session` Cookie、`X-PDH-Demo` 请求头、演示项目 id `pdh-demo`、临时目录前缀，机械改为 `pt-` / `PT` / `pt_`（`X-PT-Demo`、`pt-demo`）。按词边界替换，`app/static/vendor/`（第三方代码）不动；没有已发布用户，本地偏好（主题等）因键名变化重置可以接受。`tests/test_brand_name.py` 同时禁止旧名与 `pdh` 前缀（只豁免 vendor）。

## 有意保留

- 历史记录不改写：`changes/*.json`、`docs/evidence/*`、已有 ADR 正文、HANDOFF 过去条目，以及 `docs/design/logo/`、`docs/archive/`。仓库目录 `/Users/chandery/PaperDigHelper` 的绝对路径（仓库改名前不变）。

## 没有验证

没有构建：`cargo tauri build`、DMG/zip、NSIS 安装包、Dock 与 Finder 里的真实图标观感、Windows 上的图标都没看过；Cargo 包名改为 `pagetide` 后只做了 `cargo check --offline`。`tauri.conf.json` 设了 `mainBinaryName: "PageTide"`（进程名/可执行名为 PageTide；Cargo 包名仍是 `pagetide`）。`main.rs`、CI、脚本里没有依赖可执行文件名的地方，但打包后的实际文件名未构建验证。
