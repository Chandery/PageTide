# 自审：PDF 阅读器里捏合缩小会打开项目总览（2026-10-01）

自审，不是独立评审。owner 反馈：打开 PDF 时双指捏合缩小，也会进入项目管理页面（Mission Control 式总览）。

## 原因
- 项目总览在 `window` 上监听触控板捏合：Chromium 里是 ctrl+wheel（捕获阶段），WebKit 里是 `gesturestart`/`gesturechange`。
- 原来只排除了知识库图谱 `.org-graph`。阅读器 `#readerPages` 自己也用同一个捏合手势缩放，事件继续到达 `window`，捏合缩小累计超过阈值就打开了总览。

## 改动
- `project-switcher.js` 新增纯函数 `pinchIgnored(target, opts, open)`：总览关闭时，目标落在 `pinchIgnore` 区域内，或 `pinchBlocked()` 为真，捏合都交给页面自己处理；总览已打开时不受影响。
- `index.html` 挂载时传入 `pinchIgnore: '.org-graph, #reader, .pdfbox'`，以及 `pinchBlocked: () => body.reader-open`。这样即使在阅读器标题栏上捏合，也不会打开总览。
- 阅读器自身的缩放逻辑没有改动。

## 预览实测（合成 ctrl+wheel 事件）
- 打开阅读器后捏合缩小：缩放从 92% 变为 56%，总览没有打开；在阅读器标题栏上捏合同样不打开。
- 关闭阅读器后在主页面捏合：总览打开（`mc-open`），按 Esc 关闭。
- 再次打开阅读器捏合：总览仍然不打开。

## 测试
- `tests/test_project_switcher.cjs` 新增两项，共 9 项：
  - 阅读器、PDF 区域、图谱上的捏合被忽略；阅读器打开时一律忽略；总览已打开时不忽略。
  - 主页面的挂载代码包含 `#reader` 和 `pinchBlocked`。

## 未测 / 风险
- 只用 Chromium 的合成 ctrl+wheel 事件验证。.app（WKWebView）走 gesture 事件，经过同一个 `ignored()` 判断，但没有用真实触控板重放，需要 owner 实机确认。
