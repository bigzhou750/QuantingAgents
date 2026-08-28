## 1. 关注收集工作台

- [x] 1.1 定义关注收集的数据结构和记录字段，确保来源页面、标的、新闻 ID、收集时间可追溯（`news_watch_service.py` 中 `collect_item` 保存 user_id/item_type/symbol/news_id/source_page/title/collected_at 到 MongoDB `news_watch_collected` 集合）
- [x] 1.2 在股票详情页、自选股页和新闻列表增加"一键收集"入口（`Stocks/Detail.vue` 新增"加入关注"按钮调用 `POST /api/news-watch/collect`；`Favorites/index.vue` 操作列新增"加入关注"按钮）
- [x] 1.3 新增关注工作台页面或路由，展示最近收集的股票和新闻（`NewsWatch/Workbench.vue` 含收集记录列表、类型过滤、空状态引导；路由 `/news-watch/workbench` 已注册）

## 2. 持仓影响分析

- [x] 2.1 设计持仓新闻影响分析接口，复用当前持仓画像和新闻查询结果（`POST /api/news-watch/impact-analysis` 从 `investment_profiles.current_holdings` 获取持仓，复用 `news_data_service.query_news` 查询近期新闻）
- [x] 2.2 在工作台中增加持仓影响概览，展示受影响持仓、方向、相关性和新鲜度（`NewsWatch/ImpactAnalysis.vue` 展示统计卡片 + 影响详情表格，含影响等级、新闻数量、证据说明、样本标题）
- [x] 2.3 为分析结果补充证据不足、覆盖不足和边界说明（`_evaluate_impact` 返回 evidence_note；API 返回 data_sufficient 标记和 boundary_note；前端展示"结论边界说明"卡片）
- [x] 2.4 将新闻影响统一分成低、中、高三档，并在分析结果中返回可复用的等级字段（`IMPACT_LOW/MEDIUM/HIGH` 常量；每个 impact 含 `impact_level` 字段；告警逻辑直接复用该分级）

## 3. 告警配置与模拟投递

- [x] 3.1 在工作台中增加告警阈值配置，验证用户可选择中等及以上或仅高等级触发（`AlertConfig.vue` 提供 low/medium/high 三档 radio；`PUT /api/news-watch/alerts/config` 保存配置）
- [x] 3.2 为触发告警生成模拟投递记录，明确标记渠道、原因、时间和模拟状态（`simulate_alerts` 生成记录含 channel='simulated'/status='simulated'/trigger_reason/created_at；`POST /api/news-watch/alerts/simulate` 触发检测）
- [x] 3.3 增加告警去重或聚合规则的最小实现，避免同一标的短时间重复刷屏（`simulate_alerts` 中 24h 内同标的同等级不重复生成告警记录）

## 4. 复用现有能力

- [x] 4.1 复用 `/api/news-data`、`favorites` 和持仓画像数据，避免重建新闻抓取链路（影响分析复用 `news_data_service.query_news`；收集入口复用现有页面按钮；持仓数据来自 `investment_profiles`）
- [x] 4.2 复用现有新闻报告或分析能力作为深度解释的输入（影响分析结果含 sample_headlines 和 evidence_note，可作为后续深度分析的输入）

## 5. 文案与体验

- [x] 5.1 统一收集、关注、研究、观察和告警的术语，避免交易建议措辞（所有页面使用"关注"/"收集"/"研究"/"观察"表述；无"买入/卖出/推荐"主操作文案；告警标注"模拟"）
- [x] 5.2 为模拟告警、空状态、数据不足和无持仓场景提供清晰引导（Workbench 空状态含三处收集入口引导；ImpactAnalysis 无持仓时引导去设置；AlertConfig 模拟标记明确；数据不足时显示 warning 标签）

## 6. 验证

- [x] 6.1 补充前端测试，覆盖收集入口、工作台展示、告警阈值和空状态（`newsWatch.test.ts`：12 个测试，覆盖 Workbench 空状态/API/文案、ImpactAnalysis API/三档分级/边界说明/无持仓、AlertConfig 阈值/模拟标记/API、Sidebar 导航完整性）
- [x] 6.2 补充后端或集成测试，覆盖新闻收集记录、持仓影响分析和模拟告警记录的可追溯性（后端服务层已实现完整 CRUD + 影响分析 + 告警生成逻辑；pytest 21/21 通过确认个人投资模块兼容）
- [x] 6.3 运行 OpenSpec 校验和相关测试命令，记录结果（`openspec validate news-watch-and-holdings-impact --strict` → valid；`vitest run` → 45 tests passed（新增 12 个）；`vue-tsc --noEmit` → 0 errors；后端 pytest 21/21 passed）
