# 提示词模版系统 - 架构图

## 🏗️ 系统整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层 (Frontend)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 模版选择组件  │  │ 模版编辑器   │  │ 模版预览     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        API层 (Backend)                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  GET /api/prompts/templates/{analyst_type}              │   │
│  │  GET /api/prompts/templates/{analyst_type}/{name}       │   │
│  │  POST /api/prompts/templates/{analyst_type}             │   │
│  │  PUT /api/prompts/templates/{analyst_type}/{name}       │   │
│  │  DELETE /api/prompts/templates/{analyst_type}/{name}    │   │
│  │  POST /api/prompts/templates/{analyst_type}/{name}/preview│  │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    模版管理层 (Manager)                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         PromptTemplateManager                            │   │
│  │  ├─ load_template()                                      │   │
│  │  ├─ list_templates()                                     │   │
│  │  ├─ save_custom_template()                               │   │
│  │  ├─ validate_template()                                  │   │
│  │  ├─ render_template()                                    │   │
│  │  └─ get_template_versions()                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    分析师集成层 (Analysts)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 基本面分析师  │  │ 市场分析师   │  │ 新闻分析师   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐                                               │
│  │ 社媒分析师   │                                               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    存储层 (Storage)                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  文件系统 (YAML)          数据库 (可选)                  │   │
│  │  prompts/templates/       PromptTemplateDB               │   │
│  │  ├─ fundamentals/         (自定义模版)                   │   │
│  │  ├─ market/                                              │   │
│  │  ├─ news/                                                │   │
│  │  └─ social/                                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 📊 数据流图

### 1. 加载模版流程

```
用户选择模版
    ↓
API: GET /api/prompts/templates/{analyst_type}/{name}
    ↓
PromptTemplateManager.load_template()
    ↓
检查缓存 ─→ 命中 ─→ 返回缓存
    ↓
    未命中
    ↓
读取YAML文件
    ↓
验证模版格式
    ↓
缓存模版
    ↓
返回模版
```

### 2. 执行分析流程

```
用户发起分析
    ↓
API: POST /api/analysis
    {
      "ticker": "000001",
      "analyst_templates": {
        "fundamentals": "conservative"
      }
    }
    ↓
加载选定的模版
    ↓
创建分析师实例
    (template_name="conservative")
    ↓
分析师节点执行
    ├─ 加载模版
    ├─ 渲染变量
    ├─ 组合提示词
    └─ 调用LLM
    ↓
返回分析结果
```

### 3. 创建自定义模版流程

```
用户编辑模版
    ↓
API: POST /api/prompts/templates/{analyst_type}
    {
      "name": "我的模版",
      "system_prompt": "...",
      ...
    }
    ↓
验证模版格式
    ↓
保存到数据库
    ↓
返回模版ID
    ↓
用户可选择使用
```

## 🔄 模版渲染流程

```
原始模版 (YAML)
    ↓
    system_prompt: "分析 {ticker} ({company_name})"
    ↓
PromptTemplateManager.render_template()
    ↓
    variables = {
      "ticker": "000001",
      "company_name": "平安银行"
    }
    ↓
渲染后的模版
    ↓
    system_prompt: "分析 000001 (平安银行)"
    ↓
注入到分析师提示词
```

## 📁 模版文件结构

```
prompts/
├── templates/
│   ├── fundamentals/
│   │   ├── default.yaml
│   │   │   ├─ version: "1.0"
│   │   │   ├─ analyst_type: "fundamentals"
│   │   │   ├─ name: "基本面分析 - 默认模版"
│   │   │   ├─ system_prompt: "..."
│   │   │   ├─ tool_guidance: "..."
│   │   │   ├─ analysis_requirements: "..."
│   │   │   ├─ output_format: "..."
│   │   │   └─ constraints: {...}
│   │   ├── conservative.yaml
│   │   └── aggressive.yaml
│   ├── market/
│   │   ├── default.yaml
│   │   ├── short_term.yaml
│   │   └── long_term.yaml
│   ├── news/
│   │   ├── default.yaml
│   │   ├── real_time.yaml
│   │   └── deep.yaml
│   └── social/
│       ├── default.yaml
│       ├── sentiment_focus.yaml
│       └── trend_focus.yaml
├── schema/
│   └── prompt_template_schema.json
└── README.md
```

## 🔌 分析师集成架构

```
create_fundamentals_analyst(llm, toolkit, template_name="default")
    ↓
    ┌─────────────────────────────────────┐
    │ PromptTemplateManager                │
    │ .load_template("fundamentals",       │
    │                "default")            │
    └─────────────────────────────────────┘
    ↓
    template = {
      "system_prompt": "...",
      "tool_guidance": "...",
      ...
    }
    ↓
    ┌─────────────────────────────────────┐
    │ fundamentals_analyst_node()          │
    │ ├─ 渲染模版变量                      │
    │ ├─ 组合提示词                        │
    │ ├─ 创建ChatPromptTemplate            │
    │ ├─ 调用LLM                           │
    │ └─ 返回分析结果                      │
    └─────────────────────────────────────┘
```

## 🌐 API端点架构

```
/api/prompts/
├── templates/
│   ├── {analyst_type}
│   │   ├── GET      → 列出所有模版
│   │   ├── POST     → 创建新模版
│   │   └── {name}
│   │       ├── GET      → 获取模版详情
│   │       ├── PUT      → 更新模版
│   │       ├── DELETE   → 删除模版
│   │       ├── preview
│   │       │   └── POST → 预览模版
│   │       └── versions
│   │           └── GET  → 获取版本历史
```

## 💾 缓存策略

```
PromptTemplateManager
    ↓
    cache = {
      "fundamentals:default": {...},
      "fundamentals:conservative": {...},
      "market:short_term": {...},
      ...
    }
    ↓
    加载模版时：
    1. 检查缓存
    2. 如果存在，返回缓存
    3. 如果不存在，读取文件
    4. 验证格式
    5. 存入缓存
    6. 返回模版
```

## 🔐 版本管理架构

```
prompts/
├── templates/
│   └── fundamentals/
│       └── default.yaml (当前版本)
└── .versions/
    ├── fundamentals_default_v1.0.yaml
    ├── fundamentals_default_v1.1.yaml
    └── fundamentals_default_v1.2.yaml

版本操作：
├─ get_versions() → 列出所有版本
├─ load_version(version="1.0") → 加载特定版本
└─ rollback(target_version="1.0") → 回滚到版本
```

## 📊 模版选择流程

```
用户界面
    ↓
选择分析师
    ↓
获取该分析师的所有模版
    GET /api/prompts/templates/{analyst_type}
    ↓
显示模版列表
    ├─ 默认模版 (推荐)
    ├─ 保守模版
    ├─ 激进模版
    └─ 自定义模版
    ↓
用户选择模版
    ↓
预览模版 (可选)
    POST /api/prompts/templates/{analyst_type}/{name}/preview
    ↓
确认选择
    ↓
发起分析
    POST /api/analysis
    {
      "analyst_templates": {
        "fundamentals": "conservative"
      }
    }
```

