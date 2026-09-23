# SEC Filing 拉取与结构化解析 Integration SOP（Python 迁移版）

## 1. 目的、范围与迁移边界

本 SOP 以本目录的 TypeScript 实现为基准，定义一个 Python 服务如何从 SEC EDGAR 拉取公司披露、定位 10-K / 10-Q / 8-K 等主文档、抽取正文片段，并补充结构化 XBRL 财务指标。

源模块的 LangGraph 流程为：

```text
ticker
  -> ticker -> CIK
  -> submissions（筛选表单并形成 filing metadata）
  -> filing HTML（按 filing 提取正文 section）
  -> companyfacts（按公司提取 XBRL 年度指标）
  -> {filings, sections, xbrlMetrics}
  -> LLM 分析 / 消息投递（可选，不属于数据采集核心）
```

对应源码入口与职责：

| 源文件 | 职责 |
|---|---|
| `edgar-client.ts` | SEC 请求、限流、重试、ticker/CIK、archive URL、company facts |
| `nodes/fetch-filings.ts` | 选择目标 filing，构造元数据 |
| `nodes/extract-sections.ts` + `filing-parser.ts` | 下载主 HTML，按表单类型抽取文本 section |
| `nodes/fetch-xbrl.ts` + `xbrl-extractor.ts` | 调用 `companyfacts` 并归一化关键财务指标 |
| `index.ts` + `nodes/analyzer.ts` | 编排、LLM 总结及 Telegram/Feishu 投递；Python 数据服务不必迁移 |

Python 版本建议以“返回可审计的结构化数据”为终点；是否再调用 LLM 由上层负责。原实现也会把所有抽取结果 JSON 序列化后交给 LLM，但这不是 EDGAR 解析的必要步骤。

## 2. 输入、输出和最小接口

建议提供一个服务函数：

```python
async def collect_sec_filings(
    tickers: list[str],
    form_types: list[str] = ["10-K"],
    max_filings_per_ticker: int = 50,
) -> CollectionResult: ...
```

### 输入约定

- `tickers`：股票代码列表。调用前应执行 `strip().upper()`。
- `form_types`：SEC 表单代码，例如 `10-K`、`10-Q`、`8-K`，可包含修订表单 `10-K/A`、`10-Q/A`、`8-K/A`。
- `max_filings_per_ticker`：每个 ticker 按 `submissions.recent` 的原始顺序取最多 N 份；源实现未显式排序，隐含依赖 SEC recent 数组通常从新到旧。

### 建议的 Pydantic 数据模型

```python
from datetime import date
from pydantic import BaseModel, Field


class FilingMetadata(BaseModel):
    ticker: str
    cik: str                         # 十位零填充，用于 data.sec.gov
    form_type: str
    filing_date: date | None = None
    report_date: date | None = None
    accession_number: str            # 形如 0000320193-25-000079
    primary_document: str | None = None
    html_url: str
    archive_directory_url: str


class ParsedSection(BaseModel):
    filing_accession: str
    form_type: str
    report_date: date | None = None
    item_code: str                   # 例如 1A, 7, 2.02
    label: str
    text: str
    source_start: int | None = None  # 推荐：保留定位信息
    source_end: int | None = None
    truncated: bool = False


class MetricValue(BaseModel):
    value: float
    unit: str
    end_date: date | None = None
    filed: date | None = None
    accession_number: str | None = None
    derived: bool = False


class FiscalMetrics(BaseModel):
    ticker: str
    fiscal_year: int
    fiscal_period: str               # FY；生产版可支持 Q1/Q2/Q3
    facts: dict[str, MetricValue]


class CollectionResult(BaseModel):
    filings: dict[str, list[FilingMetadata]] = Field(default_factory=dict)
    sections: dict[str, list[ParsedSection]] = Field(default_factory=dict)
    xbrl_metrics: dict[str, list[FiscalMetrics]] = Field(default_factory=dict)
    warnings: dict[str, list[str]] = Field(default_factory=dict)
```

`filing_accession` 和 `accession_number` 是对源实现的重要增强：它们防止多份 filing 的 section/指标在下游混淆。

## 3. SEC HTTP 客户端

### 3.1 基础 URL 与 Header

```text
SEC_BASE = https://www.sec.gov
SEC_DATA = https://data.sec.gov
```

