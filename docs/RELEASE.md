# 发布流程

产品名自 2026-10-24 起为 PageTide（[ADR 0044](decisions/0044-pagetide-brand.md)）；GitHub 仓库 2026-10-25 改名为 `Chandery/PageTide`，更新检查读取的仓库在 `app/updater.py` 的 `REPO`。

所有平台都是**未签名**构建，全部由 GitHub Actions 构建（[ADR 0040](decisions/0040-windows-release.md)）：Windows x64、macOS Apple 芯片（arm64，`macos-15`）和 macOS Intel（x64，`macos-15-intel`）。每个 macOS 架构在对应架构的机器上单独构建，没有通用包（PyInstaller 只能打出解释器自己的架构）。`macos-15-intel` 是 GitHub 最后一个 Intel macOS 镜像，约 2027 年 8 月下线，之后 Intel 版需要另想办法或停止提供。

## 发一个版本

1. 合并到 `main`，本地跑完 AGENTS.md 里的检查（预算、harness、单元测试、Node 测试）。
2. 改版本号（`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`），提交，打标签并推送（标签必须等于 `v` + `tauri.conf.json` 的 version，`publish` 作业会核对）：`git tag vX.Y.Z && git push origin vX.Y.Z`。
3. 标签推送触发 `release` 工作流：`test-windows`、`test-macos`（Python 与 Node 测试）和 `build-windows`（PyInstaller、冒烟、NSIS、校验和）、`build-macos`（arm64 与 x64 各一份：PyInstaller、冒烟、`.app`、架构与版本核对、zip、校验和）并行；全部通过后 `publish` 作业确认三个平台的文件都在，再把 `PageTide_*_x64-setup.exe`、`PageTide-macos-arm64.zip`、`PageTide-macos-x64.zip` 及各自的 `.sha256` 传到该标签的 release（release 不存在则建为**草稿**；已有同名文件会被覆盖）。也可在 Actions 页面手动运行（`workflow_dispatch`），此时只产出 artifact，不发布。
4. 检查草稿 release 里三个平台的文件，再手动发布。
5. 发布后更新网站：把 `site/release.json` 的 version 改成新版本，跑 `python3 site/build.py`，按实际安装包大小改 `site/i18n/*.json`、`site/template.html` 和 README 里的 MB 数，提交并推送（Vercel 随 `main` 部署）。发布前网站一直指向上一个已发布版本。

## 应用内“检查更新”依赖什么

已安装的应用（[ADR 0041](decisions/0041-update-check.md)）读取 GitHub 的 `releases/latest`，所以：

- **仓库需公开**，release 必须**从草稿发布**为正式版（草稿与预发布不会被 `latest` 返回，应用也会忽略）。
- tag 严格是 `vX.Y.Z`，且大于已安装版本；版本号以 `tauri.conf.json` 为准（外壳以环境变量传给后端）。
- 资产名必须正好是（Windows 文件名里的版本必须等于 tag，下载链接必须是 `releases/download/<tag>/<资产名>`）：Windows `PageTide_X.Y.Z_x64-setup.exe`（Tauri NSIS 的默认输出名，工作流不重命名）与 `PageTide_X.Y.Z_x64-setup.exe.sha256`；macOS Apple 芯片 `PageTide-macos-arm64.zip`、Intel `PageTide-macos-x64.zip`，以及各自的 `.sha256`（应用按 `platform.machine()` 选：`arm64` 取前者，`x86_64` 取后者；在 Apple 芯片上用 Rosetta 运行的 Intel 版也取 Intel 包）。`.sha256` 首字段为 64 位十六进制 SHA-256（`shasum -a 256` 与工作流的格式都满足）。缺任何一个，该平台就不提示更新。macOS 压缩包里的 `.app` 的 `CFBundleShortVersionString` 必须等于 tag 的版本号（`tauri.conf.json` 的 version），否则应用拒绝替换。
- 三个平台的资产都传齐后再发布草稿（`publish` 作业会先核对），否则先发布的平台用户会收到提示而其他平台暂时没有。
- 没有在真实 GitHub 上跑过这条链路（开发沙箱禁止访问），首次发布后请用旧版本的应用实测一次。

## macOS 本机构建（可选，仅用于本地测试）

发布用的 macOS 包由 CI 构建。本地想打一个 Apple 芯片的包自测时：

