# G2LC-DR 仓库独立代码审计与调整建议

> 审计对象：`https://github.com/boboji1233/G2LC-DR`  
> 审计分支：`main`  
> 审计基线提交：`8f96f8f6b496021d37606e5ddaa936bbaf7f58e7`  
> 审计日期：2026-08-20  
> 审计性质：静态代码与架构审计；由于执行环境无法直接访问 GitHub 网络，本报告没有冒充本地复跑结果。

## 1. 总结结论

仓库不是 README 或伪代码空壳。当前版本已经具备：

- 类型化本体、指南 DSL、三值逻辑；
- CP-SAT 有限状态求解原型；
- Z3 反例搜索与约束生成原型；
- 三类证书及验证器；
- 合成夹具、测试、CI 配置；
- 不伪造标签的 metadata-only 数据适配器；
- MAPLES/MESSIDOR 测试锁和 DDR/MMRDR-CFP 同源意识。

但是，当前 `STATUS.md` 中的 “Stage 1 compiler gate completed” 不能作为论文级正确性结论。核心数学语义、有限求解器、Z3 求解器和证书验证器之间尚未完全等价，且若干实现会使编译器求解错误的“最小标注”问题。

建议正式状态降级为：

> **Stage 1 functional prototype complete; Stage 1.5 semantic soundness gate failed/pending.**

在 Stage 1.5 通过前：

- 不转写生产临床指南；
- 不开始真实 Oracle 实验；
- 不训练视觉模型；
- 不生成论文实验数字；
- 不声称证书已经独立证明最优性或完整性。

## 2. 做得好的部分

1. `EvidenceLabel` 与 `TriValue` 被分开建模，缺失标签没有自动转成阴性。
2. YAML/JSON 使用严格 Pydantic 模型，额外字段被拒绝。
3. `INCOMPLETE` 与 `OUT_OF_SPEC` 在模型层面有区分。
4. 合成规则、相对成本和临床规则被明确隔离。
5. 数据适配器默认所有临床标签为 `UNKNOWN`，不从文件名猜测诊断。
6. DDR 与 MMRDR-CFP 被归入同一个 `OIA_DDR` source family。
7. MAPLES/MESSIDOR 被标为最终测试资源。
8. 求解器、证书、CLI 和测试已经形成可继续重构的工程基础。

## 3. 阻断性问题

### P0-1：编译器当前区分的是“完整评估轨迹”，不是“临床行动”

`action_signature()` 序列化整个 `GuidelineEvaluation`，其中包含：

- `status`
- `actions`
- `matched_clauses`
- `unknown_clauses`
- `unsupported_predicates`

有限问题随后用这个完整签名判断两个状态是否需要被标注方案区分。

后果：

- 两个病例得到完全相同的临床行动，但由不同规则触发，也会被认为必须区分；
- 一个病例由显式规则产生 `routine`，另一个由 default 产生 `routine`，也可能被认为必须区分；
- 编译器会选择额外标注，破坏“最低成本行动充分标注”的主张；
- finite solver 与 Z3 solver 实际求解的目标不一致，因为 Z3 只比较行动索引。

必须拆分：

- `decision_signature`：只编码规范化后的可能临床行动集合；用于可执行性、状态对和求解器；
- `trace_signature`：编码命中规则和未知规则，仅用于审计、解释和调试。

### P0-2：优先级规则在高优先级未知时可能给出错误的唯一行动

当前逻辑只要存在一个 `TRUE` 规则，就选择最高优先级的 `TRUE` 规则，而没有检查更高优先级规则是否为 `UNKNOWN`。

反例：

```text
priority 90: NV present  -> urgent
priority 60: hemorrhage -> refer
state: hemorrhage=true, NV=UNKNOWN
```

当前可能返回唯一 `refer`。但 NV 的一个合法补全会产生 `urgent`，因此安全语义应为：

- 可能行动集合 `{urgent, refer}`；或
- `INSUFFICIENT_EVIDENCE`，并指出 NV 是决策关键缺失证据。

必须定义并实现“所有可行补全下的可能行动集合”，不能将高优先级未知条件默认为不会触发。

### P0-3：Python、有限枚举和 Z3 的指南语义不一致

当前存在至少三套语义：

1. Python `evaluate_guideline`：三值、可能返回 `ACTION_SET`；
2. finite problem：序列化完整评估对象；
3. Z3 `_guideline_action_z3`：完整状态、单一整数行动、按排序构建嵌套 `If`。

风险包括：

- 同优先级冲突在 Python 中可能形成行动集合，在 Z3 中可能由规则顺序隐式打破；
- finite 与 separation solver 可对同一问题给出不同“最优解”；
- 证书验证器复用 Z3 路径后无法证明 finite 路径语义正确。

必须先冻结一份正式决策语义，再分别实现 Python 参考解释器与 Z3 编码，并做穷举差分测试。

