# Investment Decision Chain Migration Design

将 TradingAgents 项目的投资决策链迁移到 finance-agent 项目，作为独立 Chat Agent 提供。

## 1. 决策摘要

| 决策项 | 选择 |
|--------|------|
| 迁移策略 | 适配融合（保留核心逻辑，适配到 finance-agent 基础设施） |
| 数据源 | 纯 yfinance |
| LLM | 双模型 + OpenRouter（deep: gpt-4.1, quick: gpt-4.1-mini） |
| 反思记忆 | V1 完整实现 BM25 |
| 集成方式 | 独立 Chat Agent，流式推送各阶段 |
| 项目位置 | `apps/api/src/agents/decision_chain/` |
| 实现方案 | LangGraph 原生复刻 |

## 2. 模块结构

```
apps/api/src/agents/decision_chain/
├── __init__.py                    # 导出 TradingDecisionChain
├── config.py                      # 决策链配置
├── state.py                       # AgentState, InvestDebateState, RiskDebateState
├── graph.py                       # 主编排器 TradingDecisionChain
├── propagation.py                  # 初始状态创建
├── conditional_logic.py            # 条件跳转逻辑
├── signal_processing.py            # 最终评级二次抽取
├── reflection.py                   # 反思记忆（BM25）
│
├── tools/
│   ├── __init__.py
│   ├── core_stock_tools.py         # get_stock_data
│   ├── technical_indicators_tools.py # get_indicators
│   ├── fundamental_data_tools.py   # get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
│   └── news_data_tools.py          # get_news, get_global_news, get_insider_transactions
│
├── agents/
│   ├── __init__.py
│   ├── analysts/
│   │   ├── __init__.py
│   │   ├── market_analyst.py
│   │   ├── social_media_analyst.py
│   │   ├── news_analyst.py
│   │   └── fundamentals_analyst.py
│   ├── researchers/
│   │   ├── __init__.py
│   │   ├── bull_researcher.py
│   │   └── bear_researcher.py
│   ├── managers/
│   │   ├── __init__.py
│   │   ├── research_manager.py
│   │   └── portfolio_manager.py
│   ├── trader/
│   │   ├── __init__.py
│   │   └── trader.py
│   └── risk_mgmt/
│       ├── __init__.py
│       ├── aggressive_debator.py
│       ├── conservative_debator.py
│       └── neutral_debator.py
│
└── utils/
    ├── __init__.py
    ├── memory.py                   # BM25 记忆体
    ├── agent_utils.py              # build_instrument_context, create_msg_delete, get_language_instruction
    └── agent_states.py             # TypedDict 定义（复用 LangGraph MessagesState）
```

## 3. 状态结构

严格遵循规格文档第4节，保持与原始系统等价。

### 3.1 顶层状态

```python
class AgentState(MessagesState):
    company_of_interest: str
    trade_date: str
    sender: str
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    investment_debate_state: InvestDebateState
    investment_plan: str
    trader_investment_plan: str
    risk_debate_state: RiskDebateState
    final_trade_decision: str
```

### 3.2 投资辩论子状态

```python
class InvestDebateState(TypedDict):
    bull_history: str
    bear_history: str
    history: str
    current_response: str
    judge_decision: str
    count: int
```

### 3.3 风险辩论子状态

```python
class RiskDebateState(TypedDict):
    aggressive_history: str
    conservative_history: str
    neutral_history: str
    history: str
    latest_speaker: str
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str
    count: int
```

### 3.4 初始状态

```python
{
    "messages": [("human", company_name)],
    "company_of_interest": company_name,
    "trade_date": str(trade_date),
    "investment_debate_state": {
        "bull_history": "",
        "bear_history": "",
        "history": "",
        "current_response": "",
        "judge_decision": "",
        "count": 0,
    },
    "risk_debate_state": {
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "history": "",
        "latest_speaker": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "judge_decision": "",
        "count": 0,
    },
    "market_report": "",
    "fundamentals_report": "",
    "sentiment_report": "",
    "news_report": "",
}
```

