# 发布流程

两个平台都是**未签名**构建。macOS 在本机构建，Windows 由 GitHub Actions 构建（[ADR 0040](decisions/0040-windows-release.md)）。

## 发一个版本

1. 合并到 `main`，本地跑完 AGENTS.md 里的检查（预算、harness、单元测试、Node 测试）。
2. 改版本号（`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`），提交，打标签并推送：`git tag vX.Y.Z && git push origin vX.Y.Z`。
3. 标签推送触发 `release` 工作流：`windows` 作业构建 NSIS 安装包并上传 artifact；`publish` 作业把 `PaperDigHelper_*_x64-setup.exe` 和 `.sha256` 传到该标签的 release（release 不存在则建为**草稿**）。也可在 Actions 页面手动运行（`workflow_dispatch`），此时只产出 artifact，不发布。
4. macOS 包在本机构建（见下），把 zip 和校验和手动传到同一个 release：`gh release upload vX.Y.Z PaperDigHelper-macos-arm64.zip PaperDigHelper-macos-arm64.zip.sha256`。
5. 检查草稿 release 里两个平台的文件，再手动发布。

## macOS 本机构建

```sh
.local/desktop-build-env/bin/python scripts/build_desktop.py
cargo tauri build --bundles app
cd src-tauri/target/release/bundle/macos
ditto -c -k --keepParent PaperDigHelper.app PaperDigHelper-macos-arm64.zip
shasum -a 256 PaperDigHelper-macos-arm64.zip > PaperDigHelper-macos-arm64.zip.sha256
```

`build_desktop.py` 用 `PDH_BUILD_PYTHON` 指定的 Python；没设时在 macOS 上用 `.local/desktop-build-env`（Python 3.9.6），其他情况用当前解释器。

## 用户首次打开（未签名）

- **macOS**：解压后拖进“应用程序”，右键应用 → 打开 → 再点“打开”；或终端执行 `xattr -dr com.apple.quarantine /Applications/PaperDigHelper.app`。
- **Windows**：运行安装包，SmartScreen 提示“已保护你的电脑”时点 **更多信息 → 仍要运行**。安装为当前用户（不需要管理员）。若系统没有 WebView2 运行时，安装器会联网下载它。
- 校验：`shasum -a 256 -c <文件>.sha256`（macOS），`Get-FileHash <文件> -Algorithm SHA256`（Windows）与 `.sha256` 内容比对。

## 数据位置

| 系统 | 数据目录 |
| --- | --- |
| macOS | `~/Library/Application Support/PaperDigHelper` |
| Windows | `%APPDATA%\PaperDigHelper` |

环境变量 `PAPERDIGHELPER_DATA` 可覆盖（两系统相同）。卸载应用不会删除数据目录。

## Windows 上没有验证的部分

没有在 Windows 真机上运行过。未验证：安装包与 WebView2 安装、原生保存对话框（`rfd`）、外部链接打开、退出时的草稿保护与后端进程清理、`msvcrt` 文件锁在真实并发下的表现、`%APPDATA%` 下 SQLite（WAL）的行为、杀毒软件对未签名 PyInstaller 程序的拦截。Windows 的密钥文件没有 0600，依赖用户配置目录的默认 ACL。CI 里的单元测试与打包冒烟是第一次在 Windows 上运行，依赖 POSIX 的少数测试已显式跳过。