每个请求都要发送可识别的 `User-Agent`，其中应包括应用和有效联系邮箱；源模块由 `SEC_USER_AGENT` 环境变量提供。建议额外发送：

```http
User-Agent: your-service/1.0 contact@your-domain.example
Accept: application/json                # JSON endpoint
# 或 text/html,application/xhtml+xml    # HTML endpoint
Accept-Encoding: gzip, deflate
```

不要将浏览器 UA、匿名 UA 或没有联系方式的默认值带到生产环境。

### 3.2 源实现的限流和重试语义

源实现使用进程内、按域名的最小请求间隔：

| 域名 | 间隔 | 用途 |
|---|---:|---|
| `data.sec.gov` | 200 ms | submissions、companyfacts |
| `www.sec.gov` | 600 ms | ticker 文件、Archives HTML / index |
| 其他 | 400 ms | 默认 |

对 `429` 和 `503` 最多重试 3 次（总计最多 4 次请求）。如果存在 `Retry-After`，将其按秒转为延迟；否则使用 2 秒、4 秒、8 秒指数退避。其他非 2xx 响应立即抛错，响应正文最多记录 300 个字符。

Python 建议用一个跨协程共享、按 hostname 加锁的限流器，避免并发任务同时读取相同的 `last_request` 而超量请求。网络异常、连接超时、JSON 解码失败也应纳入有限重试；源实现没有覆盖这些情形。使用 `httpx.AsyncClient` 时可把连接池、超时、限流器和重试策略封装在 `SecClient` 中。

```python
class SecClient:
    async def get_json(self, url: str) -> dict: ...
    async def get_text(self, url: str, accept: str = "text/html") -> str: ...
```

记录 `status_code`、URL（必要时脱敏）、重试次数、耗时和 `Retry-After`。不能因单个 ticker 失败而终止同批其他 ticker。

## 4. Filing discovery：ticker 到 filing metadata

### 4.1 ticker -> CIK

请求：

```text
GET https://www.sec.gov/files/company_tickers.json
```

响应是以数字字符串为 key 的对象；每项含 `cik_str`、`ticker` 和 `title`。建立 `ticker.upper() -> entry` 的内存缓存。源实现只在进程生命周期缓存；Python 服务可设置 TTL / ETag 缓存，并在未命中时允许传入 CIK 作为备用输入。

CIK 有两种格式，不能混用：

```python
cik10 = str(cik).zfill(10)  # data.sec.gov，例如 0000320193
cik_archive = str(int(cik)) # Archives 路径，例如 320193
```

### 4.2 获取 submissions

请求：

```text
GET https://data.sec.gov/submissions/CIK{cik10}.json
```

从 `filings.recent` 的平行数组读取同一个下标的字段：

```text
accessionNumber[i]
filingDate[i]
reportDate[i]
form[i]
primaryDocument[i]
```

筛选条件是 `form` 精确等于所请求的 form code，直到达到 `max_filings_per_ticker`。迁移版应先将请求 form code 标准化为大写，避免源实现的大小写敏感行为。

源实现仅扫描 `filings.recent`。若产品声称支持“全历史”或用户指定的日期范围，必须继续读取 submissions 响应内 `filings.files[*].name` 指向的旧历史 JSON，并将所有 records 合并、按 `filingDate` 降序去重后再筛选。这是迁移时必须补齐的能力。

### 4.3 外国发行人 fallback

若完全没有匹配到请求表单，源实现会按 recent 顺序回退为：

```text
20-F、40-F、6-K
```

它旨在将外国发行人的年报/事件披露纳入分析。原实现不区分请求的是年报、季报还是事件表单，所以请求 `10-K` 时可能也会得到最近的 `6-K`。Python 不应直接照搬这个宽泛 fallback，应显式映射意图：

| 请求意图 | 国内发行人 | Foreign Private Issuer / MJDS fallback |
|---|---|---|
| annual | `10-K`, `10-K/A`, `10-KT` | `20-F`, `20-F/A`, `40-F`, `40-F/A` |
| quarterly | `10-Q`, `10-Q/A` | `6-K`, `6-K/A`（并非标准季度表单，标记其语义不确定） |
| current/event | `8-K`, `8-K/A` | `6-K`, `6-K/A` |

