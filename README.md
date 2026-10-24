<!-- keep in sync with README-zh.md -->
<div align="center">

<img src="docs/assets/readme/icon.png" alt="PageTide icon" width="112">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="app/static/wordmark-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="app/static/wordmark.png">
  <img src="app/static/wordmark.png" alt="PageTide" width="320">
</picture>

📚 **An open-source research assistant for discovering and organizing papers.** 🌊

PageTide learns your research profile, recommends new papers every day, and keeps them in a library you own.

🪶 Lightweight &nbsp;·&nbsp; ⚡ Easy &nbsp;·&nbsp; 🚀 Efficient &nbsp;·&nbsp; 🌊 Open source

English · <a href="README-zh.md">简体中文</a>

[![Release](https://img.shields.io/github/v/release/Chandery/PageTide?style=flat-square&color=086EF5)](https://github.com/Chandery/PageTide/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-086EF5?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20Silicon%20%7C%20macOS%20Intel%20%7C%20Windows%20x64-555?style=flat-square)

[![Download PageTide](https://img.shields.io/badge/Download-PageTide-086EF5?style=for-the-badge)](https://github.com/Chandery/PageTide/releases/latest) [![Website](https://img.shields.io/badge/Website-pagetide.chandery.org-12315c?style=for-the-badge)](https://pagetide.chandery.org/)

🌐 **[pagetide.chandery.org](https://pagetide.chandery.org/)** · try the profile demo in your browser

<a href="https://pagetide.chandery.org/"><img src="docs/assets/readme/cover.jpg" alt="PageTide: papers that fit your research" width="880"></a>

</div>

https://github.com/user-attachments/assets/dbc5161f-7600-46f8-909a-9c377fb33406

<p align="center"><sub>🎵 Music by Pumpupthemind</sub></p>

**Stop scrolling feeds. Start the day with papers that fit your research.** PageTide searches arXiv, OpenAlex and Baidu Scholar every morning, ranks what it finds against a research profile you can read and edit, and keeps the papers you save in a library of your own. Ranking runs on your computer without AI; AI explains your picks and answers your questions.

## 📊 By the numbers

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/numbers-en-dark.svg">
  <img src="docs/assets/readme/numbers-en-light.svg" alt="PageTide by the numbers: zero tokens to rank, zero accounts, a single AI call for five previews, 22 MB download; 3 sources, 5 import formats, 3 ways to start, 2 platforms by 2 languages" width="880">
</picture>

## ✨ Features

**📬 Daily picks, explained.** Each morning a short list of new papers ranked against your profile. Every card has a one-line AI preview: what the paper says and why it matters to you. Save it, or mark it **Not interested** or **Too hard** in one click.

**🧭 A profile you can read and edit.** No black box. See the terms behind every pick, pin keywords, remove tags, undo any feedback. It learns only from what you do on purpose: doing nothing never counts as a dislike, and Too hard is not a dislike either.

**🕸️ A library that connects itself.** Saved papers become a list and a graph of related work. Open-access PDFs are archived locally. AI can suggest categories, but nothing changes until you confirm, and every change can be undone.

**✍️ Highlight. Ask. Understand.** Read the PDF inside PageTide, select a sentence, then translate it or ask about it. The answer appears beside the page.

**📥 Bring what you have.** Import PDF files or folders (subfolders become categories), or a Zotero collection exported as BibTeX or RIS.

**📈 A weekly report** of what you saved, what you skipped and which directions grew, plus an offline demo project with a guided tour, English and Chinese interface, light and dark themes, and in-app updates.

<table>
<tr>
<td width="50%"><img src="docs/assets/readme/en-today.png" alt="Today's picks with AI previews"></td>
<td width="50%"><img src="docs/assets/readme/en-reader-ask.png" alt="Highlight a sentence and ask about it"></td>
</tr>
<tr>
<td align="center"><sub>Today's picks, each with an AI preview</sub></td>
<td align="center"><sub>Highlight a sentence, ask, get an answer beside the page</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/assets/readme/en-profile.png" alt="Interest profile"></td>
<td width="50%"><img src="docs/assets/readme/en-graph.png" alt="Library graph"></td>
</tr>
<tr>
<td align="center"><sub>A profile you can read: terms, pins and feedback</sub></td>
<td align="center"><sub>Your library as a graph of related papers</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/assets/readme/en-import.png" alt="Import page"></td>
<td width="50%"><img src="docs/assets/readme/en-weekly.png" alt="Weekly report"></td>
</tr>
<tr>
<td align="center"><sub>Import PDF folders or a Zotero export</sub></td>
<td align="center"><sub>A weekly report of what changed</sub></td>
</tr>
</table>

## 🔌 Connect your services

PageTide works out of the box on arXiv. Add your own keys to switch on more sources and the AI features. Everything is optional and lives in **Settings**.

| Service | Used for | Key | Get one |
| --- | --- | --- | --- |
| **DeepSeek** | AI previews, follow-up questions, selection translation, AI-guided project setup, category suggestions | Your own API key | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) |
| **arXiv** | New preprints every day | None needed | n/a |
| **OpenAlex** | Journal and conference papers | Optional. A free key raises the daily allowance about 10 times (1,000 to 10,000 credits) | [OpenAlex API keys](https://help.openalex.org/api-reference/authentication) |
| **Baidu Scholar** | Chinese-language papers (listed as "Baidu Search" in Settings) | Your own Baidu Qianfan key; PageTide limits itself to 40 searches a day on it | [Qianfan console](https://console.bce.baidu.com/qianfan/ais/console/apiKey) |

> [!NOTE]
> You type every key into Settings yourself. Keys are saved in a local file inside PageTide's data folder, never in the settings file, and each key is sent only to the service it belongs to. There is no PageTide server.

## 🚀 Getting started

1. **Download** PageTide for macOS or Windows (see [Download](#-download)) and open it.
2. **Pick a language and a look**, then follow the short tour through the demo project. It is offline and needs no key.
3. **Create your project**: Quick start (one sentence, one AI call), AI guided (chat until the keywords feel right) or Manual (no AI).
4. **Add your keys** in Settings if you want AI and more sources (see [Connect your services](#-connect-your-services)).
5. **Press Pick today's papers.** Save what you like, mark the rest, and watch the profile follow.

## 🔒 Private by design

> [!NOTE]
> - Your papers, profile and notes are stored on your computer only.
> - No account, no telemetry, no cloud sync.
> - Recommendations, the profile and the library work offline and use no model tokens.
> - AI features are optional and use your own DeepSeek API key.

## 📥 Download

| Platform | File |
| --- | --- |
| macOS (Apple Silicon) | [`PageTide-macos-arm64.zip`](https://github.com/Chandery/PageTide/releases/latest) · 22 MB |
| macOS (Intel) | [`PageTide-macos-x64.zip`](https://github.com/Chandery/PageTide/releases/latest) |
| Windows (x64) | [`PageTide_<version>_x64-setup.exe`](https://github.com/Chandery/PageTide/releases/latest) · 17 MB |

<details>
<summary>First launch: the app is not signed</summary>

PageTide is an independent open-source project and has no paid code-signing certificate, so your system will warn you the first time.

- **macOS:** unzip, drag PageTide to Applications, then right-click it and choose Open. Or go to System Settings, Privacy & Security, and click Open Anyway. If macOS says the app is damaged, run `xattr -dr com.apple.quarantine /Applications/PageTide.app` in Terminal.
- **Windows:** when SmartScreen says "Windows protected your PC", click More info, then Run anyway. The installer is per-user and needs no administrator rights.

</details>

## ❓ FAQ

<details>
<summary><b>Where is my data stored?</b></summary>

On your computer only. On macOS it is `~/Library/Application Support/PageTide`, on Windows `%LOCALAPPDATA%\PageTideData`. The path is also shown in Settings under Storage and export, where you can export everything.

</details>

<details>
<summary><b>Does it work without a DeepSeek key?</b></summary>

Yes. Recommendations, the profile, the library, import and PDF archiving all work offline and use no model tokens. The key only adds AI previews, follow-up questions, translation, AI-guided setup and category suggestions.

</details>

<details>
<summary><b>How much do the AI features cost?</b></summary>

You pay DeepSeek directly, at DeepSeek's prices, with your own key. PageTide sends only the text each feature needs (never your whole library), records every request's token use in Settings under AI usage records, and one checkbox turns AI off.

</details>

<details>
<summary><b>Can I use Chinese-language papers?</b></summary>

Yes. Tick Chinese as a paper language when you create a project and add a Qianfan key for Baidu Scholar, or just use OpenAlex.

</details>

<details>
<summary><b>How do I update?</b></summary>

PageTide checks for updates itself and shows a banner. You can also press Check for updates in Settings.

</details>

## 🤝 Contributing

**Contributions of every kind are welcome.** Found a bug? Have an idea? Spotted a typo, or want to translate a screen? Open an [issue](https://github.com/Chandery/PageTide/issues) or send a pull request. You do not need to be an expert, and small fixes are as welcome as new features.

- **Report a bug or suggest a feature:** [open an issue](https://github.com/Chandery/PageTide/issues). Screenshots help, and please leave out any API keys.
- **Improve the docs or translations:** just edit and open a PR.
- **Write code:** for bigger changes, start with an issue so we can agree on the direction first. Setup, tests and build commands are in [CONTRIBUTING.md](CONTRIBUTING.md).

If PageTide saves you time, a star on GitHub helps other researchers find it. ⭐

## 🙏 Acknowledgments

Thank you to arXiv for use of its open access interoperability. PageTide also builds on [OpenAlex](https://openalex.org), Baidu Scholar, [Tauri](https://tauri.app), [pdf.js](https://mozilla.github.io/pdf.js/), [Cytoscape.js](https://js.cytoscape.org), [NetworkX](https://networkx.org) and [Lucide](https://lucide.dev). Promo video music by Pumpupthemind.

## 📄 License

[MIT](LICENSE) © Chandery
