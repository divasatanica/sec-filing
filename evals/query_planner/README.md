# QueryPlanner 基线评测

本目录使用 Promptfoo 调用真实 DeepSeek API，检查生产代码中的 QueryPlanner。
不需要启动 FastAPI、数据库或 embedding 模型。普通 mock 单元测试继续放在 tests/。

## 运行

在项目根目录准备好 Python .venv（uv sync）和 Node.js/npm，然后运行 npm ci。
配置现有 .env.development 中的 SEC_FILING_AGENT_DEEPSEEK_API_KEY；
模型和 base URL 同样沿用项目 Settings。不要把密钥写进配置或问题集。

```bash
npm run eval:planner
# 关键变更可重复运行，检查稳定性：
npm run eval:planner -- --repeat 3
```

脚本使用项目 .venv，禁用 Promptfoo 缓存，串行调用真实 API，并将带 UTC 时间戳的
JSON 结果保存至 results/。Promptfoo 本地状态也保存在该目录，整个目录不提交 Git。
Promptfoo 作为 package.json 的开发依赖管理，版本固定为 0.124.0；
package-lock.json 锁定完整依赖，升级工具时也应重新验证基线。

provider.py 直接调用 QueryPlanner.plan()，不复制 prompt、schema 或 API 参数。
输出 metadata 记录模型名、prompt 和 schema 的 SHA-256，方便追踪评测版本。
由于 prompt/schema 在 provider 内部，运行此评测必须禁用缓存。

## 基线与判分

cases.yaml 包含 36 个固定案例（19 个中文、17 个英文），覆盖日历季度、不同措辞、未来日期、全年、
上半年、跨年、精确日期、闰年、多公司，以及未指定/无法确定的时间。
expected 只列出该案例要精确检查的字段；未列出的字段不要求与快照一致。
列表按集合顺序无关比较，日期精确比较，范围案例必须同时提供上下界。
2099 年案例用于确保测试长期覆盖未来期间，不依赖执行当天的日期。

assertions.py 同时验证当前 PlannerOutput schema、非空 semantic_query、日期顺序
和数组空值约定。断言只用于评测，不会给生产 planner 增加新的限制。
semantic_query 的主题保留、同比关系、错误季度和无关主题仍需人工查看；
结构化字段通过不等于检索质量通过，不对自由文本做全文快照匹配。

修改 prompt、字段描述、schema 或模型后运行本套件。对比整体通过率与失败案例，
API/连接错误单独排查，不把它们当作语义解析错误。遇到真实缺陷时新增案例；
不要仅为让测试通过而更新预期字段。问题集不应穷举真实请求，需要持续积累。

普通单元测试验证请求构造、响应解析和异常；本评测验证模型理解，二者不能互相替代。

参考：https://www.promptfoo.dev/docs/providers/python/