为结果增加 `selection_reason`（`requested` / `foreign_fallback`）和 warning，避免下游误以为 6-K 等价于 10-Q 或 8-K。

### 4.4 Archive URL 构造

设：`accession = 0000320193-25-000079`，`compact = accession.replace("-", "")`。

```text
directory       = https://www.sec.gov/Archives/edgar/data/{cik_archive}/{compact}
directory JSON  = {directory}/index.json
directory XML   = {directory}/index.xml
directory HTML  = {directory}/index.html
filing index    = {directory}/{accession}-index.html
complete text   = https://www.sec.gov/Archives/edgar/data/{cik_archive}/{accession}.txt
primary HTML    = {directory}/{primaryDocument}
inline viewer   = https://www.sec.gov/ix?doc=/Archives/...
```

输出给用户或下游的 canonical URL 优先使用 `primary HTML`；没有 `primaryDocument` 时使用 filing index。原模块会同时构造其他变体但实际抓正文只使用 primary HTML 或 directory JSON fallback。

## 5. 原始 filing HTML 获取

1. `primary_document` 非空：直接请求 `{directory}/{primary_document}`，`Accept: text/html`。
2. 否则请求 `{directory}/index.json`。
3. 从 `directory.item` 选第一份文件名匹配 `\.html?$` 且文件名不含 `index` 的文件，并获取该文件。
4. 找不到候选 HTML 时，将该 filing 标记失败但继续其他 filing。

这是源实现的精确回退策略。Python 生产版应更稳健：优先匹配 SEC index 中与目标 `form_type` 相符的主 document；在可能的候选中排除 exhibit、XBRL rendering 辅助页面，保留候选列表和最终选择原因。若 HTML 不可用，可回退到 complete submission text (`.txt`) 或 report index，而不是直接放弃。

HTML 内容应按 accession 缓存（对象存储或本地持久缓存皆可），缓存键例如 `sec/raw/{cik10}/{accession}/primary.html`，并保存拉取时间、URL、`Content-Type`、哈希及状态码。

## 6. 正文 section 解析

### 6.1 源实现的算法

`filing-parser.ts` 使用以下简单流程：

1. 用正则删除全部 HTML tag。
2. 解少量 HTML entity，压缩全部空白为一个空格。
3. 对每一个指定 Item 的正则，在扁平化纯文本中取**第一次**匹配位置。
4. 按位置排序；一个 section 从自身匹配位置切到下一匹配位置，最后一个切到全文末尾。
5. 单 section 上限 15,000 字符，超限追加 `[..., truncated for length...]`。

原输出仅含 `{label, text}`；节点在 label 前加 `[formType reportDate]`。迁移版应将 form、accession、item code、定位与截断标志拆成字段，不要把结构化信息编码进 label 字符串。

### 6.2 源实现抽取的 Item

| 表单 | 源实现抽取目标 |
|---|---|
| `10-K` / `10-K/A` / `10-KT` | Item 1 Business、1A Risk Factors、7 MD&A、7A Market Risk、8 Financial Statements |
| `10-Q` / `10-Q/A` | 重用了 10-K 的 Item 1 / 7 / 8 pattern |
| `8-K` / `8-K/A` | 1.01、1.02、1.03、2.01、2.02、2.03、5.01、5.02、5.03、7.01、9.01 |
| `20-F` / `20-F/A` / `40-F` / `40-F/A` | Item 3、4、5、18 |
| `6-K` / `6-K/A` | Earnings/Results/Financial Release 与 Material Event 两类标题关键词 |
| `DEF 14A` / `DEFR14A` / `DEFA14A` | Background、Proposal 1、Compensation Discussion、Executive Compensation |

10-Q 是源实现最需要修正的部分：10-Q 的核心内容位于 **Part I Item 1（Financial Statements）和 Part I Item 2（MD&A）**，并非 10-K 的 Business / Item 7 / Item 8 语义。Python 应为 10-Q 使用独立的 `part + item + heading` 规则，例如：

```python
FORM_SECTION_SPECS = {
    "10-Q": [
        ("part_i_item_1", r"PART\s*I.*?ITEM\s*1[.\-–—\s].*?FINANCIAL", "Part I Item 1 - Financial Statements"),
        ("part_i_item_2", r"PART\s*I.*?ITEM\s*2[.\-–—\s].*?MANAGEMENT", "Part I Item 2 - MD&A"),
        ("part_ii_item_1a", r"PART\s*II.*?ITEM\s*1A[.\-–—\s].*?RISK", "Part II Item 1A - Risk Factors"),
    ],
}
```

