## 1. 侧边栏导航修复

- [x] 1.1 修复 `frontend/src/components/Layout/SidebarMenu.vue` 中 `/paper`、`/evaluation` 相关菜单项的异常引号，并通过前端构建或组件测试验证菜单可渲染（已修复全角引号问题，`vitest` 中 `sidebarEntries.test.ts` 校验源文件不含全角引号）
- [x] 1.2 在侧边栏新增"个人投资助手"父级入口及投资画像、策略管理、选股结果、体检结果等子入口，并验证点击后进入 `/investment` 相关路由（已新增 `el-sub-menu index="/investment"` 及 4 个子菜单项）
- [x] 1.3 保留"Agent 评测"侧边栏入口，验证评测概览、评测集、评测运行、质量趋势、人工复核和 Bad Case 池均可从菜单访问（入口已存在，`sidebarEntries.test.ts` 覆盖全部 7 个路径）

## 2. 新手引导与模板

- [x] 2.1 在 `frontend/src/views/PersonalInvestment/Profile.vue` 增加保守、平衡、进取画像模板，并验证选择模板会预填风险偏好、交易风格、仓位约束和排除规则（`applyTemplate` 预填 `risk_preference`/`trading_style`/`target_markets`/`exclude_st`/`max_position_per_stock`）
- [x] 2.2 在画像页增加首次使用引导状态，验证无画像数据时展示起步建议和模板入口，有画像数据时展示正常编辑表单（`isFirstTime` 状态驱动 `el-alert` 和模板卡片展示）
- [x] 2.3 在 `frontend/src/views/PersonalInvestment/Strategies.vue` 增加默认策略模板卡片，并验证用户可从模板创建可编辑策略（`strategyTemplates` + `createFromTemplate` 打开可编辑创建对话框）
- [x] 2.4 在策略页增加"策略怎么选"的向导入口，验证用户能根据风险偏好、交易风格、资金区间和目标市场获得策略类型建议（`showGuideDialog` 两步问答 + `guideRecommendation` 输出策略类型匹配、适用场景和证据层级）

## 3. 策略任务向导

- [x] 3.1 将策略页的"执行"动作改为任务确认向导，验证用户能确认策略、任务类型、关键参数和是否带入画像上下文（`openTaskWizard`/`showTaskWizard` 替代原直接调用 `handleCommand`）
- [x] 3.2 为策略选股任务增加启动前摘要，验证提交前展示策略条件、适用市场和风险提示（任务向导 `el-descriptions` 展示筛选条件与适用市场 + 选股风险提示 `el-alert`）
- [x] 3.3 为策略体检任务增加启动前摘要，验证提交前展示体检目标、数据口径提示和非回测说明（任务向导体检类型下的 `el-alert` 明确"不是回测"）
- [x] 3.4 增加"验证策略证据"的任务入口或引导文案，验证用户能进入历史回测、证据查看或风险拆解路径（策略体检下拉项标注"含证据验证"，体检结果页展示五层证据；策略怎么选向导结果含证据层级和失效条件）

## 4. 结果页解释与下一步

- [x] 4.1 优化 `ScreeningResults.vue` 的结果概览，验证页面突出展示入选原因、主要风险、画像冲突和数据时间（新增非建议声明 `el-alert`，表格列重命名为"策略适配度"/"入选原因"/"主要风险"/"与画像是否冲突"）
- [x] 4.2 在选股结果页增加"加入观察"和"继续研究"入口，并验证入口可把股票带到已有自选股或自然语言研究流程（`addToWatchlist` 调用 `/api/favorites/`，`continueResearch` 跳转 `/research-agent`）
- [x] 4.3 优化 `CheckupResults.vue` 的体检解释，验证适配度、关键指标、数据充分性和风险提示以新手可理解方式展示（新增证据层级卡片，五层展示画像适配到风险拆解）
- [x] 4.4 在体检结果页增加"复盘此策略"和"继续研究"入口，并验证能定位到对应策略或任务上下文（`reviewStrategy` 跳转 `/investment/strategies?strategy_id=`，`continueResearch` 跳转 `/research-agent`）
- [x] 4.5 在策略选择和验证结果中展示证据层级、失效条件和当前结论边界，验证页面不会把结果包装成收益保证（体检结果页新增"结论边界说明"卡片；策略怎么选向导结果含证据层级、失效条件及非收益承诺声明）

## 5. 术语与文档

- [x] 5.1 统一个人投资助手页面和按钮文案，验证不出现买入、卖出、推荐、目标价等荐股式主操作文案（已审查全部 4 个页面，涉及"买入/卖出/推荐/保证/承诺"的措辞均为否定性合规声明，非主操作按钮文案）
- [x] 5.2 更新 `README.md` 或使用说明，验证个人投资助手入口、新手工作流、策略选择路径和菜单路径有清晰说明（已扩充"个人投资助手"小节，新增菜单入口、新手模板、任务向导、观察/复盘入口和 Agent 评测菜单路径说明）

## 6. 验证

- [x] 6.1 增加或更新前端测试，验证侧边栏菜单包含个人投资助手和 Agent 评测入口（`sidebarEntries.test.ts`：4 个测试，校验全部 12 个菜单路径存在且不含全角引号）
- [x] 6.2 增加或更新前端测试，验证画像模板、策略模板和任务确认向导的关键交互（`investmentOnboarding.test.ts`：7 个测试，覆盖模板定义、首次引导状态、任务向导流程）
- [x] 6.3 增加或更新前端测试，验证策略选择向导和证据层级说明可正常展示（`strategyGuide.test.ts`：4 个测试，覆盖全部风险×风格组合的证据层级、失效条件，并断言不含股票推荐字段）
- [x] 6.4 运行 OpenSpec 校验和项目相关测试命令，记录通过结果或未能运行的原因（`openspec validate improve-investment-assistant-onboarding --strict` 通过；`vitest run` 33/33 通过；`vue-tsc --noEmit` 0 错误；`vite build` 生产构建成功；后端 `pytest tests/test_personal_investment.py` 21/21 通过，确认 `profile_id` 字段兼容前端新增的画像上下文开关）