```sh
.local/desktop-build-env/bin/python scripts/build_desktop.py
cargo tauri build --bundles app
```

`build_desktop.py` 用 `PAGETIDE_BUILD_PYTHON` 指定的 Python；没设时在 macOS 上用 `.local/desktop-build-env`（Python 3.9.6），其他情况用当前解释器。CI 用 3.11。

## 用户首次打开（未签名）

- **macOS**：解压后拖进“应用程序”，右键应用 → 打开 → 再点“打开”；或终端执行 `xattr -dr com.apple.quarantine /Applications/PageTide.app`。
- **Windows**：运行安装包，SmartScreen 提示“已保护你的电脑”时点 **更多信息 → 仍要运行**。安装为当前用户（不需要管理员）。若系统没有 WebView2 运行时，安装器会联网下载它。
- 校验：`shasum -a 256 -c <文件>.sha256`（macOS），`Get-FileHash <文件> -Algorithm SHA256`（Windows）与 `.sha256` 内容比对。

## 数据位置

| 系统 | 正式版（CI 构建） | 开发版（本地 `cargo tauri dev` / `cargo tauri build`） |
| --- | --- | --- |
| macOS | `~/Library/Application Support/PageTide` | `~/Library/Application Support/PageTide-Dev` |
| Windows | `%LOCALAPPDATA%\PageTideData`（日志在其 `logs\backend.log`） | `%LOCALAPPDATA%\PageTideDevData` |

正式版由 CI 用 `PAGETIDE_RELEASE=1` 编译；没有这个变量编出来的都是开发版：外壳给后端设 `PAGETIDE_CHANNEL=dev`，后端改用开发目录，窗口标题是 “PageTide Dev”，应用内更新关闭（否则开发版会把自己换成正式版并打开日常数据）。这样同一台电脑上开发调试和日常使用互不影响。源码直接运行的服务（`python3 -m app.server`）和命令行仍默认用仓库里的 `.local/app`。

设置页“存储与导出”可以把论文库搬到别的文件夹（`app/data_location.py`）：复制并校验后，在上表的默认目录里写一个 `location.json` 指向新位置，然后重启应用；原文件夹原样保留，由用户确认后自己删除。选中的文件夹里已有 PageTide 论文库时直接改用它，不覆盖。新位置下次启动时找不到（如移动硬盘没接上），应用回到默认目录并在设置页提示。

环境变量 `PAGETIDE_DATA` 可覆盖（两系统、两种构建都一样）。用这个变量指定时，设置页不能更改数据目录。卸载应用不会删除数据目录（Windows 的数据目录刻意不与安装目录 `%LOCALAPPDATA%\PageTide` 同名）。

## Windows 上没有验证的部分

没有在 Windows 真机上运行过。`Cargo.lock` 已提交（含 `rfd`、`tauri-plugin-single-instance`），CI 用 `--locked`；GitHub 的 Windows 运行器上单元测试、Node 测试、PyInstaller、打包冒烟和 NSIS 已通过，但那不是真机。未验证：安装包与 WebView2 安装、原生保存对话框（`rfd`）、外部链接打开、退出时的草稿保护与后端进程清理、`msvcrt` 文件锁与父进程句柄检查在真实并发下的表现、单实例插件、启动失败消息框、`%LOCALAPPDATA%\PageTideData` 下 SQLite（WAL）的行为、杀毒软件对未签名 PyInstaller 程序的拦截。Windows 的密钥文件没有 0600，依赖用户配置目录的默认 ACL。依赖 POSIX 的少数测试在 Windows 上已显式跳过；CI 的测试运行器在 Windows 上会容忍临时目录清理失败，并在末尾报告没能删除的目录数。仓库用 `.gitattributes` 固定 LF 换行（Windows 检出成 CRLF 会让按源码切片的 Node 测试失败）。

## macOS Intel 上没有验证的部分

Intel 版（`PageTide-macos-x64.zip`）只在 GitHub 的 `macos-15-intel` 运行器上构建并通过打包冒烟测试，没有在 Intel Mac 真机上打开过，也没有验证 Intel 机器上的应用内更新替换。CI 用 Python 3.11，本地 Apple 芯片包用 3.9.6，两者最低支持的 macOS 版本可能不同，未核对。
