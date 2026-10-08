# 阅读器、导出和退出恢复修复

修复检出：`audit-bug-fixes`，基线 `8e5cfd7`。用户已授权逐条修复；本代理仅写该隔离 worktree，不写正式资料，不运行模型，不合并、不运行原生窗口。以下为代码和确定性回归证据，桌面构建、原生动作、最终独立复审由主代理集成，不能把本文件称为整产品发布通过。

| 问题 | 改动与不丢资料的边界 | 当前验证 |
|---|---|---|
| B01 跨论文上下文 | Reader/助手携带论文、阅读项目、当前 PDF SHA；换对象清引用、附图开关、旧显示；异步加载和迟到回复检查 epoch。PDF 请求可指定 SHA，已换版本返回 409；网关前核对传入证据。关闭阅读器之后不会借旧 R.doc 给新论文自动附图。 | 身份 Node、HTTP 拒绝错 key/错 SHA、网关零调用；原生待验 |
| B05 导出不全 | 设置导出明确改为全部项目的结构化快照 v1；SQLite backup 得到一致性副本，包含所有表而非固定字段，含图、历史、草稿、反馈、画像、问答会话、导入状态和未来新表。附格式、版本、表记录数、字节数和 SHA；不含凭据、PDF/导入暂存文件字节、来源缓存，界面分别说明。恢复校验仅写全新目录，拒绝覆盖；不跟随 PDF 路径、不碰原文件。 | 临时 DB 恢复校验与实际 HTTP 双项目导出；所有表/历史/设置恢复、integrity_check=ok |
| B16 清空旧上下文 | “清空”改为“新会话”，服务端持久保存会话 id 和历史 cursor；旧问答不删除，但新回答不带旧历史。返回/冷启载入当前会话最近 20 条，下一模型请求最多取最近 6 条，避免隐藏仍在使用的上下文；PDF 准备完重新取会话，发送在加载时禁用。会话/PDF 版本变化前、中、结果写入事务再次校验，拒绝迟到结果。 | 会话持久及下一请求实际消息检查；并发 reset 后旧回复不落库；更换 PDF 切新会话 |
| B17 缓存误报 | 服务器和 settings 联动，失败返回 HTTP 500；前端检查响应，准确表示只清来源响应缓存，PDF、全文、笔记、项目保留。 | HTTP PermissionError 500，正常清理包含准确 preserved/removed 回执；前端由 discovery 代理复核 |
| B23 错误路径 | `/api/data-location` 从实际 data root 返回目录；设置及主页页脚显示该路径，不硬编码 Documents/.local/app。 | HTTP 路径与隔离库实际路径完全一致；原生待验 |
| B24 可读性与语言 | 翻译先显示再量尺寸、回复完成后重新 clamp，窗口/浮层尺寸变化也重新定位；整浮层限高可滚。追问按钮完整换行、title，迟到翻译不跨会话重新显示。缩小关系图时收起拥挤题名，选中/悬停仍显示；可从目录定位；新增英语条目。综述/会议类型在卡片与详情单独显示。 | popup 底部/右侧小窗计算回归、19 既有 UI 布局测试；实际几何/语言/密图原生待验，不声称全可访问性完成 |
| B26 原生导出无文件 | 论文库和设置共用真实 Tauri `save_export`，macOS NSSavePanel；写临时文件、sync、原子 rename，成功返回真实路径/字节，取消明确回执，写错抛错误。文件权限 0600。网页缺少可确认 save picker 时提示去桌面，不再 Blob 静默成功。 | Node save/cancel/error/不支持浏览器四分支；实际原生 NSSavePanel 和磁盘文件待集成 |
| B27 键盘逃逸 | 阅读器 role=dialog/aria-modal；显示时背景 inert，Tab/Shift+Tab 循环、外部 focus 返回可见控件，Back/Escape 退出恢复之前焦点及原 inert 状态。 | 代码检查与布局回归；640×480 实际 Tab 路径待主代理重测 |
| B28 论文库项目错接 | 从所选论文库项目进入阅读，跨项目入口不改顶部项目；全部项目视图优先当前所属项目，只有一个所属项目则明确携带，多个且顶部不属则选择会话项目。项目名称随助手论文标题展示；保持后端归属校验。 | 实际 organization handler 回归：医学顶部、CS 范围、共享/单项目均发正确 reading project |
| B29 短退出丢草稿 | Tauri ExitRequested/CloseRequested 暂缓退出，页面立即清计时器并等待队列，把最新 dirty draft 写 DB 后 `complete_quit`；失败保持应用打开和编辑内容并提示。随机 port、每实例私有 token、目录锁保持原样，没有共享 origin 或稳定公共端口。 | 250ms 前立即退出 VM 行为：先最新 draft-save 再 quit；存储失败无 quit；原生快速 Quit/冷启待集成 |