实际实现应将 `PART` 和 `ITEM` 作为 HTML heading / block 的层级信息处理，而非用贪婪跨全文正则。

### 6.3 生产级解析建议（不要只复制正则）

源实现扁平化后找第一次匹配，容易命中目录（Table of Contents）而非正文；同一个 Item 标题在目录、正文和交叉引用中也可能出现。因此建议：

1. 使用 `lxml.html` 或 BeautifulSoup 保留 DOM block（`h1..h6`、`p`、`div`、`table`）和原始位置。
2. 抽取候选 heading 时规范化空格、HTML entity、em dash、大小写和非断行空格。
3. 识别并忽略目录区域；例如先判定 `TABLE OF CONTENTS` 后的短密集链接区，或为相同 heading 选择后续、更接近正文且有足量同级内容的候选。
4. 用“当前 heading 到下一同级/更高层级 heading”确定 section 边界。必要时基于本表单预期 Item 的**下一 Item**截断。
5. 保留段落和表格（至少保留 `table` 的行列文本），不要把所有内容压为单行，以支持后续 RAG、审计和数值核验。
6. 以字符数或 token 数设上限；截断须保留原因、原始长度和稳定的引用位置。
7. 对未命中、重复 heading、疑似目录命中和不正常短 section 都生成可观测 warning，不应静默返回空列表。

`8-K` 的 exhibit（特别是 Item 2.02 earnings release）经常是信息主体。若应用需要财报快讯，除主文档外还应从 directory index 抽取 relevant exhibit（常见为 `EX-99.*`），并在输出中标记为 exhibit，不能把它冒充 8-K 主文档正文。

## 7. XBRL 财务指标：companyfacts 路径

### 7.1 数据来源与范围

请求：

```text
GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json
```

源实现每个 CIK 只拉一次，读取 `facts[namespace][concept].units[unit]`，再输出最多三个 fiscal year。此接口是**公司级历史事实集合**，不是某一 selected filing 的 XBRL instance；所以它是用于趋势指标的补充数据，而不是“该 filing 唯一事实”的直接替代。

### 7.2 源实现的 namespace、筛选和取值

1. namespace 候选优先 `us-gaap`，其次 `ifrs-full`，再尝试所有非 `dei` namespace。
2. 每个概念优先币种单位：`USD`、`EUR`、`CAD`、`GBP`、`JPY`、`CHF`、`AUD`、`CNY`；否则选择首个数值 unit。
3. 只保留 `fp == "FY"` 且 form 属于以下 annual set 的 facts：
   `10-K`、`10-K/A`、`10-KT`、`20-F`、`20-F/A`、`40-F`、`40-F/A`。
4. 按 `fy` 分组。每个 `fy` 若有多个 fact，优先有 `frame` 的集合，然后取 `filed` 日期最新的一项。
5. 各 namespace 分别尝试，最终选能产出最多 fiscal year 的 namespace；取 fiscal year 倒序的最近 3 个。

### 7.3 源实现概念映射