关键细节：
- 初始 messages 只有一个 human message，内容就是 ticker
- 四份 analyst report 初始为空字符串（不是 None）
- 两个 debate state 预先存在

## 4. 配置

```python
class DecisionChainConfig(BaseSettings):
    # LLM
    deep_think_llm: str = "openai/gpt-4.1"
    quick_think_llm: str = "openai/gpt-4.1-mini"
    
    # OpenRouter
    openrouter_api_key: str = ""  # 复用 settings.OPENROUTER_API_KEY
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Debate
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    max_recur_limit: int = 100
    
    # Data
    data_vendors: dict = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    tool_vendors: dict = {}
    
    # Output
    output_language: str = "Chinese"
    results_dir: str = "./decision_results"
```

模型分工：
- **quick_thinking_llm**（gpt-4.1-mini）：分析师、研究员、交易员、风险辩论、评级抽取
- **deep_thinking_llm**（gpt-4.1）：研究经理、组合经理

## 5. 图编排

### 5.1 完整流程

```
Start → Market Analyst → tools_market? → Market Analyst
      → Msg Clear Market → Social Analyst → tools_social? → Social Analyst
      → Msg Clear Social → News Analyst → tools_news? → News Analyst
      → Msg Clear News → Fundamentals Analyst → tools_fundamentals? → Fundamentals Analyst
      → Msg Clear Fundamentals → Bull Researcher ↔ Bear Researcher (轮转)
      → Research Manager → Trader
      → Aggressive Analyst → Conservative Analyst → Neutral Analyst (轮转)
      → Portfolio Manager → End
```

### 5.2 条件跳转逻辑

**分析师层**：
```python
if last_message.tool_calls:
    → 对应的 tools_* 节点
else:
    → Msg Clear → 下一个 Analyst
```

**多空论证**：
```python
if count >= 2 * max_debate_rounds:
    → Research Manager
elif current_response.startswith("Bull"):
    → Bear Researcher
else:
    → Bull Researcher
```

**风险辩论**：
```python
if count >= 3 * max_risk_discuss_rounds:
    → Portfolio Manager
elif latest_speaker.startswith("Aggressive"):
    → Conservative Analyst
elif latest_speaker.startswith("Conservative"):
    → Neutral Analyst
else:
    → Aggressive Analyst
```

### 5.3 工具边界