### P0-4：临床可行状态没有被形式化

当前 complete state 是所有本体谓词允许值的笛卡尔积。`requires` 与 `parent_predicate` 只用于检查引用和环，不会约束状态。

后果：

- 医学上不可能的组合进入状态空间；
- 不可能状态生成假反例；
- 最小标注方案被过度约束；
- 状态空间包含与目标指南无关的全部本体谓词，容易指数爆炸。

需要一个可执行的 feasibility constraint DSL，至少支持：

- implication；
- mutual exclusion；
- conditional allowed values；
- exactly-one / at-most-one；
- parent-child consistency；
- deterministic derivation consistency。

同一约束必须同时应用于有限枚举和 Z3。

### P0-5：推导图只有“结构”，没有可验证的值语义

`DerivationRule` 只包含输入和输出谓词 ID，没有说明输出值如何由输入值计算。当前 closure 只要输入谓词“可观察”，便直接读取状态中的输出值。

这等价于假设：

> 知道输入后，就能神奇地看到输出在该状态中的任意值。

必须采用一种明确且可证明的方案：

**推荐方案：**

- 每条推导规则包含有限、确定、总定义的 mapping/truth table；
- 对每种输入组合唯一产生输出值；
- 本体可行性约束强制输出与 mapping 一致；
- observation closure 通过 mapping 计算输出，而不是读取一个独立的任意状态值。

若暂时不支持一般多输入规则，则应明确将 Stage 1.5 限制为：

- 单输入；
- 有限；
- 确定；
- 总定义；
- 可组合的有向无环 coarsening/refinement 映射。

禁止继续保留无值语义的多输入规则。

### P0-6：当前 test-cover 公式不能正确处理算子协同推导

finite solver 预先计算“每个单独算子能区分哪些状态对”，再求集合覆盖。

若：

```text
operator A observes p
operator B observes q
p AND q deterministically derive r
guideline depends on r
```

A 或 B 单独可能都不能区分，但 A+B 联合可以。单算子 coverage 的并集无法表达这种协同。

必须二选一：

1. 将推导语言严格限制为不会产生算子协同的 unary deterministic closure，并在 schema/validator 中拒绝多输入规则；或
2. 重写 CP-SAT，使其显式建模 selected operators、observed predicates 和 derivation activation。

在没有完成其中之一前，不能将当前 CP-SAT 称为一般 annotation-derivation lattice 的精确解。

### P0-7：算子 prerequisites 没有被求解器执行

当前 operator schema 有 `prerequisites`，合成 fixture 也写了 `prerequisites: [gradable]`，但 exact、greedy 和 separation solver 都没有执行它。

同时，`derivable_outputs` 会被直接视为精确可观察输出，绕过 derivation graph。

必须：

- 明确 prerequisites 是“前置算子”还是“前置证据/采集条件”；
- 不允许一个字段同时承担两种语义；
- 在 exact、greedy、separation 和 verifier 中一致执行；
- 删除未经验证的 `derivable_outputs` 快捷路径，或将其改成经过 schema 验证的 operator capability；
- 加入 modality compatibility 检查。

### P0-8：证书验证器不是算法独立的验证器

当前 verifier 直接复用：

- `find_counterexample`
- `build_finite_problem`
- `brute_force_optimum`
- `exact_observed_predicates`
- 相同 loader 和相同 evaluator

因此编译器和验证器可能共享同一个错误，并同时通过测试。

建议建立独立验证边界：

- `src/g2lc_verifier/` 或明确的 `independent_verifier` 包；
- 禁止导入 `g2lc.compiler.*`；
- 独立重建状态、行动语义、可观察闭包和成本；
- 小夹具使用独立穷举；
- 大问题使用直接 SMT 检查；
- 用 import-boundary test 自动禁止违反依赖方向。

“certificate_hash” 只是内容校验和，不是数字签名或来源真实性证明，文档必须使用准确措辞。

## 4. 高优先级问题

### P1-1：证书字段没有全部重算

需要重算并严格比较：

- `guidelines_covered`
- 规则/决策覆盖字段
- `selected_operators`
- `derived_predicates`
- `total_cost`
- `solver_status`
- `verification` payload
- OOS 的 reason、required modalities 和 source clauses
- INCOMPLETE 的 missing predicates、minimum repair cost、minimal additions
- counterexample 的左右行动和不可区分性

现有篡改测试主要依赖“没有重算 certificate hash”而失败，尚不能证明语义篡改会被独立拒绝。

### P1-2：`clauses_covered` 命名不成立

行动充分并不意味着能够区分每条规则真值或还原命中规则。证书只是证明所有指南行动区别被保留。

应改为：

- `decision_programs_covered`
- `action_distinctions_covered`

除非另行定义并验证 clause-trace sufficiency，否则删除 `clauses_covered`。

### P1-3：repair 求解的不是最低增量修复成本