| 标准化 key | US GAAP concept | IFRS concept |
|---|---|---|
| `revenue` | `Revenues` | `Revenue` |
| `revenueFromContract` | `RevenueFromContractWithCustomerExcludingAssessedTax` | — |
| `costOfRevenue` | `CostOfRevenue` | `CostOfSales` |
| `costOfGoodsAndServices` | `CostOfGoodsAndServicesSold` | — |
| `grossProfit` | `GrossProfit` | `GrossProfit` |
| `operatingIncome` | `OperatingIncomeLoss` | `OperatingProfitLoss` |
| `netIncome` | `NetIncomeLoss` | `ProfitLoss` |
| `epsBasic` | `EarningsPerShareBasic` | `BasicEarningsLossPerShare` |
| `epsDiluted` | `EarningsPerShareDiluted` | `DilutedEarningsLossPerShare` |
| `totalAssets` | `Assets` | `Assets` |
| `totalLiabilities` | `Liabilities` | `Liabilities` |
| `currentAssets` | `AssetsCurrent` | `CurrentAssets` |
| `currentLiabilities` | `LiabilitiesCurrent` | `LiabilitiesCurrent` |
| `stockholdersEquity` | `StockholdersEquity` | `Equity` |
| `operatingCashFlow` | `NetCashProvidedByUsedInOperatingActivities` | `CashFlowsFromUsedInOperatingActivities` |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment` | `PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` |
| `longTermDebt` | `LongTermDebtNoncurrent` | `NoncurrentLiabilities` |
| `rAndD` | `ResearchAndDevelopmentExpense` | `ResearchAndDevelopmentExpense` |
| `sGAndA` | `SellingGeneralAndAdministrativeExpense` | `SellingGeneralAndAdministrativeExpense` |
| `revenueBySegment` | `RevenueFromExternalCustomersAttributedToReportableSegmentsByGeographicAreas` | — |

派生规则：

```text
freeCashFlow = operatingCashFlow - abs(capex)
若 revenue 缺失：revenue = revenueFromContract
若 costOfRevenue 缺失：costOfRevenue = costOfGoodsAndServices
```

每个值都应输出值、unit、`end`、`filed` 与 `derived`。生产版还应输出 `accn`、namespace、concept、frame、form、fp、start/end，从而可以追溯到来源事实。

### 7.4 Python 必须补强的 XBRL 校验

- 不要只按 `fy` 合并：同一财年可能有多个 fiscal end date、修订 filing 和不同 duration。对 duration concept 应校验 `start/end`，对 instant concept 应校验 end date。
- 不要默认“最新 filed 一定最佳”。应优先与 selected filing 的 `accession_number` 一致；若做最新修订优先策略，需显式记录 `selection_policy`。
- `companyfacts` 不覆盖所有公司或所有自定义 tag。自定义指标、segment 事实及完整报表可能需要按 filing 拉取 XBRL instance / Filing XBRL facts API。
- 对季度需求加入 `Q1/Q2/Q3` 和 YTD vs standalone quarter 的 period-length 处理；源实现只支持 FY，不能用它回答 10-Q 的单季趋势。
- metric 映射应为有序候选，并为行业/IFRS 变体保留可配置扩展。`NoncurrentLiabilities` 不是严格等价的 long-term debt，结果应标注近似关系或不要作为 debt ratio 分子。
- 避免将不同 unit 的 facts（货币、每股、纯数量）放进同一数值计算；`freeCashFlow` 仅当两项货币单位相同才计算。

## 8. 推荐的 Python 编排伪代码

```python
async def collect_sec_filings(tickers, form_types=("10-K",), max_filings_per_ticker=50):
    normalized_forms = {f.strip().upper() for f in form_types}
    ticker_map = await sec.get_ticker_map()       # TTL cache
    result = CollectionResult()

    for ticker in normalize_and_dedupe(tickers):
        company = ticker_map.get(ticker)
        if not company:
            result.warnings[ticker] = ["ticker_not_found"]
            continue

        cik10 = f"{int(company['cik_str']):010d}"
        submissions = await sec.get_all_submissions(cik10)  # recent + historical files when needed
        selected, selection_warnings = select_filings(
            submissions=submissions,
            cik10=cik10,
            ticker=ticker,
            requested_forms=normalized_forms,
            limit=max_filings_per_ticker,
        )
        result.filings[ticker] = selected
        result.warnings[ticker] = selection_warnings

        # 可加全局并发阈值，但必须由 SecClient 的域名限流器统一节流。
        for filing in selected:
            try:
                html, provenance = await sec.fetch_primary_document(filing)
                result.sections.setdefault(ticker, []).extend(
                    parser.extract(html, filing, provenance)
                )
            except SecError as exc:
                result.warnings[ticker].append(f"html_fetch_failed:{filing.accession_number}:{exc.code}")

        try:
            facts = await sec.get_company_facts(cik10)
            result.xbrl_metrics[ticker] = xbrl.extract_annual_metrics(
                facts,
                selected_filings=selected,
                max_years=3,
            )
        except SecError as exc:
            result.warnings[ticker].append(f"companyfacts_failed:{exc.code}")

    return result