| 分析师 | 可用工具 |
|--------|----------|
| Market | `get_stock_data`, `get_indicators` |
| Social | `get_news` |
| News | `get_news`, `get_global_news`, `get_insider_transactions` |
| Fundamentals | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` |

### 5.4 评级二次抽取

Portfolio Manager 输出后，再调用一次 quick LLM 抽取标准评级词：
- 允许值：`BUY`, `OVERWEIGHT`, `HOLD`, `UNDERWEIGHT`, `SELL`
- 返回 `(final_state, extracted_rating)` 二元组

## 6. 反思记忆

### 6.1 五个独立记忆体

- `bull_memory` — Bull Researcher
- `bear_memory` — Bear Researcher
- `trader_memory` — Trader
- `invest_judge_memory` — Research Manager
- `portfolio_manager_memory` — Portfolio Manager

### 6.2 检索

每个节点执行时，从对应记忆体中 BM25 检索 `n_matches=2` 条最相似历史经验，注入 prompt。

### 6.3 写入

运行结束后，调用 `reflect_and_remember(returns_losses)` 对 5 个组件分别做反思：
1. 接收当前市场情境 + 该组件输出/辩论历史 + 最终收益/亏损数字
2. 反思 LLM 产出总结
3. 以 `(situation, recommendation)` 形式写入对应 BM25 memory

### 6.4 存储

使用 `rank_bm25` 库实现 BM25 检索。持久化存储在 SQLite 文件中，每个记忆体一个表。

路径：`{results_dir}/{memory_name}.db`

## 7. 流式输出

### 7.1 API 端点

```
POST /api/v1/decision-chain/run
```

请求体：
```json
{
    "ticker": "NVDA",
    "trade_date": "2026-01-15"
}
```

### 7.2 SSE 事件类型

| 事件类型 | 数据 |
|----------|------|
| `stage_start` | `{"stage": "market_analyst"}` |
| `stage_output` | `{"stage": "market_analyst", "content": "..."}` |
| `tool_call` | `{"tool": "get_stock_data", "args": {...}, "result": "..."}` |
| `debate_exchange` | `{"speaker": "Bull Analyst", "content": "..."}` |
| `final_decision` | `{"content": "...", "rating": "BUY"}` |
| `rating_extracted` | `{"rating": "BUY"}` |
| `stage_error` | `{"stage": "...", "error": "..."}` |

## 8. 隐含行为清单

以下行为必须严格保留：

1. **分析师多轮工具调用** — tool_calls 存在时继续循环，直到不再有 tool_calls
2. **消息清理** — 每位分析师完成后，清空 messages 并插入 `HumanMessage(content="Continue")`
3. **辩论硬轮次控制** — count 到阈值强制切换，不由模型决定何时结束
4. **Research Manager 同时写入 judge_decision 和 investment_plan**
5. **Trader 收尾语** — prompt 要求 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`
6. **评级二次抽取** — Portfolio Manager 全文后再走一次 quick LLM 抽取单词评级
7. **ticker 保真** — 交易所后缀在整个链路中不能被修改

## 9. 语言策略

- Analyst 和 Portfolio Manager 的 prompt 末尾追加 `Write your entire response in Chinese.`
- 内部辩论节点（Bull/Bear、风险三分析师）保留英文，稳定推理质量
- 默认 `output_language = "Chinese"`

## 10. 日志与产物

每次运行完成后保存完整状态到：
```
{results_dir}/{ticker}/decision_chain_logs/full_states_log_{trade_date}.json
```

包含字段：`company_of_interest`, `trade_date`, `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, `investment_debate_state`, `trader_investment_decision`（日志命名）, `risk_debate_state`, `investment_plan`, `final_trade_decision`

**注意命名差异**：状态字段叫 `trader_investment_plan`，日志字段叫 `trader_investment_decision`。

## 11. 新增依赖

```
langgraph>=0.2
langchain-core>=0.3
langchain-openai>=0.2
rank_bm25>=0.2
yfinance>=0.2
```

这些依赖添加到 `apps/api/pyproject.toml`。

## 12. 与现有系统的关系

- 决策链作为独立 Chat Agent 运行，不替换现有的 screener → scorer → pipeline 量化筛选流程
- 用户通过 `/api/v1/decision-chain/run` 发起请求
- 决策链使用 yfinance 获取数据（不受 JQData/TuShare 影响）
- LLM 调用通过 OpenRouter，复用 `settings.OPENROUTER_API_KEY`

## 13. 验收标准

1. 相同 ticker 和日期输入下，执行顺序仍然是 analyst 串行 → bull/bear → research manager → trader → aggressive/conservative/neutral → portfolio manager
2. analyst 节点仍然通过 `tool_calls` 判定是否继续
3. analyst 完成后会清空消息并插入 `"Continue"` 占位消息
4. `investment_debate_state["count"]` 每次 bull 或 bear 发言都加一
5. `risk_debate_state["count"]` 每次风险分析师发言都加一
6. Research Manager 的输出同时写入 `judge_decision` 和 `investment_plan`
7. Portfolio Manager 的输出包含五档评级之一，写入 `final_trade_decision`
8. 主方法返回 `(final_state, extracted_rating)` 二元组
9. 抽取评级仍是二次 LLM 调用，而不是正则
10. 相似历史经验检索使用 BM25，而不是 embedding
11. SSE 流式推送各阶段输出正常工作
12. 日志文件完整保存所有状态字段