# 测试与验收边界

当前仓库包含实际 Python 应用、SQLite、来源适配器、唯一模型网关及桌面网页界面。标准回归以临时数据目录和合成 transport 运行；不要把 `HOME`、`PAGETIDE_DATA_DIR` 指向正式资料，也不要为普通回归提供真实密钥。

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
```

Python 3.9+ 是基础环境；关系图测试需要项目构建环境中的 NetworkX。Node 测试使用项目支持的 Node LTS，覆盖浏览器状态、请求与回复契约，不等于原生 macOS 窗口验收。完整桌面包还要用 `scripts/build_desktop.py`、`cargo tauri build --bundles app` 构建并验证实际产物。

预算检查只核对登记与算术，不发模型请求，也不证明账单、tokenizer 或真实输出质量。核心搜索、排序、反馈、归档与维护每日强制模型最低 0 token；可选模型操作必须经过网关和独立授权的测试账本。不得把跳过、合成回复或 gate 定义描述成真实评估通过。

真实评估需记录版本、样本来源与哈希、环境、命令、结果和独立审查者。推荐收益、多学科内容质量、原生操作、恢复、资源使用与真人体验各自验收；未运行项保留 `not_run`。公开脱敏证据放在 `docs/evidence/`，私有快照、原始回复和账本放在忽略的 `.local/`。

### 原生补测后的页面确认与层级回归

`test_dom_dialog_fixes.cjs` 实际执行共享 DOM 确认：显式取消/Escape、默认取消焦点、串行队列、过期对象拒绝及持续 ARIA 通知。`test_import_confirm_fixes.cjs` 执行真实放弃 handler，检查未确认不删除、双击不重复、取消保留批次和切批次拒绝。`test_settings_audit_fixes.cjs` 执行设置导出 handler 的 saved/cancelled/未知回执/写错/重复 picker 分支。`test_reader_layer_fixes.cjs` 执行真实键盘 handler、暂停 rAF 的有界等待和 canvas/text 完成回执；不会将 VM 模拟当作原生焦点、可访问性或像素渲染通过。新增系统字符串和首次手动概念名由实际 i18n/handler 回归覆盖，既有用户内容保持原文。

`test_creation_quit_fixes.cjs` 实际执行创建页退出 helper 和真实状态/请求适配函数：默认取消、返回审阅、显式放弃未提交修改、Escape/键盘、无 input 事件的表单变更、处理中的种子/网关请求、迟到 busy、IPC 错误与重复退出。退出没有新增模型请求、没有静默 finalize 项目，也没有删除已有引导草稿；原生 CmdQ/关闭窗口需在 Rust 菜单修复后的新桌面包独立复验。

macOS Rust 的 `cargo test --manifest-path src-tauri/Cargo.toml native_quit_policy --offline` 直接运行系统退出回执策略与真实 callback 的未注册状态：未确认先取消 Cocoa 退出、异常不批准且能重试、已确认不重复派发。测试不创建 NSApplication/窗口，不等于 Dock Quit/AppleEvent 实际验收；最终新桌面包仍须验证 Dock、CmdQ、关闭窗口的 Cancel/Return/Discard 与冷重启、后台子进程结束。

### 系统语言与用户材料隔离回归

`test_system_i18n_fixes.cjs` 用真实页面 render/helper 生成 DOM，再执行实际 `i18n.js` 的 MutationObserver 处理。覆盖画像反馈/来源/公式/活动、空态/冻结态、项目创建模式、学习前置提示、旧中文可见输入回执、导入错误、RIS/CSL/BibTeX 记录错误和撤销事件；损坏 PDF 回执描述“未保存为导入条目”，不声称未发生传输。命名槽只用于已知系统框架，中文项目名、题名、概念、分类、词项、反馈理由和原文片段保留；特意使用“有用/收藏/种子”等与 UI 字典相同的用户文字，检查正文与可访问标签都不被误译。原始错误中的 HTML 先经系统框架格式化再转义，未知诊断不推定已翻译。中英文检查按实际页面语言重载与重新 render，不冒称历史自由文本反向翻译。

该测试使用本地 VM DOM transport；不是 macOS 实际窗口、键盘、字体或全部任意文本的验收。静态提取器包含共享 `i18n.js` 的系统格式化入口，缺项为零只是字典覆盖检查，不能代替真实渲染。

`test_reader_draft_scope_fixes.cjs` 执行真实助手上下文与发送入口：未发送问题按论文和阅读项目分开，返回原上下文恢复中文多行原文，同对象重开和迟到会话历史不覆盖输入，清空后不复活，未选择论文时发送不丢输入。草稿只在当前窗口内存保留，不进入模型请求、数据库或笔记；没有冷重启持久化承诺，也不为内存限额静默删除用户草稿。最终桌面包仍需复验切论文和项目。