## 权限和资源契约

原生两条 IPC 通过构建 manifest 生成专门权限，启动时只给本实例的**精确随机 loopback origin** 和 `main` 窗口授予；Rust 每次还校验实际 webview origin/label，外部页面继续拒绝导航。没有 shell/file 泛权限和固定端口。保存路径只能由原生 save panel 用户选择；默认名称不能包含目录分隔符。单次原生字符串导出最多 512 MB，超过明确错误，不假成功；大型库/8GB 实测仍未验证。直接依赖 serde_json 和 objc2 Foundation/AppKit 均已存在当前 Cargo 缓存/锁的传递依赖中，不装全局工具。参考：[Tauri 能力隔离](https://v2.tauri.app/security/capabilities/)、[运行期授权](https://v2.tauri.app/security/runtime-authority/)，NSSavePanel 方法按本机 objc2 0.3.2 官方绑定核对。

结构化快照与 PDF 归档备份是两件明确的事。恢复 helper 用于逐表完整性复验/检查，**没有新增用户恢复入口**；真正迁移使用前仍须复制/重定位归档路径，不能将仅恢复 DB 冒充已恢复所有 PDF 文件。新增运行期模型 token 为 0；没有改问答模型、预算上限或正式账本。

## 已执行验证

失败先行：新会话/证据测试初次 2 个 ImportError、快照测试初次 ModuleNotFoundError，新增能力缺失。快照首次实现还失败 `unable to open database file`：临时 backup 继承 WAL，读取主文件遗漏 WAL；仅临时副本转 DELETE journal 并关闭后修复，源库 journal 不改。既有 organization 阅读回归最初 1/94 失败，原因签名新增第三个明确 project（旧 fixture 为无所属项目）；更新期望 null，并新增跨项目真实 handler 检查，没有放宽断言。

- `python3 -m unittest discover -s tests -p test_reader_context_fixes.py -v`：3/3，exit 0，0.023s。
- `python3 -m unittest discover -s tests -p test_local_snapshot_fixes.py -v`：1/1，exit 0，0.018s（后续新增事务前置拒绝待最终同源复跑）。
- `python3 -m unittest discover -s tests -p test_reader_http_fixes.py -v`：6/6，exit 0，3.223s，含晚到回复 reset。
- `node --test tests/test_reader_identity_fixes.cjs tests/test_organization_ui.cjs`：95/95，exit 0，177.179791ms（后续缩小图标签改动待最终同源复跑）。
- `node --test tests/test_draft_quit_fixes.cjs tests/test_save_file_fixes.cjs tests/test_reader_identity_fixes.cjs`：7/7，exit 0，37.321584ms。
- `python3 -m unittest discover -s tests -p test_ui_layout.py -v`：19/19，exit 0，0.009s。
- 两段 index 内联 JS `vm.Script` 语法解析通过；静态英文缺项首次 21，补后 0/1367（后续 6 条新说明已补，待最终 extractor）。
- 既有 `test_app_server.py`：21 项 1 失败/11.030s，旧上传 fixture 不是完整 PDF，被主代理 B22 防线拒绝；已通知主代理替换为真实结构 synthetic PDF。该失败未计通过。

所有模型接口被 mock，不付费调用、不上传任何用户资料。这里的通过只证明列出的软件行为；模型内容质量、原生窗口实测和最终整产品 gate 未在本代理关闭。

## 最终源码补查

- 最终 `node --test tests/test_reader_identity_fixes.cjs tests/test_organization_ui.cjs tests/test_draft_quit_fixes.cjs tests/test_save_file_fixes.cjs`：99/99，exit 0，205.468458ms，包含低缩放标签源码后的组织图行为。
- 最终 `test_local_snapshot_fixes.py`：1/1，exit 0，0.016s，事务前置拒绝同源且明确校验 sanitized settings 不含凭据。
- 最终 `test_ui_layout.py`：19/19，exit 0，0.017s；`i18n_extract.py`：0/1373；`git diff --check` exit 0。
- 最新 index 两段内联脚本语法解析通过。
- `node --test tests/test_reader_send_fixes.cjs`：2/2，exit 0，46.878875ms；直接提取并执行产品 `ask()`，错论文/错项目/错引用版本均在 API transport 前拒绝；正确请求实际携带所选阅读项目、引用和 PDF SHA，即使顶部是其他项目。
- 保存/退出 IPC、后台 inert 和浮层实际像素几何均仍以主代理原生包验收为准，不能用 VM 或静态断言替代。

## B29 集成补修 R-F18：学习图页面退出（最终冻结 2026-10-07 22:13:52 UTC）

独立复审确认真实 Rust `prepare_quit` 的页面fallback在route.html没有 `PDHPrepareQuit` 时直接 `complete_quit`，绕过原beforeunload的dirty graph/brief提示。这里新增学习图页面实际退出hook，随机origin/IPC授权与原生机制不变。

- 图、需求、尚在编辑的概念、未确认AI简介和未确认修订预览都要求选择；退出不会自动调用save、revision-confirm或模型。
- 页面提供“返回检查并保存”“取消退出”“放弃本页未保存修改并退出”。返回检查只定位现有保存/编辑/确认操作；取消保留全部内容；只有明确放弃才请求退出。服务器已保存的AI预览保留，提示不误称已删除。
- 保存、公开核对、AI判断仍在进行时不退出；选择框打开后若新操作开始，再点放弃也不能绕过。原生命令失败保留所有修改并显示应用保持打开；clean正常退出，重复请求不双重确认。
- 主Save在概念编辑框/AI简介未确认时拒绝保存，提示先“确定”或“取消”，防止重绘丢掉未提交输入。创建图显式Save仅清除已提交需求的dirty；请求中晚输入仍保留dirty，不被已保存旧需求覆盖。
- HTML使用原生dialog提供焦点约束，样式在已有project-creation.css，保留no-inline-style约束；8条中英文新提示齐全。浏览器beforeunload与native hook使用同一待确认/进行中谓词。

失败先行：真实route-page VM使用原Rust eval脚本，旧hook缺失时dirty仍调用complete_quit；初轮8项为6失败、2因缺去重导致未结promise而取消，未计通过。追加未确认简介主Save控制初次失败后补拒绝，没有把AI草稿自动当用户确认。

最终实际检查：

- `tests/test_route_quit_fixes.cjs`真实函数VM **10/10通过**，含明确Save写一次、取消/放弃、busy、新操作、IPC错误、晚输入、重复退出、浏览器unload。
- Node quit/drafts/brief/editor/i18n合计 **96/96通过**，exit0，110.523ms；英文extractor **0 missing /1413**。
- Python explore_new/recommendation_eligibility/route_full_flow/weekly_detail四组 **79/79通过**，exit0，0.928s。探索正例补题名/摘要实际匹配的公共query与明确正向方向资料，另留无用途unmatched阴性；LRU预算恢复、3+1+1、完整反馈/撤销/重启旧断言不放宽。周报用实际周内材料与输出核验，上一周的understood与老库材料不混入当前周，不再依赖过时assign签名spy。
- 本轮上述检查全部隔离临时数据，0模型/0网络；主工作单元独立复核另行记录。
- **真实原生Cmd+Q/关闭、对话框操作与冷重启状态仍blocked**，本代理未运行原生窗口，不能用VM冒充实际桌面退出验证或发布通过。

本次冻结源码/测试：

| 文件 | SHA256 |
|---|---|
| `app/static/route-page.js` | `440f698623ec788c5128be915fba64d943f3092fe5791fd4cb77c846e9e89fb4` |
| `app/static/route.html` | `c5e5749e9592492b9763197500347d175f213d0df6f8b990b8fd4be974fa2e59` |
| `app/static/project-creation.css` | `9007d2eb9fdd79a0a807151056ab7e3d7b882f3a4c1de6ceff0414a3b99a8217` |
| `app/static/i18n/en-US.json` | `f3fdd72afaf87671a80b6aa78df5e402822d06ac4c4ea757dbe6ea39387798fc` |
| `tests/test_route_quit_fixes.cjs` | `d1b5db9c0508e923b97baaa7a270f61c3578c08d72573ee0439c95c56acf27ba` |

私有原始日志：`.local/audit-fixes-native-20261008/route-quit-before.log`、`route-quit-edit-before.log`、`reader-integration-node.log`、`reader-integration-python.log`。最终全量/构建及原生限制由主工作单元写入总报告。

## 原生补测补修：页面确认、导出取消、Esc 与暂停画面刷新（2026-10-08）

主代理在隔离原生包实际发现：Wry 没有 JS alert/confirm hook，导入“放弃”无动作；设置检查 `result.cancelled` 与真实 `{status:'cancelled'}` 不一致；助手输入中文后 Tab/Esc 把阅读器关掉，助手却仍打开。主代理另观察到窗口 Zoom 后 PDF 才重新绘制，AX 仍含旧加载提示；这里按确定性的无限 rAF 等待和未删除加载节点修源码，不将截图/前台绘制时机推断写成确认的渲染 bug。

- 新 `dialogs.js/css` 提供真正的 DOM `<dialog>`，带名称、说明、Cancel 初始焦点、Tab/Shift+Tab 循环和明确 Cancel/Escape=false；队列逐个显示，任何未显示/失败/上下文过期均不批准。决策采用 textContent，既不解释 HTML，也不触发模型。确认关闭恢复仍有效的旧焦点。
- 设置、创建（切换模式/重新生成）、画像恢复、笔记历史覆盖、导入停止检索/放弃和未完成批次放弃全部 await DOM 确认。关键调用禁重复提交，确认期间项目/会话/论文/批次变化会拒绝旧决定；取消不清当前草稿/数据。原生 alert 调用替换为持续 ARIA 状态/错误提示，设置导出在操作旁持续显示。
- 导出逐个处理 saved/cancelled/未知回执/异常，只对 saved 显示路径；取消明确报告且数据不变；保存 picker 未完成时不再打开第二个。缓存失败仍不显示成功，取消不调用删除接口。
- Reader Esc 依最上层关闭翻译、选中文本工具、助手，然后阅读器；真实 `<dialog>` 打开时不抢其 Escape/Tab/focus。助手关闭恢复入口焦点，关闭阅读器也收起助手，中文未提交文本保留；IME composition 期间不关层。
- `afterPaints` 至多等 250ms，完成后取消定时器/待执行帧。页面 canvas 和文字层仍必须真的 await 成功，失败返回 false；初次失败走既有内置预览，已有可见画面仍保留。只有真实 render 成功且 epoch/doc/jobs 未过期才揭开新 stage、删直接子加载提示并换旧 stage；迟到阶段不擦新对象。
- 英语过滤统计拆独立文字节点，PDF 已知校验错误翻译而文件名不变；无摘要占位移到可翻译节点。撤销导入分类已有 pack 明确保留，复验翻译。手动新概念只在新建时使用当前语言默认名；现存用户图/名字/笔记不翻译；操作“删除”英文改为 Remove。

失败先行：共享 DOM 测试初次 0/4（helper 缺失 + 五类真实调用仍是 native）；真实 reader handler/paint 测试初次 0/3，直接复现 Esc 错关阅读器、浮层不关闭和无 rAF 时 450ms 仍未完成。导出取消分支与真实 import handler 追加针对回归。import UI 精确加载顺序初次 26/27，新增 /dialogs.js 后更新为完整本地依赖顺序，没有移除原本顺序/资源限制。

已执行（均离线 VM/临时后端，不调用模型、不运行 native、不构建）：

- `node --test tests/test_dom_dialog_fixes.cjs tests/test_import_confirm_fixes.cjs tests/test_reader_layer_fixes.cjs tests/test_settings_audit_fixes.cjs tests/test_i18n.cjs tests/test_organization_ui.cjs tests/test_reader_identity_fixes.cjs tests/test_reader_send_fixes.cjs tests/test_draft_quit_fixes.cjs tests/test_route_quit_fixes.cjs`：157/157，exit 0，516.305709ms。
- 新增 IME 守卫后，`node --test tests/test_reader_layer_fixes.cjs tests/test_dom_dialog_fixes.cjs tests/test_import_confirm_fixes.cjs tests/test_settings_audit_fixes.cjs`：20/20，exit 0，506.019167ms。
- `test_import_ui.py` 27/27，exit 0，0.517s；`test_ui_layout.py` 19/19，exit 0，0.010s；`test_i18n.py` 14/14，exit 0，1.830s。所有模型传输均 mock。
- 五个 HTML 的实际内联脚本和六个修改的外部脚本通过 `vm.Script` 解析；`i18n_extract.py` 0/1416 缺项；`git diff --check` exit 0（最终补写证据之后还由集成复验）。Node 为现有 v23.11.0，不冒充支持的 Node LTS。

本次新增模型 token/费用为 0，无正式资料/密钥/账本变更。主代理最新原生新包确认、Cancel/Escape、冷重启、保存回执、Reader 焦点和暂停绘制路径仍需实际复验；这里的 VM 不关闭 B24/B26/B27 或全产品发布门槛。此前全量/构建绿在本补修之后已经过期。B29 原生 CmdQ 菜单绕过页面 quit hook 的新问题由主代理修 Rust 菜单，并独立记录，不在本补修中宣称修毕。

## B29 再补：创建页未提交草稿的显式退出（2026-10-08）

独立源码复审发现 `project_creation.html/project-creation.js` 原来没有 `PDHPrepareQuit/beforeunload`，而审阅区的手工学习图、五字段需求、正在编辑的概念、关键词、检索式、路径和候选选择只在内存。此发现是创建页的独立缺口，不能继承原 Route 页面 hook 的通过。

新增本地 `creation-quit.js` 和实际三选项 DOM dialog：默认“取消退出”，另有“返回审阅”和“放弃未提交修改并退出”。取消/Escape恢复原焦点，返回审阅选择可见且未禁用的编辑入口，三个选项有名称/说明、ARIA 错误状态和 Tab 循环。不发生模型调用、项目 finalize 或静默确认；明确放弃的是当前未提交窗口编辑，已经保存的引导草稿继续保留，界面明确说明。

实际适配器在退出时比较全部 input/textarea/select 当前值与创建页初始值，无需依赖 input 事件，因此直接原生/AX 写入也能识别。另读取 review 的 graph/briefDirty/editing/discarded/selection 状态、已建 guidance session、种子/关键词。处理中计数包含真实 API 的响应解析生命周期、原始 PDF 上传和 session DELETE；并叠加引导、地图生成/核对/搜索与种子队列状态。退出选择之后再次核对 busy；运行中不退出，错误 IPC 重新启用选项并保留所有字段/会话。空白页直接退出，重复退出只调用一次 IPC；已经明确成功创建后导航用 leaving 标记，避免浏览器卸载保护误拦该导航。

失败先行：`test_creation_quit_fixes.cjs` 初次 0/5，缺 helper 和真实退出状态函数；实现后 5/5，补实际 API pending 生命周期与 HTML 依赖/ARIA 后 7/7。最终同源执行：

- `node --test tests/test_creation_quit_fixes.cjs tests/test_dom_dialog_fixes.cjs tests/test_i18n.cjs tests/test_ai_scope_ui_fixes.cjs tests/test_route_quit_fixes.cjs`：52/52，exit 0，118.842917ms。
- `python3 -m unittest discover -s tests -p test_project_creation_ui.py -v`：19/19，exit 0，0.015s。
- `python3 scripts/i18n_extract.py`：0/1422；两份改动实际 JS 解析通过；`git diff --check` exit 0。

没有模型、正式账本/资料、Rust 或导入后端变更，没有运行构建/原生。主代理需要将新文件登记在同一 critical unit，并在自己的自定义 Quit 菜单新包中实际验证创建页 Cancel/Return/Discard、冷启和正在处理状态；旧 native/build 结果不覆盖本补修。源码已通知独立复审代理检查，不自行把独立审查标通过。

## B29 系统退出补修：Dock / AppleEvent 经过同一草稿确认（2026-10-08）

独立本地源码检查确认 pinned Tao 0.35.3 的 `TaoAppDelegateParent` 仅注册 `applicationWillTerminate:`，没有 `applicationShouldTerminate:`；其 willTerminate 调用 `AppState::exit()`，直接交付 `LoopDestroyed`。因此先前自定义 CmdQ 菜单和 Tauri `ExitRequested` 保护不能据此声称覆盖 Dock/system `terminate:`。这是来源源码确认的缺口；本代理没有操作 Dock，也没有把源码检查标为原生测量。[Apple 的退出生命周期说明](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/AppArchitecture/Tasks/GracefulAppTermination.html)说明系统退出先询问 delegate；没有该方法时，不会自动替应用检查未保存内容。

在主代理明确授权的窄范围中，只增补以下 native 行为：

- setup 主线程取得现有 NSApplication delegate，严格核对实际类名和整个继承链中该 selector 缺失；`class_addMethod` 只加缺失的 `applicationShouldTerminate:`。既有 delegate 对象、ivars、launch/openURL/reopen/willTerminate 等 callback 全部保留。未知 delegate/已有 selector/注册失败使启动拒绝继续，避免覆盖未来框架自己的退出策略。
- AppHandle 和由 `NSApplicationTerminateReply::ENCODING` 生成的 method signature 使用进程生命周期存储。给同一 retained delegate 重新 setDelegate，以使 AppKit 重新看到可选方法；没有代理替换或新 delegate。objc2-app-kit 的直接 feature 显式声明 `NSApplication` 与其 class 依赖 `NSResponder`，不依赖偶然 transitive feature union；该版本没有独立 `NSApplicationDelegate` feature。
- 未确认时 callback 同步返回 `TerminateCancel`，同时运行已有 `prepare_quit`；页面仍拥有取消/返回/明确放弃和草稿保存决策。没有 `TerminateLater` 挂起状态、补充 reply IPC 或默认批准。已获原有 `complete_quit` 的 origin 授权、`session.quitting=true` 后才允许 `TerminateNow`。callback 内状态读取/派发异常被捕获，异常不跨 Objective-C 边界，返回取消；handle 未注册也返回取消。
- `prepare_quit` 显示/聚焦窗口，让 Dock 退出请求的页面选择可见；eval 错误记录并保持打开。原有 `complete_quit → app.exit(0)` 和应用指令权限不变，不添加模型请求、IPC 命令或预算变化。

正常确认后的 pinned 生命周期经源码核对：Tauri 2.11.5 的 `app.exit` 向 tauri-runtime-wry 2.11.4 proxy 派发 `Message::RequestExit`，后者先交付 `ExitRequested`，ack 标记使原 guard 不再拦截，随后 `ControlFlow::Exit/LoopDestroyed → RunEvent::Exit`，应用原有 `PythonProcess.stop` 执行。`AppHandle.exit` 在 proxy 发送失败时另有 framework cleanup + `process::exit` 兜底，不能声称该异常也交付应用自己的 Exit callback。此补修不改该框架兜底，也不将正常源码路径替代后台子进程实际退出验收。

失败先行：新增两个真实 policy 测试初次编译 exit 101，四处 `native_termination_reply` 缺失；没有把编译失败当行为通过。实现后加入真实 callback 在 handle 未注册时的取消测试，不创建 NSApplication/窗口，不读取正式资料。

实际执行：

- `cargo test --manifest-path src-tauri/Cargo.toml native_quit_policy --offline`：最终 **3/3通过**，exit 0，编译/链接 2.25s，测试 0.00s；直接验证未确认取消且只派发一次、确认后不再派发、panic 后取消并可重试，以及真实 callback 未注册时保持打开。
- `cargo check --manifest-path src-tauri/Cargo.toml --offline`：显式 feature 声明后 exit 0，1.07s。没有新增 crate/version；没有全量测试、桌面构建、UI 操作或付费调用。
- 主代理的独立复审代理已收到 callback ABI、静态生命周期、delegate retain、Cancel/ack/cleanup 的具体复核请求；审查结论由独立代理登记，不能自行标通过。

**最终桌面构建、真实 Dock Quit/AppleEvent、CmdQ、关闭窗口、Cancel/Return/Discard、冷启和 Python 子进程终止仍需要主代理的新包验收**。未测试系统强制结束、macOS 注销/关机与强杀，不推定这些路径安全；旧 build/native 结果不覆盖本 Rust 修改。该项继续在同一 critical 工作单元，不提前关闭原生 gate。

## R-F31 英文系统说明与原始用户内容

独立审查先证明四条可复现路径：项目事实的固定创建模式/空关键词；学习前置 chip 的固定证据 title；导入失败/身份冲突及侧车错误；冷恢复的旧中文 scope_notice。八条另测 Route/周报数字句本来可译，未误报成缺陷。随后按实际 render/helper 修复，并增加真实 i18n MutationObserver transport 回归。

| 系统文字 | 修复路径及保护边界 |
|---|---|
| 画像有用/收藏/来源/公式/活动 | 固定枚举及统计分开渲染，来源预译；题名、项目名、词项、历史固定词和用户反馈理由保持原文。 |
| 项目创建方式与暂无关键词 | 固定 mode 及空占位允许翻译；实际关键词与用户名称仍保护。 |
| 学习前置与旧 scope_notice | 只预译已知证据枚举和完整程序说明，概念、目标、检索词、摘要/引文节选不翻译。 |
| 导入 failed、warning、seed failure、侧车及 RIS/CSL/BibTeX 错误 | 仅 typed system error 入口格式化已知错误框架；原始 bibliography key/未闭合片段保留；未知诊断保持原文，随后转义防 HTML 执行。 |
| Route/图库撤销 | 已存固定系统事件 label 在显示时译为当前语言；不转换数据中的类别名、用户 reason 或项目名。 |
| 图库用户字段/可访问标签 | 固定提示用命名槽原样插入用户值，明确禁止二次字典处理；题名、项目名、分类正文/tooltip/面包屑与选择框保持中文原文。 |

首批新画像 3/3 失败；另外五个已确认页面路径首轮均失败，图库又实证“收藏”题名/分类名变成 Save。修后 `test_system_i18n_fixes.cjs` **15/15**；相关 Node 合计 **191/191**（0 skip，235.6ms），包括既有画像/组织/周报/i18n/creation/reader policy/import confirmation/quit 回归。`PYTHONPATH=tests python3 -m unittest test_i18n test_import_ui test_project_creation_ui test_ui_layout -v` **79/79**（2.396s），无真实模型请求；提取器 **0/1427**，八个修改脚本解析通过。私有可重跑日志 `system-i18n-focused-final.log` / `system-i18n-python-final.log` 在同一单元 `.local/audit-fixes-20261008/logs/`。

既有 AI scope VM 原没有 window，新增实际中文 i18n 初始化后旧原文/转义断言仍通过；没有以 no-op 代替依赖。新回归明确按语言重载后重新 render，不宣称自动反译历史英文自由文本。测试 DOM transport 与真实函数执行不等于 WebKit/实际 macOS窗口；根代理的新包英文界面复验、全量与 build 仍需分别记录。此补修不修改 Rust/模型/服务/提示/配额，不触碰正式资料，无模型或网络开销。

原生导入回执文字补正：损坏 PDF 可能已通过 HTTP 送达本地服务，但校验拒绝且没有注册条目。`renderFailedUploads` 改述“未保存为导入条目（传输或校验失败）”，不再声称“未上传”。新增实际函数第 15 条回归先失败（旧英文 not uploaded），修后中英文通过，冷恢复失败文件名保持原文；持久回执与上传逻辑未改。相关最终 Node 191/191、Python 79/79 均以此新源重跑。
