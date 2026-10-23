# ADR 0040：发布范围扩到 Windows x64；打包与 release 流程

2026-10-23。此前产品只面向 macOS（AGENTS.md：owner confirmed macOS-only）。owner 在本日要求：

> “好了，现在请你做好包装，推到远程，release 要包括 macos 版本和 windows 版本”

**这条引文是 owner 的请求记录；变更记录里的 `owner_approved` 仍是 false，不由 agent 自填。** 它放宽了“只做 macOS”，没有放宽 AGENTS 的其他边界（无托管后端、无遥测、模型只经网关、零 token 核心路径）。

## 决定

1. **目标**：macOS arm64（`.app`，由维护者在本机构建，`ditto` 打 zip）与 Windows x64（NSIS 安装包，由 GitHub Actions 的 `windows-latest` 构建）。同一套代码：Tauri 2 外壳 + PyInstaller one-dir Python 后端。
2. **平台差异收在两处**：Python 侧 `app/platform_compat.py`（文件锁：macOS `fcntl.flock`、Windows `msvcrt.locking` 第 0 字节；`register_at_fork` 仅在存在时注册；默认数据目录：macOS `~/Library/Application Support/PaperDigHelper`、Windows `%APPDATA%\PaperDigHelper`）；Rust 侧 `src-tauri/src/main.rs` 的 `cfg`（后端文件名 `.exe`、`rundll32 url.dll,FileProtocolHandler` 打开 http/https、`CREATE_NO_WINDOW`、`rfd` 保存对话框）。macOS 的原生退出守卫、保存面板代码不动。
3. **数据与密钥保护**：POSIX 上密钥和备份仍是 0600；Windows 没有等价的 mode 位，保护来自每用户配置目录（`%APPDATA%`）的默认 ACL。这是较弱的保证（同一 Windows 账户下的其他进程可读），不是“已加固”。
4. **WebView2**：安装包嵌入 Microsoft 的 WebView2 bootstrapper（`embedBootstrapper`，静默）。系统已有运行时（Windows 11、较新的 Windows 10）时不下载任何东西；没有时 bootstrapper 需要联网下载运行时。没有选“固定版本运行时”（会让安装包增大约 150 MB 以上）。
5. **未签名**：两个平台都不签名、不公证（没有证书，也不使用任何 secret）。用户首次打开会遇到 macOS Gatekeeper / Windows SmartScreen 提示，见 [RELEASE](../RELEASE.md)。
6. **CI**：`.github/workflows/release.yml`，`workflow_dispatch` 与 `v*` 标签触发；`windows` 作业只读权限，跑测试、构建、冒烟、上传 artifact；`publish` 作业仅标签触发、仅它有 `contents: write`，把安装包与校验和传到该标签的 release（不存在则建草稿）。第三方 action 暂用主版本标签，改成提交 SHA 是后续项。
7. **Windows 上的显式跳过测试**：依赖 POSIX 文件 mode、符号链接权限、`select` 管道或 macOS 路径的测试用 `skipIf(win32)` 并写明原因；0600 断言在 Windows 上只是不执行，其余照跑。

## 没有验证

Windows 代码路径（Rust `cfg(windows)`、`rfd`、msvcrt 锁、NSIS 打包、WebView2）在作者的 macOS 机器上无法编译或运行；首个验证是 CI。**没有任何 Windows 真机运行证据。**
