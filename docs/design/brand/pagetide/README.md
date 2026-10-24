# PageTide 设计交付

- PageTide-icon.png：用户于 2026-10-24 选定的图标，原样复制本轮上传附件；小浪闭合，大浪保留开口。1254×1254，外部透明。此图标已经由用户选定。
- PageTide-wordmark.png：新增 PageTide 独立字标设计提案，2172×724，外部透明。深蓝 Page、亮蓝 Tide，T 横画带轻微起伏。字标尚待用户确认。
- PageTide-lockup.png：上述图标与字标的横向组合，外部透明。组合排版只按可见内容边界对齐，没有改动两张源 PNG。
- PageTide-brand-preview.png：组合、独立字标和界面尺寸预览。
- design.json：图标来源及完整内置 image_gen 字标提示词。
- composition.json：组合尺寸与透明边界数据，便于其他 agent 重排。

当前文件是 PNG 设计资产；没有把位图包装成矢量文件，也没有完成逐像素的小尺寸专用图标。
本次仅交付设计，未改应用、未重新打包。


## 应用里怎么用（2026-10-24，ADR 0044）

`build_icons.py` 从 `PageTide-icon.png` 与 `PageTide-wordmark.png` 生成 `src-tauri/icons/*`、`app/static/favicon.png`、`wordmark.png`、`wordmark-dark.png`（需要 Pillow）。素材本身原样保留作来源；图标设计由 owner 于 2026-10-24 选定，字标随同一次交付。旧海狮图标在 `docs/design/logo/`，不再使用。