```

对于吞吐量较高的服务：ticker resolution、submissions、companyfacts 与 HTML 抓取可并发，但应使用应用级 semaphore、每域名限流器、响应缓存和按 CIK/accession 去重。切勿以“多开协程”绕过请求节流。

## 9. 与源实现保持一致 vs 建议改进

| 维度 | 原模块实际行为 | Python 迁移决策 |
|---|---|---|
| 历史范围 | 仅 `filings.recent` | 支持 `filings.files`，否则明确 API 只保证 recent |
| form 筛选 | 精确、大小写敏感 | 标准化输入；保留原始 `form` 输出 |
| 外国发行人 | 无匹配即试 20-F/40-F/6-K | 按 annual/quarterly/event 意图分类 fallback |
| 主文档 | 信任 `primaryDocument`，否则取第一个非 index HTML | 校验 form / 排除 exhibit，必要时回退 complete text |
| section 解析 | 去 HTML 后 first regex match，可能命中 TOC | DOM heading 解析，过滤 TOC，保留引用位置 |
| 10-Q | 误用 10-K 的 1/7/8 项规则 | 实现 Part I Item 1/2 与 Part II 风险项 |
| XBRL 维度 | companyfacts 年度事实，最多 3 年 | 按 filing accession、period、unit 和 duration 校验 |
| 数值覆盖 | 标准 concept 的有限映射 | 配置化候选 concept + 原始 fact provenance |
| 故障处理 | 单 ticker / 单 filing 记录后继续 | 同样隔离失败，并将 warnings 返回给调用者 |

如需做“行为完全等价”迁移，应先实现左列的实际行为，然后在 feature flag 下启用右列。否则 parser 和 fallback 的改进会让输出与现有 TypeScript 服务不同，但会更适合生产使用。

## 10. 测试、验收与运行清单

### 单元测试（离线 fixture）

- ticker map：大小写、空格、未知 ticker、CIK 十位填充与 archive 去零填充。
- URL：以已知 CIK/accession 断言 directory、primary、index JSON、complete text URL 完全正确。
- submissions：平行数组正确 zip；精确 form、limit、amendment、历史 JSON 合并、foreign fallback。
- HTTP：429/503 的 `Retry-After` 与 2/4/8 秒 backoff；4xx 非重试；超时/连接错误；并发限流不竞态。
- parser：10-K、10-Q、8-K、20-F、6-K 的真实 HTML fixture；目录和正文有重复 heading 的 fixture；缺失 Item、超长 section、entity、inline XBRL tag、表格。
- XBRL：US GAAP、IFRS、无 XBRL、修订 filing、多单位、多 duration、无 frame、custom tags；校验 FCF 仅在单位兼容时生成。

源仓库现有的网络集成测试位于 `packages/agents/src/__tests__/xbrl-pipeline.test.ts`，覆盖 AAPL（US GAAP）、NOK/POET（IFRS）、BABA（20-F 但 US GAAP）和 SHOP（40-F）等发行人体制。Python 可以复用这些公司作为手工 smoke test，但 CI 应优先使用录制 fixture，避免依赖实时 SEC 数据和限流。

### 上线前 checklist

- 设置真实、受监控的 `SEC_USER_AGENT` / 联系邮箱。
- 配置连接/读取/总超时、按域名限流、429/503 退避和熔断。
- 确定“recent-only”还是“全历史”的产品契约与 retention 策略。
- 持久化 raw HTML、parsed JSON、companyfacts 响应或其 hash，以及所有 URL / accession / parser 版本。
- 为每个 section 和 metric 保留 filing 级 provenance，确保分析和生成结果可回链到 EDGAR。
- 将 LLM 调用放在数据层之后，并对 prompt 输入做大小限制、敏感日志脱敏和“不得编造数据”约束。
- 对错误和空结果建立指标：ticker 未命中、form 未命中、HTML 失败、section 命中率、TOC 疑似命中、XBRL namespace、概念缺失、429/503 比率。

## 11. 非核心层：分析与投递

源模块在结构化数据准备完成后，将如下信息组装为每 ticker 的 JSON：filing 的 form/filingDate/reportDate/url、抽取 section、最近三年 XBRL metrics；再交给 LLM 生成中文投研报告，并通过 event bus 投递 Telegram 或 Feishu。

Python 项目若只需结构化 API，应在 `CollectionResult` 返回后结束。若需要报告层，应把它实现为独立 consumer，并让报告中的每条数值/引用都能回链至本 SOP 定义的 `FilingMetadata`、`ParsedSection` 或 `MetricValue` provenance。