当前 repair 把 available 与 unavailable operators 一起重新按总成本优化，然后只报告 unavailable selections。

正确的 repair 问题应是：

- 当前 available operator set 视为已存在、固定或增量成本为 0；
- 只最小化新增 unavailable operator 的增量成本；
- instability 权重与主目标一致；
- 验证新增集合与当前 available 集合合并后可执行。

### P1-4：成本离散化可能改变最优解

`_units` 将成本四舍五入到 0.001。若候选方案成本差小于该精度，CP-SAT 与 float brute force 可能优化不同目标。

应：

- 在输入 schema 中采用 Decimal 字符串或明确整数成本单位；
- 冻结 objective scale；
- 分层优化：成本 -> 数量 -> 确定性字典序；
- 添加亚毫精度、等成本、等数量、零成本测试。

### P1-5：separation solver 可能错误声称 OPTIMAL

当 restricted master 只返回 `FEASIBLE` 时，最终不能无条件改成 `OPTIMAL`。必须保留真实 master status，并只有在每轮 master 最优、反例 oracle sound 且收敛时才声明全局最优。

### P1-6：symbolic certificate 路径仍会强制枚举状态

certificate writer 对所有非 OOS 结果调用 `enumerate_states()`。这会使原本用于大状态空间的 separation solver 在写证书时重新失败。

证书必须按 proof method 区分：

- finite-exhaustive；
- finite-cp-sat；
- smt-counterexample-free；
- feasible-only；
- optimality-not-certified。

### P1-7：指南验证会静默跳过大状态冲突

当状态数超过 `conflict_state_limit`，同优先级冲突检查被直接跳过，且没有 Z3 fallback。

必须：

- 使用 SMT 始终检查冲突、死规则、未覆盖状态；
- 或明确返回 validation incomplete，禁止生产规则晋级；
- action schema 应要求每个行动包含与 schema 完全一致的 key；
- effective_date 应为 ISO date 或明确允许 synthetic sentinel；
- typed equality 不应混淆 Python 的 `True == 1`。

## 5. 工程与门禁问题

1. Makefile 没有 `stage1-gate`。
2. CI 没有 branch coverage。
3. coverage 配置排除了整个 `src/g2lc/data/*`，当前 89.47% 是 scoped coverage，不是仓库总覆盖。
4. CI 没有执行 package build。
5. `artifacts/audit/stage1_gate.json`、审计报告和 review bundle 不在仓库。
6. 最新 commit 没有可独立确认的 GitHub status check 结果。
7. 当前测试主要围绕一个 24-state fixture，无法支持一般正确性主张。

## 6. Stage 2 数据层建议

Stage 2 当前只应保留安全骨架。真实异构医学监督不应长期塞在单个 image row 的：

- `dr_grade`
- `label_status`
- `annotation_granularity`

推荐拆分为：

```text
images.parquet
cases.parquet
labels.parquet
regions.parquet
correspondences.parquet
splits.parquet
```

`labels.parquet` 至少包含：

```text
global_image_id
predicate_id
value_json
label_status
annotation_granularity
annotator_id_or_group
annotator_count
adjudication_status
source_table
source_row_id
source_row_hash
guideline_system
guideline_version
provenance
```

在 Stage 1.5 通过前，不继续扩展真实 dataset parsers。

## 7. 下一轮唯一目标

下一轮 Codex 的唯一目标应是：

> **让 Python reference semantics、finite exact solver、Z3 solver、repair solver 和 independent verifier 对同一个正式数学问题给出一致结果。**

通过标准不是测试数量，而是：

- 关键反例先失败、修复后通过；
- 多组随机小问题 exact=brute-force=separation；
- feasible-state constraints 在 Python 与 Z3 完全一致；
- action-only sufficiency；
- derivation semantics 可执行且一致；
- verifier 不导入 compiler；
- 重哈希后的语义篡改全部被拒绝；
- branch coverage 与 CI gate 真实通过。

## 8. 当前评分

| 维度 | 评分 | 说明 |
|---|---:|---|
| 仓库工程组织 | 8/10 | 结构清晰，不是空壳 |
| 类型与数据安全意识 | 8/10 | UNKNOWN、许可、测试锁处理较好 |
| 合成原型完成度 | 7/10 | CLI、solver、certificate 已成形 |
| 数学语义一致性 | 4/10 | finite/Python/Z3 尚不统一 |
| 最小标注最优性可信度 | 3/10 | 当前可能优化 trace，并忽略协同/前置条件 |
| 证书独立性 | 3/10 | verifier 复用核心实现 |
| 真实 Oracle 准备度 | 2/10 | 无生产规则、无真实数据且核心需修复 |
| 视觉训练准备度 | 0/10 | 目前不应启动 |

最终结论：

> **保留现有仓库作为很好的原型基础，但撤销 Stage 1 已完成的结论，先执行 Stage 1.5 语义正确性重构。**
