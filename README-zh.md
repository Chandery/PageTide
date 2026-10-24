<!-- 与 README.md 保持同步 -->
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="app/static/wordmark-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="app/static/wordmark.png">
  <img src="app/static/wordmark.png" alt="PageTide" width="360">
</picture>

**开源的论文发现与管理助手。**

学习你的研究画像，每天推荐新论文，收进属于你自己的论文库。

轻量 · 简单 · 高效 · 开源

<a href="README.md">English</a> · 简体中文

[![Release](https://img.shields.io/github/v/release/Chandery/PageTide?style=flat-square&color=086EF5)](https://github.com/Chandery/PageTide/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-086EF5?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20Silicon%20%7C%20Windows%20x64-555?style=flat-square)

[![下载 PageTide](https://img.shields.io/badge/下载-PageTide-086EF5?style=for-the-badge)](https://github.com/Chandery/PageTide/releases/latest)

<a href="https://github.com/Chandery/PageTide/releases/latest"><img src="docs/assets/readme/pagetide-loop.gif" alt="PageTide 演示" width="880"></a>

</div>

每天有两万篇新论文发表，真正与你有关的寥寥几篇。PageTide 是一个桌面应用：每天早上替你检索 arXiv、OpenAlex 和百度学术，挑出贴合你研究方向的论文，并用一句话讲清每篇说了什么。收藏好的、标记不要的，画像就越来越准。所有数据都留在你自己的电脑上。

## 功能

<table>
<tr>
<td width="50%" valign="top">

**每日推荐**

每天早上一份贴合项目的新论文清单，每篇附一句 AI 速览：它讲了什么，和你有什么关系。

<img src="docs/assets/readme/zh-today.png" alt="今日推荐与 AI 速览">

</td>
<td width="50%" valign="top">

**由你掌控的画像**

清楚看到 PageTide 认为你关心什么。它只从你明确的操作中学习：收藏、不感兴趣、钉住关键词。任何一项都能修改或撤销。

<img src="docs/assets/readme/zh-profile.png" alt="兴趣画像页">

</td>
</tr>
<tr>
<td width="50%" valign="top">

**你的论文库，一图成网**

用列表或关系图浏览收藏的论文，并让 AI 建议分类，帮你整理。

<img src="docs/assets/readme/zh-graph.png" alt="论文库关系图">

</td>
<td width="50%" valign="top">

**边读边问**

打开 PDF，划选一句话，就能在页面旁直接翻译或追问。

<img src="docs/assets/readme/zh-reader-ask.png" alt="阅读器中划词后的回答">

</td>
</tr>
</table>

还包括：

- 周报：看你的画像这一周有什么变化。
- 离线演示项目和首次启动的新手指引。
- 导入已有论文库：PDF 文件和文件夹，或从 Zotero 导出的 BibTeX、RIS 分类。
- 有开放版本的论文可下载 PDF 并归档。
- 中英文界面，浅色与深色主题。
- 应用内检查更新。

## 实际演示

<!-- 30 s promo video: paste the github.com/user-attachments/... URL here on its own line (mp4 under 10 MB) -->

这里将嵌入一段 30 秒的演示视频：从创建项目到对论文提问。

## 隐私优先

> [!NOTE]
> - 论文、画像和笔记只保存在你的电脑上。
> - 无需账号，无遥测，无云同步。
> - 推荐、画像和论文库离线运行，不消耗模型 token。
> - AI 功能可选，使用你自己的 DeepSeek 密钥。

## 下载

| 平台 | 文件 |
| --- | --- |
| macOS（Apple Silicon） | [`PageTide-macos-arm64.zip`](https://github.com/Chandery/PageTide/releases/latest) |
| Windows（x64） | [`PageTide_<version>_x64-setup.exe`](https://github.com/Chandery/PageTide/releases/latest) |

<details>
<summary>首次打开：应用未签名</summary>

PageTide 是独立开源项目，没有购买付费的代码签名证书，所以系统第一次会给出提示。

- **macOS：** 解压后把 PageTide 拖进“应用程序”，右键点它选择“打开”；或到“系统设置 → 隐私与安全性”点“仍要打开”。如果提示“已损坏”，在终端运行 `xattr -dr com.apple.quarantine /Applications/PageTide.app`。
- **Windows：** SmartScreen 提示“已保护你的电脑”时，点“更多信息”，再点“仍要运行”。安装为当前用户，不需要管理员权限。

</details>

## 快速开始

1. 打开 PageTide，选择语言和外观，跟着演示项目走一遍简短的指引。
2. 创建自己的项目：快速创建、AI 引导或手动创建。
3. 生成今日推荐，收藏或标记你看到的论文。
4. 可选：在设置里填入 DeepSeek 密钥，开启 AI 速览和追问。

## 路线与反馈

欢迎在 [Issues](https://github.com/Chandery/PageTide/issues) 提想法、报问题、提需求。

## 参与贡献

从源码运行、跑测试、构建桌面版，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢

Thank you to arXiv for use of its open access interoperability. PageTide 还使用了 [OpenAlex](https://openalex.org)、百度学术、[Tauri](https://tauri.app)、[pdf.js](https://mozilla.github.io/pdf.js/)、[Cytoscape.js](https://js.cytoscape.org)、[NetworkX](https://networkx.org) 和 [Lucide](https://lucide.dev)。

## 许可证

[MIT](LICENSE) © Chandery
