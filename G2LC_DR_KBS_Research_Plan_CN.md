# G2LC-DR：面向 KBS 投稿的完整研究任务与实验实施计划

> **项目全称**：Guideline-to-Label Compiler for Diabetic Retinopathy  
> **中文名称**：糖尿病视网膜病变“指南到标注”编译器  
> **目标期刊**：Knowledge-Based Systems（KBS）  
> **文档版本**：v1.0  
> **资料核验日期**：2026-08-20  
> **研究性质**：方法学创新 + 知识系统 + 医学影像验证  
> **核心原则**：先证明“指南所需证据与标注设计”的科学问题成立，再训练视觉模型；不把新网络结构作为论文主要创新。

---

## 0. 一页执行摘要

### 0.1 最终研究方向

本文不再提出一个新的 DR 分类网络，而是研究一个新的知识系统问题：

> **给定一组版本化、可执行的临床分级/转诊指南，以及一组具有不同粒度、成本、可推导关系和标注稳定性的医学标注算子，如何自动编译出能够支持这些指南的最低成本标注方案；当已有数据不足时，如何给出可验证的缺失证据证书；当新指南超出当前影像与证据语言时，如何输出规范外证书，而不是强制预测。**

推荐论文标题：

> **From Guidelines to Labels: Certified Minimum-Cost Evidence Design for Reusable Medical Image AI**

DR 应用版标题：

> **G2LC-DR: A Guideline-to-Label Compiler for Certified and Reusable Diabetic Retinopathy AI**

### 0.2 唯一核心创新

整篇论文只围绕一个核心贡献展开：

> **将一族临床指南反向编译为最小成本、可执行、可审计的医学标注规范。**

视觉编码器、病灶分割器、基础模型、保形预测和域泛化均为验证工具，不单列为主要创新。

### 0.3 论文成立的四个硬条件

1. **形式化**：定义“指南可执行标注方案”，给出等价条件、不可执行条件和最小补充标注问题。
2. **算法化**：实现精确 CP-SAT/MILP 求解器、可扩展贪心求解器和基于 SMT 的反例生成器。
3. **同病例跨指南验证**：使用 MAPLES-DR/MESSIDOR 在同一批图像上比较不同真实分级体系，隔离普通域偏移。
4. **证书化**：对缺失证据和规范外指南输出机器可检查的证书，不允许无依据地“零样本适配”。

### 0.4 最低可行数据组合

必须优先获得：

- DDR 或 MMRDR-CFP（同一来源家族，不能作为独立域）；
- IDRiD；
- DeepDRiD；
- MAPLES-DR 标签 + 原始 MESSIDOR-1 图像；
- FGADR 或 Retinal-Lesions 至少一个；
- MMRDR-UWF 作为独立成像域验证。

### 0.5 第一阶段停止条件

在训练神经网络之前，必须完成 Oracle 实验。若真实专家病灶标注经过指南规则后仍不能合理复现对应等级，则立即停止视觉模型训练，优先检查：

- 指南规则是否转写错误；
- 指南使用的证据是否未被数据标注；
- 病灶定义是否跨数据集不一致；
- 规则是否需要区间语义或拒识，而不是确定性硬判断。

---

# 1. 研究边界、主张与非主张

## 1.1 论文允许作出的主张

论文可以主张：

1. 对一个**预先声明的影像可观察证据语言**，G2LC 能判断现有标注是否足以执行目标指南。
2. G2LC 能在候选标注算子中求出最低成本或近似最低成本的充分标注方案。
3. 对证据语言内、训练时未使用的目标指南，冻结视觉证据模型后可以加载规则并执行，无需重新训练图像编码器。
4. 当目标指南需要当前体系中不存在的证据时，G2LC 能输出缺失谓词、缺失算子和规范外证书。
5. 在 MAPLES/MESSIDOR 同病例场景中，证据驱动的跨指南执行优于简单等级映射和每指南独立分类器。
6. 标注方案可在成本、专家稳定性和指南覆盖率之间形成可解释的 Pareto 前沿。

## 1.2 论文禁止作出的主张

不得声称：

- 支持“任意未来指南”；
- 替代眼科医生或已经达到临床部署；
- 仅凭彩色眼底图像可恢复 OCT、视力、治疗史等不可观察信息；
- 首次使用病灶概念、概念瓶颈、规则推理或多指南切换；
- 新的编码器、注意力、图网络或损失函数是主要贡献；
- MMRDR-CFP 与 DDR 是两个独立数据域；
- 缺失病灶标注等价于病灶不存在；
- 使用不同数据集分别代表不同指南即可证明“指南迁移”。

## 1.3 医学范围

第一篇论文只纳入：

- 彩色眼底照相（CFP）；
- 超广角眼底照相（UWF）；
- DR 分级、可转诊决策、重拍/人工复核；
- 图像上可观察的病灶、解剖结构和质量证据。

第一篇论文不纳入：

- OCT/DME 主任务；
- 视力、血糖、治疗史等临床变量；
- KneeOA；
- LLM 自由文本诊断；
- 联邦学习；
- 生成式数据增强作为主要创新。

---

# 2. 科学问题与可检验假设

## 2.1 研究问题

### RQ1：指南可执行性

给定证据本体、标注算子集合和指南族，如何判定某个标注方案是否足以唯一执行所有指南？

### RQ2：最小标注设计

在标注成本、专家一致性和算子推导关系约束下，哪些标注算子构成最低成本的指南充分基？

### RQ3：不可执行与补救

当已有数据不足时，如何求出使目标指南可执行所需的最小补充标注集合？

### RQ4：证据预测误差下的安全决策

当视觉模型只能给出病灶数量或位置的可能集合时，如何判断临床行动是否仍唯一；若不唯一，应请求确认哪项证据？

### RQ5：未见指南执行

冻结图像模型后，仅加载训练阶段未使用的指南程序，是否能比直接分类、概念瓶颈、多头模型和等级映射更可靠地迁移决策？

## 2.2 假设

| 编号 | 假设 | 主要验证实验 |
|---|---|---|
| H1 | 全像素分割不是支持目标指南族的必要条件；较低成本的数量区间、象限和存在性组合可达到近似相同的 Oracle 指南执行性能 | P2、P8 |
| H2 | G2LC 选出的算子集在相同标注成本下，比随机、互信息、L1 稀疏选择和人工启发式覆盖更多指南 | P1、P8 |
| H3 | 在 MAPLES/MESSIDOR 同病例上，证据执行显著优于简单等级映射和每指南独立分类器 | P3 |
| H4 | 加入专家稳定性后，所选标注方案的跨专家决策方差和选择性风险低于仅按价格优化的方案 | P7、P8 |
| H5 | 对证据语言内的未见指南，冻结视觉模型并加载规则的 G2LC 可保持较低 Guideline Transport Error；对语言外指南可正确拒绝 | P5、P6 |
| H6 | G2LC 的缺失证据证书能准确找回人为删除的必要谓词/算子 | P6 |
| H7 | 直接等级头在源域可能更高，但在未见指南和同病例标签语义变化时不如证据接口稳健 | P3、P4、P5 |

---

# 3. 形式化问题定义

## 3.1 证据空间

令临床证据状态为：

\[
e=(p_1,\ldots,p_K)\in\mathcal E,
\]

其中每个谓词 \(p_k\) 具有有限或离散化后的定义域，例如：

```text
gradable ∈ {no, yes}
ma_presence ∈ {absent, present}
ma_count_bin ∈ {0, 1-4, 5-19, >=20}
hem_quadrants ∈ {0, 1, 2, 3, 4}
venous_beading_quadrants ∈ {0, 1, >=2}
irma_quadrants ∈ {0, >=1}
nv_presence ∈ {absent, present, uncertain}
vitreous_hemorrhage ∈ {absent, present}
```

离散边界必须来自目标指南使用的真实阈值，不得使用任意等宽分箱。

## 3.2 指南

一套版本化指南表示为：

\[
g:\mathcal E\rightarrow\mathcal A,
\]

其中行动空间可包括：

```text
grade ∈ {no_DR, mild, moderate, severe, proliferative}
referral ∈ {routine, surveillance, refer}
acquisition_action ∈ {accept, reshoot, manual_review}
```

每条规则必须带有：

- `guideline_id`
- `version`
- `effective_date`
- `source_url`
- `source_section`
- `modality_scope`
- `required_predicates`
- `rule_priority`
- `action`
- `review_status`

## 3.3 标注算子

候选标注算子 \(q_j\) 是从真实证据状态到可保存标注的映射：

\[
q_j:\mathcal E\rightarrow\mathcal Z_j.
\]

示例：

- 病灶存在性；
- 数量区间；
- 精确计数；
- 象限级计数；
- 点标注；
- 像素掩膜；
- 病灶到黄斑的距离区间；
- 图像质量等级；
- 图像级最终 DR 等级。

每个算子包含：

\[
(c_j,\ v_j,\ o_j,\ \text{prerequisite}_j,\ \text{derives}_j),
\]

分别表示：

- 标注成本；
- 不稳定性或观察者差异；
- 可观察模态；
- 前置条件；
- 可推导出的低粒度算子。

## 3.4 指南可执行性

一个标注方案 \(S\subseteq Q\) 对指南族 \(\mathcal G\) 可执行，当且仅当：

\[
\forall g\in\mathcal G,\ \exists h_g,\quad g=h_g\circ\phi_S,
\]

其中 \(\phi_S(e)\) 是方案 \(S\) 对证据状态的联合观测。

等价地：

\[
\phi_S(e)=\phi_S(e')
\Rightarrow
g(e)=g(e'),\quad
\forall e,e'\in\mathcal E,\ \forall g\in\mathcal G.
\]

其反例形式为：

\[
\exists e,e',g:
\phi_S(e)=\phi_S(e')\land g(e)\neq g(e').
\]

只要该公式可满足，方案 \(S\) 就不可执行；反例状态对本身就是可解释的失败证书。

## 3.5 最小成本指南充分标注

\[
S^\star=
\arg\min_{S\subseteq Q}
\sum_{q_j\in S}
\left(c_j+\lambda_v v_j+\lambda_m m_j\right)
\]

约束：

\[
S\text{ 对 }\mathcal G\text{ 可执行},
\]

其中 \(m_j\) 可表示模态采集、标注工具或数据许可的额外代价。

## 3.6 最小补充标注

给定已有算子集合 \(S_0\)：

\[
\Delta S^\star=
\arg\min_{\Delta S\subseteq Q\setminus S_0}
C(\Delta S)
\]

约束：

\[
S_0\cup\Delta S
\text{ 对目标指南族可执行}.
\]

输出应包括：

- 缺失谓词；
- 最小补充算子；
- 增量成本；
- 由哪些指南条款触发；
- 不补充时的反例状态对。

## 3.7 证据集合下的选择性执行

视觉模型对图像 \(x\) 输出证据可能集合：

\[
\Gamma(x)\subseteq\mathcal E.
\]

对指南 \(g\)，行动集合为：

\[
A_g(x)=\{g(e):e\in\Gamma(x)\}.
\]

- 若 \(|A_g(x)|=1\)，输出唯一行动和证书；
- 若 \(|A_g(x)|>1\)，拒识并报告最有价值的待确认证据；
- 若指南调用了证据语言外的谓词，输出 `OUT_OF_SPEC`。

---

# 4. 创新护栏与近邻工作区分

## 4.1 必须承认的直接近邻

| 工作 | 已解决的问题 | 本项目不能重复声称 | G2LC 的差异 |
|---|---|---|---|
| DAPHNE（Eye, 2022） | 检测病灶后可在 ICDRS 与 UK NSC 等标准间切换 | “首次通过病灶支持多分级体系” | 从指南反向推导最低成本标注；给出可执行性、缺失证据和规范外证书 |
| DR 概念瓶颈研究（2024） | 使用概念解释 DR 分类 | “首次概念化解释 DR” | 研究数据标注设计和指南充分性，而非仅概念到等级预测 |
| VLM-GCR（AAAI 2026） | 病灶概念图、概念伪标签与可干预推理 | “首次病灶图谱推理” | 不把图谱预测作为核心，核心是指南族到标注算子的反向编译 |
| RETFound/UrFound/FLAIR | 视网膜基础模型与迁移 | “首次用基础模型提升 DR” | 基础模型只作为证据预测器和强基线 |
| DG-ADR、CauDR、DECO 等 | 跨数据集域泛化 | “首次跨域 DR” | G2LC 区分图像域偏移与同图像标签规范变化 |
| HACDR-Net | 多病灶分割 | “首次联合病灶分割” | 分割只是高成本算子基线，论文研究何时不需要完整分割 |

## 4.2 审稿时的唯一主线

论文贡献建议只写三条：

1. **新问题**：将临床指南族反向编译为医学标注需求，并定义指南可执行性。
2. **新方法与理论**：给出可执行性反例、最小成本标注求解、最小补充标注和规范外证书。
3. **新协议**：在同病例多分级体系、未见指南、跨图像域和多专家标注差异下进行验证。

视觉模型贡献不得单独列为第四条。

---

# 5. 总体工作包与依赖关系

```text
WP0 研究治理与复现框架
 ├── WP1 数据获取、许可、主表与去重
 ├── WP2 证据本体、指南 DSL 与规则单元测试
 │    └── WP3 标注算子格、成本与稳定性模型
 │          └── WP4 G2LC 精确/近似编译器与证书
 │                └── WP5 Oracle 可执行性实验  ← 关键 Go/No-Go
 │                      ├── WP6 视觉证据预测模型
 │                      ├── WP7 证据集合与选择性执行
 │                      └── WP8 对比、消融、统计与外部验证
 └───────────────────────────────────────────────┘
                         ↓
                  WP9 论文、开源与投稿
```

## 5.1 工作包交付物

| 工作包 | 交付物 | 退出标准 |
|---|---|---|
| WP0 | Git 仓库、环境锁、CI、实验登记表 | `pytest`、lint、类型检查通过 |
| WP1 | 数据许可台账、统一 manifest、去重报告 | 无已知跨划分重复；患者级划分可追踪 |
| WP2 | `evidence_ontology.yaml`、4 套指南 DSL、规则测试 | 所有规则覆盖/互斥/版本检查通过 |
| WP3 | `annotation_operators.yaml`、推导图、成本表 | 每个算子具有来源、成本、稳定性和可推导关系 |
| WP4 | CP-SAT 精确求解、贪心求解、SMT 反例与证书 | 小规模穷举结果与精确求解完全一致 |
| WP5 | Oracle 结果、同病例跨指南结果 | 至少一个非平凡最小方案成立；规则执行可解释 |
| WP6 | 证据预测模型与基线 | 主要病灶 AUPRC、校准和外域结果完整 |
| WP7 | 行动集合、拒识和缺失证据查询 | 证书 soundness 通过自动测试 |
| WP8 | 全部协议、对比、消融、统计 | 主假设 H1–H7 有预注册结论 |
| WP9 | 论文、附录、代码、模型卡、数据卡 | 可从零复现实验表格和图 |


# 6. 数据集获取、许可与用途

## 6.1 数据分层

### A 级：核心、不可替代

| 数据集 | 规模与标签 | 本项目角色 | 获取方式 | 关键风险 |
|---|---|---|---|---|
| MAPLES-DR + 原始 MESSIDOR-1 | 198 张同病例；新 DR/ME 等级；10 类解剖/病理像素标注；保留 MESSIDOR 原等级 | 同病例跨指南核心测试、Oracle 实验、标注时间与规则验证 | MAPLES 标签公开；原图需从 ADCIS 申请 | 必须下载 MESSIDOR original，不是 MESSIDOR-2；不得用目标 Canadian 等级调参 |
| MMRDR | 11,118 CFP、10,404 UWF、2,938 OCT；CFP/UWF 有 5 级 DR 和 7 类病灶存在性 | 大规模高级病灶存在性；UWF 独立外域；官方基础模型基线 | Figshare 公开 | MMRDR-CFP 来源是 OIA-DDR，与 DDR 重叠 |
| IDRiD | 516 张分级图像；81 张精细病灶分割；视盘/黄斑任务 | 精细 MA/HE/EX/SE、解剖和空间算子 | IEEE DataPort | 规模小；按官方划分，缺失标签不能当阴性 |
| DeepDRiD | 常规眼底、双视野、质量标签和 UWF；官方训练/验证/外部验证 | 图像质量、双视野、重拍/复核决策、UWF 外域 | 官方 GitHub | 同一患者/眼的多视野不得跨训练测试 |

### B 级：强烈建议

| 数据集 | 规模与标签 | 角色 | 获取方式 | 风险 |
|---|---|---|---|---|
| FGADR Seg-set | 1,842 张；MA、HE、EX、SE、IRMA、NV 像素标注；3 名眼科医生分级 | 补 IRMA、NV，建立高等级规则证据 | 签署非商业协议后邮件申请 | Grade-set 当前未开放；禁止再分发 |
| Retinal-Lesions | 1,593 张；8 类像素病灶；45 名眼科医生重分级 | 补 NV、玻璃体前/玻璃体出血、纤维增殖 | 官方 Google Form 申请 | 图像来自 Kaggle EyePACS 子集；与 EyePACS 不能跨域重复使用 |
| MAPLES 多专家子集 | 51 张；3 名资深视网膜专家独立标注 MA、Hem、EX、CWS | 估计算子稳定性和跨专家决策方差 | MAPLES 资源/Scientific Reports 文章所述公开数据 | 以轻中度病例为主，不能代表全部 DR |

### C 级：可选扩展

- EyePACS：增加大规模分级与相机/国家域差异；使用 Retinal-Lesions 时必须去除其对应 EyePACS 图像。
- APTOS 2019：外域分级基线。
- MESSIDOR-2：仅用于独立外域分级，不能替代 MAPLES 对应的 MESSIDOR original。
- TJDR：FGADR 或 Retinal-Lesions 申请失败时，补充四类常见病灶分割。
- RFMiD/ODIR：开放集和其他眼病干扰测试，不进入核心指南编译实验。

## 6.2 官方获取入口与具体步骤

### 6.2.1 DDR / OIA-DDR

官方入口：

- https://github.com/nkicsl/DDR-dataset
- 仓库 README 提供百度网盘和 Google Drive。

下载后文件被拆为 10 个分片，Linux/macOS 合并方式：

```bash
mkdir -p data/raw/ddr
cd data/raw/ddr
cat DDR-dataset.zip.0* > DDR-dataset.zip
unzip DDR-dataset.zip
```

Windows PowerShell 可使用：

```powershell
Get-Content DDR-dataset.zip.0* -Encoding Byte |
  Set-Content DDR-dataset.zip -Encoding Byte
```

更稳妥的 Windows 方式是在 WSL 中运行 Linux 命令。

检查项：

```bash
find data/raw/ddr -type f | wc -l
sha256sum data/raw/ddr/DDR-dataset.zip > data/checksums/ddr_archive.sha256
```

**用途**：

- DR 分级；
- 757 张病灶分割/检测子集；
- 与 MMRDR-CFP 标签合并后获得更丰富图像级病灶存在性。

**硬规则**：MMRDR-CFP 明确以 OIA-DDR 为源，因此二者必须标记为同一 `source_family=OIA_DDR`，禁止在“跨域”实验中一边训练、一边测试。

### 6.2.2 MMRDR

官方入口：

- 数据：https://figshare.com/articles/dataset/MMRDR/29423747
- 论文评测代码：https://github.com/Vladimirovich2019/MMRDR_Evaluation
- 论文：https://www.nature.com/articles/s41597-026-07005-9

公开 Figshare 元数据可通过 API 读取：

```bash
mkdir -p data/raw/mmrdr data/metadata
curl -L "https://api.figshare.com/v2/articles/29423747" \
  -o data/metadata/mmrdr_figshare.json
```

项目应提供安全下载器：

```bash
python scripts/download_figshare.py \
  --article-id 29423747 \
  --output-dir data/raw/mmrdr \
  --write-checksums
```

下载器要求：

- 从 Figshare API 读取每个文件的公开下载 URL；
- 流式下载；
- 支持断点续传；
- 校验 Figshare 提供的 MD5；
- 记录文件名、大小、MD5、下载日期；
- 不自动接受任何非公开许可。

**只在主论文使用 CFP 与 UWF**。OCT 可保留在数据仓库但第一篇不做主实验。

MMRDR 标签顺序必须直接从官方 CSV/论文确认并写入版本化映射，不能根据字段位置猜测。官方列出的七类包括：

```text
MA, hard exudate, intraretinal hemorrhage,
VB/IRMA, neovascularization, vitreous hemorrhage, retinal detachment
```

注意 `VB/IRMA` 是合并标签，不能拆成独立 VB 与 IRMA 真值。

### 6.2.3 IDRiD

官方入口：

- 项目页：https://idrid.grand-challenge.org/Data/
- IEEE DataPort：https://ieee-dataport.org/open-access/indian-diabetic-retinopathy-image-dataset-idrid
- DOI：https://doi.org/10.21227/H25W98

步骤：

1. 注册 IEEE DataPort；
2. 阅读并接受数据许可；
3. 下载分割、分级和视盘/黄斑定位任务；
4. 保留官方训练/测试划分；
5. 将原始归档和解压后的目录都记录校验值。

建议目录：

```text
data/raw/idrid/
├── A_Segmentation/
├── B_Disease_Grading/
└── C_Localization/
```

不要将 81 张精细标注图像的缺失任务扩展为全 516 张阴性掩膜。

### 6.2.4 DeepDRiD

官方入口：

- https://github.com/deepdrdoc/DeepDRiD
- 许可：仓库标注 CC-BY-SA-4.0。

获取：

```bash
git clone --depth 1 https://github.com/deepdrdoc/DeepDRiD.git \
  data/raw/deepdrid
```

如仓库因大文件导致浅克隆不完整，则：

```bash
git -C data/raw/deepdrid lfs install
git -C data/raw/deepdrid lfs pull
```

核对以下目录：

```text
regular_fundus_images/
  regular-fundus-training/
  regular-fundus-validation/
  Online-Challenge1&2-Evaluation/
ultra-widefield_images/
  ultra-widefield-training/
  ultra-widefield-validation/
  Online-Challenge3-Evaluation/
```

重点解析：

- DR 等级；
- overall quality；
- artifacts；
- clarity；
- field definition；
- patient/eye/view 标识。

若患者 ID 可由文件名或表格恢复，所有视野必须按患者分组划分。

### 6.2.5 FGADR

官方入口：

- https://csyizhou.github.io/FGADR/

步骤：

1. 下载并阅读 IIAI FGADR Dataset Research Use Agreement；
2. 签署协议；
3. 将签署文件发送至官方页面给出的邮箱 `yizhou.szcn@gmail.com`；
4. 获取个人下载链接；
5. 禁止将原始图像、下载链接或衍生可还原数据放入公开仓库。

当前可用的是 **Seg-set 1,842 张**；Grade-set 尚未获得法律/医院批准，不应将其写入必需实验。

仓库只保存：

```text
data/licenses/fgadr/
├── agreement_status.yaml
└── access_notes.md
```

不得提交签名协议或个人信息。

### 6.2.6 MAPLES-DR 标签

官方入口：

- Figshare：https://figshare.com/articles/dataset/_b_MAPLES-DR_b_MESSIDOR_Anatomical_and_Pathological_Labels_for_Explainable_Screening_of_Diabetic_Retinopathy/24328660
- 文档：https://liv4d.github.io/MAPLES-DR/en/
- 论文：https://www.nature.com/articles/s41597-024-03739-6

下载器：

```bash
python scripts/download_figshare.py \
  --article-id 24328660 \
  --output-dir data/raw/maples_labels \
  --write-checksums
```

推荐同时保存：

- `MAPLES-DR.zip`
- `AdditionalData.zip`

`AdditionalData.zip` 包含标注耗时、专家意见、预标注和共识前诊断，是建立成本/不稳定性模型的重要来源。

也可使用官方 `maples_dr` Python 库处理标签与 MESSIDOR 图像的匹配、裁剪和统一尺寸；版本必须锁定。

### 6.2.7 原始 MESSIDOR-1 图像

官方入口：

- https://www.adcis.net/en/third-party/messidor/

步骤：

1. 在 ADCIS 页面填写研究用途；
2. 完成邮箱验证；
3. 下载原始 MESSIDOR 的所有分卷；
4. 不要下载 MESSIDOR-2 代替；
5. 按 MAPLES 文档匹配图像名；
6. 对 198 张目标图像生成匹配报告。

必须自动检查：

```text
expected_maples_images = 198
matched_images = 198
unmatched_images = 0
duplicate_matches = 0
```

任何不满足都阻断 P2/P3 实验。

### 6.2.8 Retinal-Lesions

官方入口：

- https://github.com/WeiQijie/retinal-lesions

官方仓库提供 Google Form 申请入口。获得数据后：

- 标记 `source_family=EYEPACS_RLDR`；
- 保留 8 类像素病灶；
- 记录灰度值 127 表示作者指出不符合其采用分级规范、但仍保留在掩膜中的区域；
- 与 EyePACS 做图像去重，禁止把同一图像分别放在训练与测试。

### 6.2.9 MAPLES 多专家标注

论文：

- https://www.nature.com/articles/s41598-026-53558-5

用途：

- 51 张图像；
- 3 名资深视网膜专家；
- 独立标注 MA、出血、硬性渗出和 CWS；
- 用于估计存在性、计数、位置和像素边界四类算子的稳定性。

若下载入口集成到 MAPLES Figshare 更新版本，应在 `data_sources.yaml` 中记录文章版本与文件校验值，不得默认旧版本已经包含该子集。

## 6.3 数据许可台账

创建 `data/licenses/dataset_registry.yaml`：

```yaml
datasets:
  - dataset_id: mmrdr
    source_url: https://figshare.com/articles/dataset/MMRDR/29423747
    license: "verify-from-source"
    access_type: public
    redistribution_allowed: false
    commercial_use: false
    downloaded_at: null
    checksum_manifest: data/checksums/mmrdr.json

  - dataset_id: fgadr
    source_url: https://csyizhou.github.io/FGADR/
    license: research-use-agreement
    access_type: request
    redistribution_allowed: false
    commercial_use: false
    downloaded_at: null
    approval_reference: null
```

每个数据集必须记录：

- 获取日期；
- 许可版本；
- 是否允许再分发；
- 是否允许公开衍生标签；
- 论文要求的引用；
- 原始归档校验值；
- 访问审批状态。

## 6.4 没有私人专家标注时的补救结论

不需要自行创建大规模专家标注子集。核心创新由以下公开资源支撑：

1. MAPLES/MESSIDOR：同病例多分级体系；
2. MMRDR：大规模高级病灶存在性；
3. FGADR/Retinal-Lesions：高级病灶像素证据；
4. MAPLES 多专家子集：标注稳定性；
5. DeepDRiD：质量和 UWF。

没有自己的专家数据会限制“临床部署”主张，但不会破坏：

- 指南可执行性定义；
- 编译器；
- 最小标注设计；
- 缺失证据证书；
- 同病例跨指南实验。

最低成本的专家合作只需请眼科医生审核：

- 指南—谓词矩阵；
- DSL 规则；
- 10–20 个规则边界病例；
- 哪些谓词在 CFP/UWF 中可观察。

---

# 7. 计算环境、仓库与工程规范

## 7.1 建议硬件

### 编译器与 Oracle 阶段

- CPU：8 核以上；
- 内存：32 GB；
- GPU：不需要；
- 磁盘：200 GB 起。

### 视觉模型最低配置

- 1×24 GB GPU；
- 64 GB 内存；
- 1 TB SSD。

### 强版本配置

- 2–4×24/48 GB GPU；
- 128 GB 内存；
- 2 TB SSD。

所有论文结果必须报告实际 GPU 型号、训练时长、峰值显存和总 GPU-hours。

## 7.2 主环境

建议主项目使用：

- Python 3.11；
- PyTorch 2.6.x + CUDA 12.4 作为参考锁定环境；
- `uv` 或 Conda；
- Linux/WSL2；
- Docker 作为可选复现层。

基础模型旧代码使用独立环境，禁止为了兼容 UrFound/RETFound 的旧依赖而污染主环境。

主要依赖：

```text
torch
torchvision
timm
segmentation-models-pytorch
albumentations
opencv-python-headless
pillow
numpy
pandas
pyarrow
scipy
scikit-learn
statsmodels
torchmetrics
hydra-core
omegaconf
pydantic
typer
rich
networkx
ortools
z3-solver
pulp
rapidfuzz
imagehash
faiss-cpu
mlflow
dvc
pytest
hypothesis
ruff
mypy
pre-commit
```

## 7.3 仓库结构

```text
g2lc-dr/
├── README.md
├── LICENSE
├── CITATION.cff
├── pyproject.toml
├── uv.lock
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── .gitignore
├── .pre-commit-config.yaml
├── configs/
│   ├── data/
│   ├── guideline/
│   ├── compiler/
│   ├── model/
│   ├── experiment/
│   └── cost/
├── data/
│   ├── raw/                 # 永不入 Git
│   ├── interim/
│   ├── processed/
│   ├── manifests/
│   ├── metadata/
│   ├── checksums/
│   └── licenses/
├── docs/
│   ├── G2LC_DR_KBS_Research_Plan_CN.md
│   ├── DATA_ACCESS.md
│   ├── GUIDELINE_PROVENANCE.md
│   ├── EXPERIMENT_REGISTRY.md
│   └── DECISIONS.md
├── guidelines/
│   ├── ontology/
│   ├── messidor/
│   ├── canadian/
│   ├── icdr/
│   ├── nhs_des/
│   └── synthetic/
├── src/g2lc/
│   ├── cli.py
│   ├── schemas/
│   ├── data/
│   ├── dedup/
│   ├── ontology/
│   ├── guidelines/
│   ├── operators/
│   ├── compiler/
│   ├── certificates/
│   ├── oracle/
│   ├── models/
│   ├── calibration/
│   ├── evaluation/
│   └── reporting/
├── scripts/
│   ├── download_figshare.py
│   ├── prepare_*.py
│   ├── run_*.sh
│   └── reproduce_tables.sh
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── fixtures/
├── baselines/
│   ├── README.md
│   ├── retfound/
│   ├── flair/
│   ├── urfound/
│   ├── hacdr_net/
│   └── dg_adr/
├── experiments/
│   ├── registry.yaml
│   ├── runs/
│   └── reports/
└── outputs/
    ├── figures/
    ├── tables/
    ├── checkpoints/
    └── certificates/
```

## 7.4 必须提供的 CLI

```bash
g2lc validate-config
g2lc build-manifest
g2lc audit-dedup
g2lc validate-ontology
g2lc validate-guidelines
g2lc enumerate-states
g2lc compile-annotations
g2lc certify-guideline
g2lc find-missing-evidence
g2lc run-oracle
g2lc train-evidence
g2lc calibrate-evidence
g2lc evaluate
g2lc render-report
```

每个命令必须：

- 支持 `--config`；
- 输出机器可读 JSON 和人类可读 Markdown；
- 在输入缺失、许可未确认或校验失败时非零退出；
- 记录 Git commit、配置哈希、数据 manifest 哈希和随机种子。


# 8. 统一数据主表、预处理与泄漏审计

## 8.1 统一 manifest

使用 Parquet 作为主存储，CSV 只用于人工检查。每一行对应一张图像或一个眼/视野样本。

最低字段：

```text
global_image_id
dataset_id
source_family
source_image_id
patient_id
eye_id
laterality
view_id
modality
camera
field_of_view
image_path
width
height
official_split
project_split
grade_system
grade_version
dr_grade
quality_overall
quality_artifact
quality_clarity
quality_field
label_status
label_source
annotator_type
annotation_granularity
license_id
sha256
phash
dataset_version
```

病灶标签采用长表：

```text
global_image_id
concept_id
value
value_type
granularity
mask_path
point_path
region_definition
annotator_id_hash
consensus_method
uncertainty
source_file
```

## 8.2 标签状态三值化

所有概念必须区分：

```text
POSITIVE
NEGATIVE
UNKNOWN
```

不得将 `UNKNOWN` 编码为 0。

例如：

- DeepDRiD 无 MA 掩膜：`UNKNOWN`；
- MMRDR 明确 MA=0：`NEGATIVE`；
- FGADR 掩膜存在非零像素：`POSITIVE`；
- 某数据集中未标该病灶：`UNKNOWN`。

训练损失使用任务掩码：

\[
\mathcal L=
\sum_{i,j}
m_{ij}\lambda_j\mathcal L_{ij},
\qquad
m_{ij}=1\ \text{仅当真实标签存在}.
\]

## 8.3 标签映射禁止事项

禁止直接假设：

- 所有 0–4 标签都遵循同一标准；
- MESSIDOR R2 等于 ICDR moderate；
- MMRDR 的 `VB/IRMA` 可拆成两个独立概念；
- MAPLES 的 neovessel 与 IRMA 在 CFP 上总能可靠区分；
- 图像级 DR 等级可以反推出所有病灶真值。

每一个跨数据集映射必须写入：

```text
configs/data/label_mapping/<dataset>.yaml
```

并注明：

- 原始定义；
- 目标定义；
- 是否为精确映射；
- 是否为多值/区间映射；
- 证据来源；
- 是否只允许用于基线。

## 8.4 图像预处理

主流程：

1. 解码检查；
2. 记录原始分辨率；
3. 去除纯黑外边框，但保存裁剪参数；
4. 保持纵横比；
5. 根据模型输入尺寸进行 padding；
6. 保存视网膜 ROI；
7. 颜色增强只在训练时进行；
8. 不覆盖原图。

建议输出：

```text
data/processed/<dataset>/<version>/
├── images_512/
├── images_1024/
├── masks_1024/
├── roi/
└── manifest.parquet
```

图像级任务建议 512 或 768；小病灶分割建议 1024 及多尺度 patch。

允许的数据增强：

- 水平翻转；
- 小角度旋转；
- 轻度亮度/对比度；
- 轻度 gamma；
- 轻度颜色扰动；
- 受控模糊/曝光模拟，用于质量实验。

禁止：

- 会消除病灶的强随机裁剪；
- 未记录参数的 CLAHE；
- 跨左右眼但不修正 laterality 的翻转；
- 将 UWF 强行裁成与 CFP 一样的局部视野而不保留原始版本。

## 8.5 四级去重流程

### L1：精确哈希

```bash
sha256sum
```

相同 SHA-256 直接归并。

### L2：感知哈希

计算：

- pHash；
- dHash；
- wHash。

以 Hamming 距离形成候选对。

### L3：深度特征近邻

使用冻结的通用视觉模型或 DINOv2 特征：

- L2 归一化；
- FAISS kNN；
- 对高相似跨数据集图像生成候选表。

### L4：几何/人工确认

对候选使用：

- SSIM；
- 特征匹配；
- 裁剪/旋转对齐；
- 人工确认。

输出：

```text
outputs/data_audit/dedup_pairs.parquet
outputs/data_audit/dedup_clusters.parquet
outputs/data_audit/dedup_report.md
```

## 8.6 已知重复关系

必须预先标记：

- `MMRDR-CFP ↔ OIA-DDR/DDR`：同源；
- `MAPLES-DR ↔ MESSIDOR original`：同一图像；
- `Retinal-Lesions ↔ EyePACS/Kaggle DR`：子集；
- `MAPLES ↔ MESSIDOR-2`：部分对应不完整，不能用 MESSIDOR-2 替代；
- 任何 GDRBench 预处理副本 ↔ 原始公开数据：同图不同版本。

## 8.7 划分策略

优先级：

1. 官方划分；
2. 患者级划分；
3. 眼级划分；
4. 无患者 ID 时图像级划分，并明确局限。

核心规则：

- 同一患者、同一眼、不同视野不能跨 split；
- MAPLES/MESSIDOR 198 张全部作为固定外部测试，不进入视觉模型调参；
- MMRDR-UWF 按官方患者级 split；
- MMRDR-CFP 只能按图像级官方 split，论文中说明；
- 所有超参数由源域验证集确定；
- 目标指南标签不用于模型选择。

---

# 9. 证据本体与指南 DSL

## 9.1 证据本体 v1

建议至少定义以下谓词。

### 图像可判读性

```text
gradable
artifact_present
clarity_level
field_definition
macula_visible
optic_disc_visible
required_view_complete
```

### 常见病灶

```text
ma_presence
ma_count
ma_count_bin
ma_quadrants
hem_presence
hem_count
hem_count_bin
hem_quadrants
hard_exudate_presence
hard_exudate_distance_to_fovea
cws_presence
cws_count
```

### 高等级病灶

```text
irma_presence
irma_quadrants
venous_beading_presence
venous_beading_quadrants
nv_presence
nvd_presence
nve_presence
vitreous_hemorrhage_presence
preretinal_hemorrhage_presence
fibrous_proliferation_presence
retinal_detachment_presence
laser_mark_presence
```

### 解剖与区域

```text
fovea_location
optic_disc_location
retinal_roi
quadrant_definition
lesion_to_fovea_distance
lesion_to_disc_distance
```

## 9.2 可观察性声明

每个谓词必须声明：

```yaml
predicate_id: irma_presence
domain: [absent, present, uncertain]
observable_modalities: [CFP, UWF]
requires:
  - gradable
known_ambiguities:
  - "IRMA may be difficult to distinguish from neovascularization on color fundus images"
out_of_scope_modalities:
  - OCT
```

若某指南需要：

- OCT 中心厚度；
- 视力；
- 治疗史；
- 荧光素渗漏；

而证据语言未包含或当前模态不可观察，编译器必须返回 `OUT_OF_SPEC`。

## 9.3 指南 DSL 示例

```yaml
guideline:
  id: nhs_des
  version: "2025-12-04"
  source_url: "https://www.gov.uk/government/publications/diabetic-eye-screening-retinal-image-grading-criteria"
  modality_scope: [CFP]
  action_schema: [grade, referral, acquisition_action]

rules:
  - id: ungradable_reshoot
    priority: 100
    when:
      any:
        - eq: [gradable, no]
        - eq: [macula_visible, no]
    then:
      acquisition_action: reshoot
      referral: manual_review

  - id: higher_risk_r2_421
    priority: 80
    when:
      any:
        - all:
            - eq: [hem_ma_severity, severe]
            - gte: [hem_ma_affected_quadrants, 4]
        - gte: [venous_beading_quadrants, 2]
        - gte: [irma_quadrants, 1]
    then:
      grade: R2H
      referral: hospital_eye_service

  - id: proliferative
    priority: 90
    when:
      any:
        - eq: [nv_presence, present]
        - eq: [vitreous_hemorrhage_presence, present]
        - eq: [preretinal_hemorrhage_presence, present]
    then:
      grade: R3
      referral: urgent
```

该示例只是软件结构；正式规则必须逐条由官方来源核验，不允许把示例当作完整 NHS 规则。

## 9.4 必须实现的指南

### G1：MESSIDOR 原分级

用途：

- 与 MAPLES 新等级做同病例语义变化；
- 验证简单等级映射为何不足。

### G2：MAPLES/Canadian teleophthalmology

用途：

- 真实专家共识目标；
- 同病例跨指南的主要目标。

### G3：ICDR

用途：

- 0–4 严重度与 4-2-1 规则；
- 证据粒度需求分析。

### G4：NHS DES 2025 版本

用途：

- 版本化、特征式分级和转诊行动；
- 作为训练阶段完全保留的未见指南；
- 其官方页面明确采用“分级者选择病灶特征，软件规则产生等级”的形式，适合编译验证。

## 9.5 规则来源与审核

建立 `docs/GUIDELINE_PROVENANCE.md`，每条规则记录：

```text
rule_id
原文来源
页面/章节
生效日期
证据谓词
转写说明
存在的模糊处
是否经过眼科医生审核
审核日期
```

规则变更通过 Git 版本控制。任何阈值更改必须产生：

- diff；
- 规则单元测试更新；
- 新旧版本决策差异报告。

## 9.6 规则验证

### 单元测试

每条规则至少包含：

- 正例；
- 边界正例；
- 边界负例；
- 缺失证据；
- 不可判读；
- 冲突规则。

### 属性测试

使用 Hypothesis 自动生成状态，验证：

- 规则结果确定；
- 优先级无循环；
- 所有合法状态有行动或明确 `UNRESOLVED`；
- 同一优先级规则不产生冲突；
- 严重证据增加时不存在非预期等级下降；
- `ungradable` 优先于普通分级。

### SMT 检查

使用 Z3 检查：

- 规则不可满足；
- 两个互斥行动同时触发；
- 状态空间未覆盖；
- 冗余规则；
- 新旧版本的最小差异状态。

---

# 10. 标注算子格与成本模型

## 10.1 标注粒度

对每类病灶定义：

```text
pixel_mask
  ├── connected_components
  ├── point_centers
  ├── exact_count
  ├── quadrant_counts
  ├── distance_to_fovea
  ├── area
  └── presence
exact_count
  ├── count_bin
  └── presence
quadrant_counts
  ├── affected_quadrants
  └── presence
image_level_grade
```

推导关系是有向无环图，不是简单线性链。例如：

- 总数量不能推出象限分布；
- 象限存在性不能推出精确计数；
- 图像级等级不能可靠推出具体病灶；
- 只有掩膜 + 有效解剖结构才能推出标准化黄斑距离。

## 10.2 算子 schema

```yaml
operator_id: hem_quadrant_count
concept_id: hemorrhage
output_type: integer_vector
domain: [0, 1, 2, 3, "4+"]
modalities: [CFP, UWF]
requires:
  - gradable
  - fovea_location
  - optic_disc_location
derives:
  - hem_affected_quadrants
  - hem_presence
base_cost: null
instability: null
source_datasets:
  - maples_dr
  - fgadr
annotation_protocol:
  type: quadrant_count
  instructions_version: v1
```

## 10.3 成本来源

按优先级使用：

1. MAPLES `AdditionalData.zip` 中实际标注时间；
2. MAPLES 多专家实验中的人工/预标注修正流程；
3. 公开数据集协议中可获得的时间；
4. 无真实时间时使用匿名化相对成本；
5. 在论文主结果中同时报告无量纲成本和分钟成本敏感性。

建议基准相对成本：

```text
presence = 1
ordinal burden = 2
exact count = 4
quadrant count = 5
point annotation = 6
pixel mask = 10
anatomy + lesion relational annotation = 12
```

这些初值只用于开发，正式论文必须：

- 由公开时间校准；
- 做 0.5×、1×、2× 敏感性；
- 报告不同成本模型下所选方案的 Jaccard 稳定性。

## 10.4 不稳定性成本

对多专家标注计算：

- presence agreement；
- count-bin agreement；
- affected-quadrant agreement；
- lesion detection agreement；
- pixel IoU；
- boundary distance。

将不稳定性定义为：

\[
v_j=1-\operatorname{agreement}(q_j)
\]

或使用归一化方差。主结果不应只给单一加权和，还应报告：

```text
cost – stability – guideline coverage
```

三目标 Pareto 前沿。

## 10.5 现有数据支持矩阵

创建：

```text
data/manifests/dataset_operator_support.parquet
```

列：

```text
dataset_id
operator_id
support_level ∈ {FULL, PARTIAL, WEAK, NONE}
label_definition
known_ambiguity
sample_count
positive_count
license_constraint
```

示例：

| 数据集 | `nv_presence` | `nv_mask` | `vb_quadrants` | `quality_overall` |
|---|---:|---:|---:|---:|
| MMRDR-CFP/UWF | FULL | NONE | PARTIAL（VB/IRMA 合并） | PARTIAL |
| FGADR | FULL | FULL | NONE | NONE |
| Retinal-Lesions | FULL | FULL | NONE | NONE |
| DeepDRiD | UNKNOWN | NONE | NONE | FULL |
| MAPLES | PARTIAL/稀少 | FULL/稀少 | NONE | PARTIAL |

---

# 11. G2LC 编译器实现

## 11.1 朴素状态对集合覆盖

定义指南需要区分的状态对：

\[
U=\{(e,e'):\exists g\in\mathcal G,\ g(e)\neq g(e')\}.
\]

算子 \(q_j\) 可区分状态对 \(u=(e,e')\)，当：

\[
q_j(e)\neq q_j(e').
\]

二进制变量 \(z_j\) 表示是否选择算子：

\[
\min \sum_j c_jz_j
\]

约束：

\[
\forall u\in U,\quad
\sum_{j:q_j(e)\neq q_j(e')}z_j\ge1.
\]

这是加权 test cover / hitting set 形式。

## 11.2 防止状态空间爆炸的主算法

不应枚举全部 \(\mathcal E\times\mathcal E\)。使用**主问题 + SMT 分离 oracle**：

1. CP-SAT 根据当前反例集合求候选方案 \(S\)；
2. Z3 搜索：
   \[
   \exists e,e',g:
   \phi_S(e)=\phi_S(e')\land g(e)\neq g(e');
   \]
3. 若 SAT，得到反例状态对；
4. 为该反例加入“至少一个算子必须区分它”的约束；
5. 重复；
6. 若 UNSAT，方案获得可执行性证书。

伪代码：

```python
counterexamples = []
while True:
    selected = solve_master_cp_sat(counterexamples, costs)
    ce = z3_find_counterexample(selected, guidelines, ontology)
    if ce is None:
        return ExecutableCertificate(selected, counterexamples)
    counterexamples.append(ce)
```

## 11.3 精确求解器

使用 OR-Tools CP-SAT：

- 二进制算子变量；
- 推导支配约束；
- 必须/禁止算子；
- 许可约束；
- 模态约束；
- 预算约束；
- 多目标字典序：
  1. 可执行；
  2. 最小成本；
  3. 最小不稳定性；
  4. 最少算子数。

输出：

```json
{
  "status": "OPTIMAL",
  "selected_operators": [],
  "objective": {},
  "supported_guidelines": [],
  "counterexamples_resolved": 0,
  "solver_stats": {},
  "certificate_hash": "..."
}
```

## 11.4 贪心近似

每轮选择单位成本下区分剩余状态对最多的算子：

\[
q^\star=
\arg\max_q
\frac{|\operatorname{cover}(q)\cap U_{\text{uncovered}}|}
{c_q+\lambda v_q}.
\]

必须报告：

- 与精确解的成本差；
- 指南覆盖差；
- 运行时间；
- 大规模状态空间的扩展性。

## 11.5 推导支配消除

若算子 \(q_a\) 总能推导 \(q_b\)，且：

\[
c_a\le c_b,
\]

则 \(q_b\) 在相同约束下被支配，可预先删除。

但若 \(q_a\) 的稳定性更差或许可不同，不可简单删除。

## 11.6 最小缺失证据

给定现有算子 \(S_0\)：

- 固定 \(z_j=1\) 对所有 \(q_j\in S_0\)；
- 优化额外算子；
- 使用 Z3 unsat core 或反例归因生成解释。

证书示例：

```yaml
status: NOT_EXECUTABLE
guideline: icdr
version: "2003-frozen"
failed_rules:
  - severe_npdr_421
missing_predicates:
  - venous_beading_quadrants
  - irma_quadrants
minimal_additions:
  - operator: vb_quadrant_presence
  - operator: irma_affected_quadrants
counterexample:
  state_a:
    vb_quadrants: 1
  state_b:
    vb_quadrants: 2
  observed_equal_under_current_scheme: true
  action_a: moderate_npdr
  action_b: severe_npdr
```

## 11.7 规范外检测

编译指南前执行：

1. DSL schema 验证；
2. 谓词是否存在；
3. 谓词是否在目标模态可观察；
4. 是否有候选算子；
5. 现有数据是否支持训练/推导；
6. 是否依赖外部临床变量。

状态：

```text
EXECUTABLE
EXECUTABLE_WITH_ABSTENTION
MISSING_EVIDENCE
OUT_OF_SPEC
INVALID_GUIDELINE
```

## 11.8 证书 soundness

自动验证：

- `EXECUTABLE`：Z3 不得找到反例；
- `MISSING_EVIDENCE`：提供的反例必须在当前方案观测相同、行动不同；
- `minimal_additions`：添加后无反例；删除其中任一必要项应恢复反例，或说明存在多个等价最小解；
- `OUT_OF_SPEC`：缺失谓词必须确实不存在或不可观察。

---

# 12. 理论与软件测试义务

## 12.1 建议理论命题

### Proposition 1：可执行性等价条件

证明：

\[
g=h_g\circ\phi_S
\]

与“\(\phi_S\) 的每个等价类内 \(g\) 恒定”等价。

### Proposition 2：单调性

若 \(S\) 可执行，且 \(S\subseteq S'\)，则 \(S'\) 也可执行。

### Proposition 3：最小补充标注正确性

精确求解器返回的 \(\Delta S^\star\) 在给定有限算子集合和成本下为最优。

### Proposition 4：贪心近似界

在转换为加权集合覆盖且覆盖集合固定的条件下，给出标准对数近似界；若采用反例动态生成，明确界适用于最终显式反例全集或给出条件化说明。

### Proposition 5：规范外不可能性

若指南依赖证据语言中不存在且不可由现有模态观察/算子推导的谓词，则不存在仅基于当前 \(\phi_S\) 的确定执行器。

## 12.2 测试层级

### 单元测试

- DSL parser；
- predicate type；
- action priority；
- operator derivation；
- cost parser；
- certificate serializer。

### 属性测试

- 增加算子不会降低可执行性；
- 增加指南不会降低所需信息；
- 成本统一放大不改变最优集合；
- 被支配算子不应进入唯一最优解；
- 精确解成本不高于贪心解；
- 证书反例满足定义。

### 穷举对照

构造 3–8 个谓词的小型合成问题：

- 穷举所有算子子集；
- 与 CP-SAT 结果比较；
- 与 SMT 动态反例算法比较；
- 100% 一致后才进入真实指南。

### 故障注入

- 删除谓词；
- 修改阈值；
- 交换规则优先级；
- 产生冲突行动；
- 错误推导边；
- 许可禁用算子。

系统必须在测试中发现。


# 13. Oracle 实验：训练视觉模型之前的关键验证

## 13.1 目的

Oracle 阶段直接使用真实专家标注，不经过神经网络，用于回答：

- 指南是否被正确形式化；
- 哪些标注粒度真正足够；
- 像素掩膜是否为过度标注；
- 现有公开数据缺少什么；
- 同一图像在不同指南下为何产生不同结果；
- 标注不确定性是否会导致规则边界不稳定。

## 13.2 标注方案 S0–S6

从高粒度真值派生：

| 方案 | 内容 |
|---|---|
| S0 | 仅原始图像级 DR 等级 |
| S1 | 所有病灶存在性 |
| S2 | 存在性 + 有序病灶负担 |
| S3 | 数量区间 + 受累象限 |
| S4 | 精确计数 + 象限 + 解剖距离 |
| S5 | 完整像素掩膜 + 解剖结构 |
| S6 | G2LC 自动选出的最低成本方案 |

### 派生规则

- 连通域阈值必须按图像分辨率归一；
- 过小连通域的处理做敏感性分析；
- MA 与小出血的合并/拆分应遵循数据定义；
- 象限坐标系由 fovea 和 optic disc 定义；
- 黄斑距离以 optic-disc diameter 标准化；
- 无法区分的病灶输出 `uncertain`，不能强行二分类。

## 13.3 Oracle-P1：规则正确性

输入：

```text
人工构造证据状态
→ 指南 DSL
→ 行动
```

要求：

- 每条规则至少 5 个边界用例；
- 结果与原始指南人工核对；
- 规则覆盖率 100%；
- 冲突状态为 0；
- 所有拒识均有明确原因。

## 13.4 Oracle-P2：真实标注到指南

输入：

```text
专家掩膜/病灶标签
→ 标注算子派生
→ 指南执行
→ 与专家等级比较
```

分别在：

- MAPLES；
- IDRiD；
- FGADR；
- Retinal-Lesions；

上执行可支持的指南子集。

必须分开报告：

1. 指南在该数据上是否理论可执行；
2. Oracle 证据执行结果；
3. 视觉模型预测证据执行结果。

## 13.5 Oracle-P3：MAPLES/MESSIDOR 同病例跨指南

固定 198 张 MAPLES 图像：

- 输入不变；
- 原 MESSIDOR 等级不用于 Canadian 模型训练；
- Canadian 共识等级不用于超参数选择；
- 从专家证据分别执行 MESSIDOR 与 Canadian 规则；
- 比较以下基线。

基线：

1. `identity mapping`：同编号直接映射；
2. 经验混淆矩阵映射；
3. 原等级 → 目标等级的逻辑回归；
4. 每目标指南独立图像分类器；
5. 全病灶 + 手写规则；
6. G2LC 最小方案 + 规则；
7. G2LC 证据区间 + 选择性执行。

关键分析：

- MESSIDOR R2 在 Canadian 下变为 R1 的病例；
- 由“1 个出血/5 个 MA”与“至少 4 个出血”等规则差异造成的病例；
- 哪些病例仅凭原等级不可辨识；
- 哪个额外算子最能消除歧义。

## 13.6 Oracle-P4：标注预算曲线

对预算 \(B\)：

\[
B\in\{5\%,10\%,20\%,40\%,60\%,80\%,100\%\}
\]

比较：

- 全掩膜；
- 全存在性；
- 人工启发式；
- 随机同成本；
- 互信息；
- L1；
- 贪心 G2LC；
- 精确 G2LC。

报告：

- 可执行指南数；
- 可执行规则条款比例；
- Oracle GTE；
- Worst-Guideline Risk；
- 成本；
- 运行时间。

## 13.7 Oracle-P5：缺失证据故障注入

从完整算子集中依次删除：

- NV；
- VB 象限；
- IRMA 象限；
- 玻璃体出血；
- 图像质量；
- 黄斑位置；
- 出血数量区间。

评价：

- 系统是否判为不可执行；
- 缺失证据 precision/recall/F1；
- 最小补充集合是否包含被删除项或等价替代项；
- 证书反例是否有效。

## 13.8 Oracle Go/No-Go

### Go

满足以下多数条件：

- S6 明显低于 S5 成本；
- S6 Oracle 指南执行性能接近 S5；
- MAPLES 同病例实验优于等级映射；
- 缺失证据证书准确；
- 至少一套未见指南在证据语言内可执行；
- 对证据语言外规则能正确拒绝。

### No-Go / 修改范围

若出现：

- G2LC 总选择全部掩膜；
- Oracle 规则与专家等级严重不一致；
- MAPLES 证据不足以区分两个体系；
- 指南规则无法可靠形式化；
- 所有公开数据均缺乏核心谓词；

则采取：

1. 缩小指南族；
2. 将硬规则改为区间/三值逻辑；
3. 聚焦 R0–R2 或 referable DR；
4. 将“完整分级”改为“指南条款可执行性”；
5. 增加 Retinal-Lesions/FGADR；
6. 仅在证据可支持的子规则上作结论。

---

# 14. 视觉证据预测模型

## 14.1 设计原则

- 主模型只预测标准化证据，不直接绕过证据接口输出最终目标指南等级。
- 直接等级分类头仅作为基线和消融。
- 使用标准架构，避免论文退化为网络结构创新。
- 每个标签只在真实标注存在时计算损失。
- 存在性、数量、象限和掩膜应利用可推导一致性，但不得把伪标签当真实标签。

## 14.2 模型组成

### M1：图像质量模型

数据：

- DeepDRiD 常规眼底质量；
- 可选人工合成退化。

输出：

```text
gradable
overall_quality
artifact
clarity
field_definition
macula_visible
optic_disc_visible
```

推荐：

- ConvNeXt-Tiny；
- Swin-Tiny；
- RETFound 线性探测/微调作为强基线。

### M2：图像级病灶存在性/负担模型

数据：

- MMRDR-CFP/UWF；
- FGADR；
- Retinal-Lesions；
- DDR/IDRiD 派生存在性。

输出：

```text
MA
HE
hard_exudate
CWS
VB_or_IRMA
IRMA
NV
VH
preretinal_hemorrhage
fibrous_proliferation
RD
```

注意不同数据集输出空间不同，使用标签掩码和层级标签。

### M3：病灶分割模型

训练数据：

- DDR；
- IDRiD；
- FGADR；
- Retinal-Lesions；
- MAPLES 只用于固定 Oracle/外部测试时，不进入主模型调参。

推荐架构：

1. 标准 SegFormer-B2；
2. U-Net/UNet++；
3. HACDR-Net 作为近三年强基线；
4. MAPLES 官方 fundus-lesions-toolkit 作为工具基线。

输出：

- MA；
- HE；
- EX；
- CWS；
- IRMA；
- NV；
- 其他高级病灶在样本足够时加入。

### M4：解剖模型

输出：

- optic disc；
- fovea/macula；
- retinal ROI；
- 可选 vessel map。

数据：

- IDRiD；
- MAPLES；
- 其他公开解剖数据只作预训练。

## 14.3 推荐训练策略

### 图像级任务

参考配置：

```yaml
input_size: 512
optimizer: AdamW
learning_rate: 1.0e-4
weight_decay: 0.01
epochs: 100
warmup_epochs: 5
scheduler: cosine
batch_size_per_gpu: 32
mixed_precision: true
gradient_clip_norm: 1.0
early_stop_patience: 15
seeds: [17, 23, 42, 71, 101]
```

类别不平衡：

- class-balanced BCE；
- focal BCE；
- balanced sampler；
- 报告不使用重采样的消融。

### 分割任务

```yaml
input_size: 1024
crop_size: 768
optimizer: AdamW
learning_rate: 2.0e-4
weight_decay: 0.01
epochs: 120
batch_size_per_gpu: 4
loss:
  dice: 1.0
  focal: 1.0
  boundary: 0.2
```

小病灶：

- 正负 patch 平衡；
- lesion-centered crop；
- whole-image validation；
- lesion-level 指标优先于像素 accuracy。

### 基础模型

至少比较：

- ImageNet ConvNeXt-T；
- RETFound；
- FLAIR；
- UrFound（若 CFP 权重和代码可用）。

统一：

- 相同训练/验证划分；
- 相同输入尺寸或同时报告原生尺寸；
- 相同下游头；
- 区分 linear probe 与 full fine-tune；
- 不用目标域标签选超参数。

## 14.4 异构监督

对样本 \(i\)、任务 \(t\)：

\[
\mathcal L_i=
\sum_t m_{it}w_t\mathcal L_{it}.
\]

层级一致性：

- `mask present → presence positive`；
- `count > 0 → presence positive`；
- `affected_quadrants > 0 → presence positive`；
- `NV positive → high-grade evidence possible`，但不直接强制最终等级。

弱标签只约束允许集合。例如 MMRDR `VB/IRMA=1`：

\[
P(VB\lor IRMA)=1,
\]

不能分别将 VB、IRMA 都置为 1。

## 14.5 禁止捷径

主 G2LC 模型中：

- 不允许 RGB 特征直接连到最终指南等级头；
- 最终行动只能由证据集合和规则产生；
- 可在消融中加入 `bypass head`，用于证明捷径在未见指南上的失效。

## 14.6 模型选择

模型选择指标：

- 平均病灶 AUPRC；
- 稀有高级病灶 AUPRC；
- ECE/Brier；
- 最差数据域性能；
- 不使用目标指南等级。

不得只按源域分级 accuracy 选模型。

---

# 15. 证据校准、集合预测与选择性行动

## 15.1 为什么需要集合

指南常用硬阈值，而视觉预测靠近阈值时不应强制判断。例如：

```text
预测出血数量区间 = {1–3, 4–19}
Canadian 阈值 = 4
```

此时行动可能同时是 R1 与 R2，系统应拒识并请求确认出血数量。

## 15.2 校准方法

主实现：

- 温度缩放；
- isotonic regression；
- split conformal；
- deep ensemble 作为强但昂贵基线。

校准集必须来自源域验证集，不能使用 MAPLES Canadian 目标标签。

## 15.3 证据集合

分类谓词：

```text
Gamma_p(x) = conformal prediction set
```

有序数量：

```text
Gamma_count(x) = contiguous ordinal interval
```

分割派生量：

- 对多个模型/增强采样；
- 计算连通域数量、象限和距离分布；
- 构造分位数区间。

联合集合不应简单假设谓词独立。最低可行实现：

- 保留 top-k 联合样本；
- 或对每个规则涉及的谓词做保守笛卡尔积；
- 报告保守性导致的 coverage 损失。

## 15.4 行动投影

```python
actions = {guideline(state) for state in evidence_set}
if len(actions) == 1:
    return CertifiedAction(actions.pop())
return Abstain(
    possible_actions=actions,
    resolving_queries=rank_queries(evidence_set, guideline),
)
```

## 15.5 最有价值的确认证据

对候选查询 \(q\)，计算其对行动集合的期望缩减：

\[
\operatorname{VOI}(q)=
|A_g(x)|-
\mathbb E_{q}
[|A_g(x)\mid q|].
\]

优先建议：

- 最能消除行动歧义；
- 成本最低；
- 观察者稳定性最高；

的证据查询。

## 15.6 安全输出结构

```json
{
  "status": "ABSTAIN",
  "guideline": "canadian",
  "version": "frozen-v1",
  "possible_actions": ["R1", "R2"],
  "uncertain_evidence": [
    {
      "predicate": "hem_count_bin",
      "possible_values": ["1-3", "4-19"]
    }
  ],
  "recommended_confirmation": "confirm hemorrhage count bin",
  "evidence_model_version": "...",
  "certificate_hash": "..."
}
```

---

# 16. 全部实验协议

## P0：规则与编译器正确性

### 目标

证明软件与形式定义一致。

### 数据

合成证据状态、人工边界用例。

### 方法

- 穷举；
- CP-SAT；
- 贪心；
- SMT 反例生成。

### 指标

- exact match；
- 最优成本；
- 证书 soundness；
- 运行时间；
- 内存。

### 通过标准

- 小型问题精确解与穷举 100% 一致；
- 所有 `EXECUTABLE` 证书无法被 Z3 找到反例；
- 故障注入全部被发现。

## P1：指南族到标注设计

### 目标

回答不同指南族需要什么标注。

### 指南集合

```text
{MESSIDOR}
{Canadian}
{ICDR}
{NHS 2025}
{MESSIDOR, Canadian}
{ICDR, NHS 2025}
{全部}
```

### 输出

- 最小算子集；
- 成本；
- 共享算子；
- 每增加一套指南的边际成本；
- 不可执行条款；
- 最小补充证据。

## P2：Oracle 标注充分性

### 目标

不经过模型验证 S0–S6。

### 数据

MAPLES、IDRiD、FGADR、Retinal-Lesions。

### 指标

- Oracle GTE；
- Executability Rate；
- Certificate Coverage；
- Annotation Cost；
- Rule Violation；
- action agreement。

## P3：同病例多指南

### 目标

隔离标签语义变化。

### 数据

MAPLES/MESSIDOR 198 张。

### 划分

全部固定外部测试；不得用于选择模型/成本权重。

### 比较

- 等级直接映射；
- 混淆矩阵映射；
- 独立分类器；
- 多头模型；
- CBM；
- DAPHNE-style；
- G2LC Oracle；
- G2LC predicted evidence；
- G2LC + abstention。

## P4：端到端证据执行

### 目标

评价从图像到证据到行动。

### 训练

DDR/MMRDR-CFP、IDRiD、FGADR/Retinal-Lesions、DeepDRiD。

### 测试

- 源域官方测试；
- MAPLES；
- MMRDR-UWF；
- DeepDRiD UWF。

### 误差分解

```text
GT evidence → rule
Pred evidence → rule
RGB → direct grade
```

## P5：未见指南

### 目标

验证冻结模型后的规则迁移。

### 协议

- 训练/开发只使用 MESSIDOR、Canadian、ICDR 中的部分；
- NHS DES 2025 规则文件在最终测试阶段才加载；
- 不用 NHS 行动标签训练图像模型；
- 若证据不全，允许输出缺失证据或拒识。

### 评价

- GTE；
- WGR；
- Certified Case Coverage；
- Out-of-Spec F1；
- 与每指南重训模型比较。

## P6：规范外与缺失证据

### 目标

证明系统不会对超范围指南强制预测。

### 人为指南

加入：

- OCT 中央厚度；
- 视力；
- 既往激光治疗史；
- 荧光素渗漏；
- 未定义新谓词。

### 指标

- `OUT_OF_SPEC` precision/recall/F1；
- missing predicate exact match；
- minimal repair cost；
- false executable rate，目标为 0。

## P7：多专家稳定性

### 数据

51 张 MAPLES 多专家子集。

### 方法

对每名专家独立派生：

- presence；
- count bin；
- quadrant；
- mask。

### 比较

- 仅成本 G2LC；
- 成本 + 稳定性 G2LC；
- 全掩膜；
- 存在性。

### 指标

- 所选方案 Jaccard；
- action disagreement；
- decision variance；
- selective risk；
- 标注成本。

## P8：预算与成本敏感性

### 成本配置

- 相对成本；
- MAPLES 时间校准；
- 0.5×/1×/2×；
- 高/中/低专家不稳定性权重。

### 输出

- Cost–Coverage curve；
- Cost–GTE curve；
- Pareto front；
- 最优方案稳定性。

## P9：跨图像域与质量退化

### 训练/测试

- CFP → UWF；
- DDR/MMRDR-CFP → IDRiD/MAPLES；
- leave-one-dataset-out；
- 清晰 → 合成模糊/曝光/遮挡；
- DeepDRiD 质量子组。

### 重点

该协议检验图像域偏移，不与指南偏移混为一谈。


# 17. 近三年方法对比：选择原则、复现等级与完整基线矩阵

## 17.1 时间窗口与纳入原则

本文把“近三年”固定为：

> **2023-08-20 至 2026-08-20**

为避免遗漏直接定义本研究边界的工作，额外保留一项窗口外的必选概念基线：DAPHNE（2021）。

纳入主结果表的方法必须至少满足一项：

1. 与 DR 分级、病灶证据、概念推理、跨域泛化或视网膜基础模型直接相关；
2. 有官方代码，能够在本研究统一划分上重跑；
3. 虽无官方代码，但与 G2LC 的核心主张直接碰撞，必须进行忠实重实现；
4. 发表在 KBS 或近三年高影响力医学影像/AI 会议期刊，可用于说明当前技术边界。

不采用以下不规范比较方式：

- 从论文中抄录不同数据划分、不同预处理和不同指标的数字，与本方法直接排一张表；
- 为无代码方法猜测实现细节；
- 在目标测试集上调参后仍称为“未见域”或“未见指南”；
- 只选择弱基线，不比较 RETFound、FLAIR、GDRNet、DECO、DG-ADR 等强方法；
- 将 KBS 论文列入参考文献，却不解释本研究与其差异。

## 17.2 复现等级

| 等级 | 定义 | 允许进入的表格 |
|---|---|---|
| **R1：官方复现** | 使用作者官方代码/权重；仅修改数据适配层和统一评价脚本 | 主结果表、补充材料 |
| **R2：忠实重实现** | 无官方代码或代码不可运行；按论文和补充材料实现，记录所有假设 | 主结果表，但标注 `reimplementation` |
| **R3：文献背景** | 数据、代码或关键细节不足，无法公平重跑 | 相关工作/讨论，不与实验数字直接排名 |

每个 R1/R2 方法必须保存：

```text
baseline_name
paper_version
official_repo_commit
local_patch_commit
training_config_hash
dataset_manifest_hash
split_hash
seed
checkpoint_sha256
metric_code_hash
```

## 17.3 近三年重点方法清单

> “必须”表示进入至少一个统一实验；“建议”表示资源允许时加入；“背景”表示不直接用异构论文数字排名。

| ID | 方法 | 年份/来源 | 任务与意义 | 官方代码/来源 | 复现等级 | 本文角色 |
|---|---|---:|---|---|---|---|
| R-00 | **DAPHNE** | 2021, *Eye* | 病灶/解剖特征后执行 ICDRS 与 UK NSC；证明“切换分级标准”本身不是新意 | https://www.nature.com/articles/s41433-021-01415-2 | R2 | **必须，最直接概念基线** |
| R-01 | **RETFound** | 2023, *Nature* | 视网膜基础模型；强视觉编码器 | https://github.com/RViMLab/RETFound_MAE | R1 | **必须** |
| R-02 | **GDRNet** | 2023, MICCAI | 多源 DR 域泛化基准与方法 | https://github.com/chehx/DGDR | R1 | **必须** |
| R-03 | Lesion-aware Contrastive Learning | 2023, MICCAI | 病灶感知 DR 表征 | https://conferences.miccai.org/2023/papers/383-Paper1429.html | R1/R2 | 建议 |
| R-04 | **UrFound** | 2024, MICCAI | 多模态视网膜基础模型与领域知识预训练 | https://github.com/yukkai/UrFound | R1 | 建议/强编码器 |
| R-05 | **CLIP-DR** | 2024, MICCAI | 文本知识、排序提示、GDRBench | https://github.com/Qinkaiyu/CLIP-DR | R1 | **必须，知识型分级基线** |
| R-06 | **DECO** | 2024, MICCAI | 解耦表示的未见域泛化 | https://github.com/richard-peng-xia/DECO | R1 | **必须** |
| R-07 | **CauDR** | 2024, *Computers in Biology and Medicine* | 因果启发的 DR 域泛化 | DOI: 10.1016/j.compbiomed.2024.108459 | R2/R3 | 建议；不能假称官方复现 |
| R-08 | **ConceptExplanations-DR** | 2024, MELBA | TCAV 与概念瓶颈 DR 分类 | https://github.com/andreastoraas/conceptexplanations_dr_grading | R1 | **必须，概念基线** |
| R-09 | **HACDR-Net** | 2024, AAAI | DR 多病灶分割 | 论文：https://ojs.aaai.org/index.php/AAAI/article/view/28453 | R1/R2 | **必须或用官方实现替代** |
| R-10 | **FLAIR** | 2025, *Medical Image Analysis* | 视网膜图文基础模型 | https://github.com/jusiro/FLAIR | R1 | **必须，视觉语言基础模型** |
| R-11 | **DG-ADR** | 2025, WACV | 生成式增强与 DR 域泛化 | https://github.com/sharonchokuwa/dg-adr | R1 | **必须** |
| R-12 | KBS model-based ensemble | 2025, KBS | DR 模型集成，文章号 114581 | DOI: 10.1016/j.knosys.2025.114581 | R2/R3 | **必须解释差异；可做简化重实现** |
| R-13 | KBS multi-granularity feature alignment | 2025, KBS | 医学图像无监督域适应 | KBS 2025 论文 | R3/R2 | 背景；若任务接口适配则建议 |
| R-14 | **MMRDR 官方基准** | 2026, *Scientific Data* | ResNet-50、ViT、RETFound、FLAIR 等统一技术验证 | https://github.com/Vladimirovich2019/MMRDR_Evaluation | R1 | **必须复用评价代码** |
| R-15 | **VLM-GCR** | 2026, AAAI | VLM 引导病灶概念图推理与干预 | https://ojs.aaai.org/index.php/AAAI/article/view/39948 | R2/R3 | **必须作为最近的概念碰撞** |
| R-16 | ProME-DR | 2026, AAAI | 零样本 DR 分级 | AAAI 2026 proceedings | R3 | 背景/可选 |

### 复现优先级

资源有限时按以下顺序执行：

1. ResNet-50、ConvNeXt-T、Swin-T 直接分级；
2. RETFound；
3. GDRNet；
4. DECO；
5. DG-ADR；
6. CLIP-DR；
7. FLAIR；
8. ConceptExplanations-DR/标准 CBM；
9. DAPHNE-style；
10. HACDR-Net 或等价官方多病灶分割基线；
11. VLM-GCR 忠实重实现，仅在细节足够时进入主表。

## 17.4 按科学问题组织的基线组

### B-G：直接分级与基础模型

| 编号 | 方法 | Backbone | 输出 | 公平性要求 |
|---|---|---|---|---|
| B-G0 | ResNet-50 ERM | ResNet-50 | 五级 Softmax | 统一数据、输入、增强 |
| B-G1 | ConvNeXt-T ERM | ConvNeXt-T | 五级 Softmax | 同上 |
| B-G2 | Swin-T ERM | Swin-T | 五级 Softmax | 同上 |
| B-G3 | CORAL ordinal | 与 B-G1 相同 | 有序阈值 | 比较 Softmax 与有序学习 |
| B-G4 | RETFound fine-tune | 官方 ViT-L/可用权重 | 等级 | 官方权重，统一下游划分 |
| B-G5 | FLAIR linear probe | 官方视觉编码器 | 等级 | 冻结编码器 |
| B-G6 | FLAIR fine-tune | 官方模型 | 等级 | 记录显存与参数量 |
| B-G7 | CLIP-DR | 官方实现 | 等级 | 按 GDRBench 设置适配 |
| B-G8 | KBS ensemble-style | 多个统一基模型 | 等级 | 只用训练/验证集选权重 |

### B-D：域泛化

| 编号 | 方法 | 说明 |
|---|---|---|
| B-D0 | ERM multi-source | 统一多源训练下限 |
| B-D1 | MixStyle | 经典轻量 DG 基线 |
| B-D2 | GDRNet | 2023 DR 专用 DG |
| B-D3 | DECO | 2024 DR 解耦 DG |
| B-D4 | CauDR-reimpl | 因果 DG，明确重实现 |
| B-D5 | DG-ADR | 2025 DR 专用 DG |

### B-E：病灶证据预测

| 编号 | 方法 | 任务 |
|---|---|---|
| B-E0 | U-Net | 四/六类病灶分割 |
| B-E1 | SegFormer-B2 | 多病灶分割 |
| B-E2 | HACDR-Net | 近三年强分割方法 |
| B-E3 | RETFound encoder + segmentation head | 基础模型编码器 |
| B-E4 | Image-level multi-label ConvNeXt | 存在性/负担 |
| B-E5 | MMRDR 官方分类基准 | 七类存在性 |

### B-K：知识、概念与规则

| 编号 | 方法 | 与 G2LC 的差别 |
|---|---|---|
| B-K0 | Standard CBM | 预测固定概念再预测等级；不设计标注体系 |
| B-K1 | Concept Embedding Model | 柔性概念表示；无指南可执行证书 |
| B-K2 | ConceptExplanations-DR | 近年公开 DR 概念基线 |
| B-K3 | DAPHNE-style | 固定病灶特征映射到多套等级；不反向求最小标注 |
| B-K4 | VLM-GCR-reimpl | 病灶概念图推理；不解决指南到标注编译 |
| B-K5 | All-evidence + rule | 使用所有可得病灶；测试 G2LC 是否减少成本 |
| B-K6 | Grade-to-grade mapping | 从源等级直接映射目标等级；同病例跨指南弱基线 |
| B-K7 | Per-guideline classifier | 每套指南独立重训；对比零重训规则加载 |
| B-K8 | Multi-head classifier | 一个编码器、每套指南一个输出头；无法处理真正未见指南 |

### B-A：标注设计与选择

| 编号 | 方法 | 说明 |
|---|---|---|
| B-A0 | All pixel masks | 成本最高的“全标注”上界 |
| B-A1 | All presence labels | 便宜但可能不可执行 |
| B-A2 | Clinician/manual heuristic | 按指南人工挑选证据 |
| B-A3 | Random same-cost | 同预算随机选择 |
| B-A4 | Mutual Information | 基于训练标签的特征选择 |
| B-A5 | L1 sparse selector | 稀疏预测特征选择 |
| B-A6 | Greedy set cover | 不含推导格与稳定性的基础版本 |
| B-A7 | **G2LC exact** | CP-SAT/SMT 精确解 |
| B-A8 | **G2LC scalable** | 反例分离 + 贪心/近似解 |

### B-S：安全与拒识

| 编号 | 方法 | 说明 |
|---|---|---|
| B-S0 | Forced prediction | 无拒识 |
| B-S1 | Max-softmax threshold | 普通置信阈值 |
| B-S2 | Deep ensemble threshold | 模型不确定性 |
| B-S3 | Evidence interval + rule projection | 证据集合投影 |
| B-S4 | G2LC certificate | 集合投影 + 缺失/规范外证书 |

## 17.5 公平比较规范

1. **相同训练样本与划分**：同一实验组中，不因方法而增加目标域或目标指南标签。
2. **相同预处理**：除官方模型强制输入规格外，裁剪、归一化和增强保持一致。
3. **相同模型选择信息**：未见指南/域的测试标签不得用于早停、阈值或超参数选择。
4. **相同指标实现**：统一调用 `g2lc.metrics`；MMRDR 任务可交叉核对官方代码。
5. **相同随机种子**：默认 `{17, 29, 43, 71, 101}`。
6. **相同患者级划分**：有患者 ID 时严格按患者；没有时明确标注为图像级限制。
7. **参数量与算力透明**：报告可训练参数、FLOPs、GPU 小时和峰值显存。
8. **不将无法复现论文数字放入公平排名**：R3 仅在独立的 literature context 表中列出。

---

# 18. 主实验矩阵与运行编号

## 18.1 数据角色冻结

| 数据 | 训练 | 验证 | 最终测试 | 说明 |
|---|---:|---:|---:|---|
| DDR/MMRDR-CFP 家族 | ✓ | ✓ | 可做源内 | 必须去重并作为同一来源家族 |
| IDRiD | ✓ | ✓ | leave-one-domain-out 时为测试 | 病灶与解剖证据 |
| FGADR | ✓ | ✓ | 可做外域 | IRMA/NV 像素监督 |
| Retinal-Lesions | ✓ | ✓ | 可做高级病灶外测 | 申请成功后使用 |
| DeepDRiD regular | ✓ | ✓ | ✓ | 质量与双视野 |
| DeepDRiD UWF | 否或仅扩展 | 否 | ✓ | 独立成像域 |
| MMRDR-UWF | 否或仅扩展 | 否 | ✓ | 独立 UWF 队列 |
| MAPLES/MESSIDOR | **否** | **否** | **全部冻结测试** | 同病例多指南核心测试 |
| MAPLES 51 多专家子集 | 否 | 否 | ✓ | 稳定性测试 |

> 最终主结果提交前，不得查看 MAPLES 目标指南标签来选模型、成本权重或证据阈值。

## 18.2 核心运行组

### EX00：编译器正确性

```text
EX00-SYN-EXACT
EX00-SYN-GREEDY
EX00-SYN-MISSING
EX00-SYN-OOS
EX00-SCALE-N_GUIDELINES-{2,4,8,16,32}
EX00-SCALE-N_OPERATORS-{10,25,50,100,250}
```

### EX01：指南到标注方案

```text
EX01-MESSIDOR
EX01-CANADIAN
EX01-ICDR
EX01-NHS2025
EX01-ALL_GUIDELINES
EX01-HOLDOUT_NHS2025
```

每个运行输出：

- 最小算子集合；
- 总成本；
- 指南/条款覆盖；
- 求解时间；
- optimality gap；
- 证书 JSON；
- 未覆盖状态对/反例。

### EX02：Oracle 证据充分性

```text
EX02-S0-GRADE_ONLY
EX02-S1-PRESENCE
EX02-S2-BURDEN
EX02-S3-COUNT
EX02-S4-QUADRANT
EX02-S5-SPATIAL
EX02-S6-FULL_MASK
EX02-G2LC-MINIMUM
```

### EX03：同病例跨指南

```text
EX03-MESSIDOR_TO_CANADIAN-GRADE_MAP
EX03-MESSIDOR_TO_CANADIAN-PER_GUIDELINE
EX03-MESSIDOR_TO_CANADIAN-CBM
EX03-MESSIDOR_TO_CANADIAN-DAPHNE
EX03-MESSIDOR_TO_CANADIAN-G2LC_ORACLE
EX03-MESSIDOR_TO_CANADIAN-G2LC_PRED
```

### EX04：视觉证据模型

```text
EX04-QUALITY-CONVNEXT
EX04-EVIDENCE-CONVNEXT
EX04-EVIDENCE-RETFOUND
EX04-EVIDENCE-FLAIR
EX04-SEG-UNET
EX04-SEG-SEGFORMER
EX04-SEG-HACDR
EX04-ANATOMY-SEGFORMER
```

### EX05：端到端指南执行

```text
EX05-{BACKBONE}-{GUIDELINE}-{DOMAIN}-{SEED}
```

其中：

```text
BACKBONE ∈ {convnext, retfound, flair}
GUIDELINE ∈ {messidor, canadian, icdr, nhs2025}
DOMAIN ∈ {source, idrid, maples, deepdrid, mmrdr_uwf}
SEED ∈ {17,29,43,71,101}
```

### EX06：近三年强基线

```text
EX06-ERM
EX06-RETF0UND
EX06-GDRNET
EX06-CLIPDR
EX06-DECO
EX06-DGADR
EX06-FLAIR
EX06-CBM
EX06-DAPHNE
EX06-VLMGCR_REIMPL
```

### EX07：证书与拒识

```text
EX07-FORCED
EX07-MSP
EX07-ENSEMBLE
EX07-EVIDENCE_SET
EX07-G2LC_CERT
EX07-OOS_INJECTION
EX07-MISSING_OPERATOR_INJECTION
```

### EX08：成本与稳定性

```text
EX08-COST_ONLY
EX08-COST_STABILITY
EX08-RELATIVE_COST
EX08-TIME_CALIBRATED_COST
EX08-WEIGHT_SWEEP
EX08-MULTIEXPERT
```

### EX09：图像域泛化

```text
EX09-ERM
EX09-GDRNET
EX09-DECO
EX09-CAUDR_REIMPL
EX09-DGADR
EX09-G2LC_EVIDENCE
```

---

# 19. 完整消融实验

## 19.1 编译器消融

| ID | 消融 | 改动 | 验证问题 | 主要指标 |
|---|---|---|---|---|
| A01 | 无算子推导格 | 把每个算子视为独立 | 推导关系是否减少冗余标注 | cost、coverage |
| A02 | 仅存在性 | 禁止数量/象限/位置 | 便宜标签是否足够 | executability、GTE |
| A03 | 无成本 | 所有算子成本相同 | 成本建模的必要性 | 实际估计工时 |
| A04 | 无稳定性项 | 只最小化成本 | 是否会选择专家一致性差的算子 | disagreement、WGR |
| A05 | 无证据不确定性 | 点预测硬执行 | 集合语义是否降低危险错误 | selective risk |
| A06 | 全状态枚举 vs 反例分离 | 两种算法 | 可扩展性与正确性 | runtime、gap |
| A07 | 精确 vs 贪心 | CP-SAT 与贪心 | 近似方法损失 | optimality gap |
| A08 | 无支配消除 | 保留冗余算子 | 预处理是否关键 | runtime、选集大小 |
| A09 | 硬规则 | 不使用 UNKNOWN/区间 | 三值语义是否必要 | false executable rate |
| A10 | 无规范外检测 | 未知谓词强行忽略 | 规范外证书是否必要 | OOS F1、unsafe error |
| A11 | 无缺失证据最小化 | 只报告“不可执行” | 最小修复建议的价值 | exact set match、cost |
| A12 | 单指南设计 | 每次只考虑一个指南 | 指南族设计是否提高复用性 | marginal annotation cost |

## 19.2 数据与标签消融

| ID | 消融 | 验证问题 |
|---|---|---|
| A13 | 去掉 FGADR | IRMA/NV 像素标签对可执行性的贡献 |
| A14 | 去掉 Retinal-Lesions | 增殖期病灶标签的贡献 |
| A15 | 去掉 MMRDR 高级病灶存在性 | 七类病灶存在性是否必要 |
| A16 | 去掉 DeepDRiD 质量标签 | 质量证据对重拍/拒识的贡献 |
| A17 | 去掉 IDRiD 解剖标签 | 黄斑/视盘空间关系的贡献 |
| A18 | 将 UNKNOWN 错误设为 NEGATIVE | 展示异构监督错误处理造成的偏差 |
| A19 | 不做跨库去重 | 仅作为泄漏审计，不能作为合法主结果 |
| A20 | 只用一个数据集 | 异构专家证据是否提高概念覆盖 |

## 19.3 视觉模型消融

| ID | 消融 | 说明 |
|---|---|---|
| A21 | ImageNet vs RETFound vs FLAIR | 编码器选择 |
| A22 | 图像级存在性 vs 像素分割派生 | 标注粒度与性能成本 |
| A23 | 无有序负担头 | 只预测 presence |
| A24 | 无质量分支 | 所有图像强制判读 |
| A25 | 无解剖分支 | 不使用区域/位置 |
| A26 | 有/无数据集均衡采样 | 避免大库主导 |
| A27 | 有/无 masked heterogeneous loss | 验证缺失监督掩码 |
| A28 | 加直接等级旁路头 | 检验视觉捷径是否破坏证据忠实性 |
| A29 | 联合训练 vs 分阶段训练 | 证据任务相互干扰 |
| A30 | 单模型 vs deep ensemble | 证据集合校准 |

## 19.4 规则与指南消融

| ID | 消融 | 说明 |
|---|---|---|
| A31 | 训练时持有全部指南 | 上界，不是未见指南实验 |
| A32 | 持出 NHS 2025 | 核心未见指南 |
| A33 | 持出 Canadian | 检验另一真实指南 |
| A34 | 新旧版本变化 | 版本迁移 |
| A35 | 删除某一高级病灶谓词 | 自动生成最小缺失证据 |
| A36 | 人为加入 OCT/视力谓词 | 规范外检测 |
| A37 | 规则阈值扰动 | 对指南转写误差的敏感性 |
| A38 | 专家规则 vs 自动转写草案 | 证明不能直接信任 LLM 规则生成 |

## 19.5 对比和消融的最低发表集合

资源不足时，以下不可删除：

- B-G0/B-G4/B-G7；
- B-D2/B-D3/B-D5；
- B-K0/B-K3/B-K6/B-K7；
- B-A0/B-A1/B-A3/B-A6/B-A7；
- B-S0/B-S1/B-S4；
- A01/A02/A03/A04/A09/A10/A11/A18/A28/A32/A36；
- Oracle 与 Predicted evidence 两层结果。

---

# 20. 指标定义与计算规范

## 20.1 病灶与证据预测

### 图像级证据

- AUROC；
- AUPRC，作为稀有病灶首要指标；
- Macro-F1；
- per-class sensitivity/specificity；
- Brier Score；
- ECE；
- classwise ECE；
- calibration slope/intercept。

### 像素/病灶级证据

- Dice；
- IoU；
- AUPRC；
- lesion-level sensitivity；
- lesion-level F1；
- FROC；
- 固定每图假阳性数量下的灵敏度。

对 MA 等小病灶，禁止只报告 Dice 或像素 Accuracy。

## 20.2 DR 分级与行动

- Quadratic Weighted Kappa（主要等级指标）；
- MAE；
- Macro-F1；
- Balanced Accuracy；
- 各等级灵敏度；
- referable DR sensitivity/specificity；
- PDR sensitivity/specificity；
- confusion matrix。

## 20.3 G2LC 专用指标

### M1：Guideline Transport Error（GTE）

对目标指南 \(g\)：

\[
\mathrm{GTE}(g)=\frac{1}{N}\sum_{i=1}^{N}
\ell\big(\hat a_i^{(g)},a_i^{(g)}\big).
\]

动作是有序等级时使用归一化绝对距离；转诊/重拍时使用临床代价矩阵。

### M2：Worst-Guideline Risk（WGR）

\[
\mathrm{WGR}=\max_{g\in\mathcal G_{test}}\mathrm{GTE}(g).
\]

### M3：Guideline Executability Rate（GER）

\[
\mathrm{GER}=\frac{\#\text{完全可执行指南条款}}{\#\text{全部目标指南条款}}.
\]

同时报告 guideline-level 和 clause-level 两个版本。

### M4：Certified Case Coverage（CCC）

\[
\mathrm{CCC}=\frac{\#\{i:|A_g(x_i)|=1\ \land\ certificate\ valid\}}{N}.
\]

### M5：Selective Risk 与 AURC

在只自动处理覆盖率为 \(c\) 的病例上计算风险：

\[
R(c)=\mathbb E[\ell(\hat a,a)\mid accepted].
\]

报告 risk–coverage curve 与 AURC。

### M6：Annotation Cost–Guideline Coverage

横轴：总标注成本；纵轴：GER 或可支持的指南数量。报告：

- 曲线；
- 曲线下面积；
- 达到 80%/90%/100% 覆盖的最小成本；
- 相对全掩膜节省比例。

### M7：Missing-Evidence Accuracy

在故障注入中，真实缺失集合为 \(M\)，系统输出 \(\hat M\)：

- predicate precision/recall/F1；
- exact set match；
- minimal repair cost ratio；
- 是否包含非必要证据。

### M8：Out-of-Specification Detection

- OOS AUROC；
- precision/recall/F1；
- false executable rate；
- unsafe forced decision rate。

其中 **false executable rate 必须接近 0**。

### M9：Certificate Soundness

用独立 SMT 检查器验证：

\[
\mathrm{Soundness}=1-
\frac{\#\text{找到反例的“可执行”证书}}{\#\text{可执行证书}}.
\]

目标为 1.0。

### M10：Certificate Completeness

在可穷举小问题中，比较编译器与 brute force 真值：

- executable false negative rate；
- minimal set exact recovery；
- missing set exact recovery。

### M11：Solver Scalability

- wall-clock time；
- CPU/GPU memory；
- 迭代反例数量；
- 最终 optimality gap；
- 指南数/算子数/状态变量数增长曲线。

### M12：Selection Stability

不同成本权重、Bootstrap 病例和专家标注下，计算所选算子集合的：

- Jaccard similarity；
- inclusion frequency；
- rank stability；
- action variance。

### M13：Marginal Guideline Annotation Cost

新加入指南 \(g_{new}\) 的增量成本：

\[
\Delta C(g_{new})=C^*(\mathcal G\cup\{g_{new}\})-C^*(\mathcal G).
\]

它直接衡量标注体系对指南更新的复用能力。

## 20.4 主指标预注册

建议在完整实验前冻结：

1. Oracle MAPLES 同病例 Canadian GTE；
2. Predicted-evidence MAPLES Canadian GTE；
3. NHS 2025 held-out WGR；
4. 90% GER 所需标注成本；
5. OOS false executable rate；
6. CCC=80% 时的 selective risk。

其余指标标记为次要或探索性，避免事后挑指标。

---

# 21. 统计检验与不确定性报告

## 21.1 重复与置信区间

- 视觉模型：5 个随机种子；
- 编译器确定性算法：无需随机种子，但成本 Bootstrap 与贪心 tie-breaking 重复 100 次；
- 患者级 Bootstrap：2,000 次；
- 报告均值、标准差和 95% CI；
- 有患者 ID 时必须以患者为重采样单位。

## 21.2 配对检验

### 同病例 MAPLES

- 二分类行动：McNemar；
- QWK/MAE/GTE：paired bootstrap；
- 多个方法：先全局 Friedman，再做配对 Wilcoxon；
- 使用 Holm–Bonferroni 校正。

### 多域结果

- 对每个数据域的指标进行配对 Wilcoxon signed-rank；
- 同时报告平均域与最差域；
- 不只报告合并样本后的单一 p 值。

## 21.3 效应量

除 p 值外报告：

- 绝对 GTE 降低；
- 相对风险降低；
- QWK 差值；
- cost saving；
- Cliff’s delta 或配对效应量；
- NNT-style 的“每避免一次错误需要增加多少标注成本”，作为探索性解释。

## 21.4 多重比较

主比较提前固定：

1. G2LC vs DAPHNE-style；
2. G2LC vs per-guideline classifier；
3. G2LC vs all-evidence；
4. G2LC vs greedy no-lattice；
5. G2LC certificate vs max-softmax reject。

其他方法属于次要比较，统一做 Holm 校正。

## 21.5 禁止的数据窥视

- MAPLES 目标等级只能在最终评估脚本中读取；
- NHS held-out 规则可以在最终加载时读取，但其目标行动标签不能用于训练和调参；
- 外部测试数据不得参与归一化统计估计；
- 所有阈值由训练/验证域选择；
- 一旦打开锁定测试标签，必须记录时间、Git commit 和配置哈希。

---

# 22. 计算资源、实验登记与结果可追溯性

## 22.1 建议计算资源

### 最低配置

- 1× NVIDIA RTX 4090 24 GB；
- 128 GB RAM；
- 4 TB 可用 SSD；
- 16 CPU cores。

### 推荐配置

- 2–4× 24/48 GB GPU；
- 256 GB RAM；
- 8 TB SSD；
- 支持 Slurm 或容器化调度。

RETFound ViT-L 全量微调可能需要更大显存；资源不足时优先：

1. linear probe；
2. LoRA/adapter；
3. gradient accumulation；
4. 输入 512 而不是 1024；
5. 冻结大部分 backbone。

## 22.2 实验登记表

每次运行写入 `runs/run_registry.parquet`：

```yaml
run_id: EX05-retfound-canadian-maples-17
timestamp_utc: 2026-08-20T00:00:00Z
git_commit: ...
config_hash: ...
data_manifest_hash: ...
split_hash: ...
guideline_hash: ...
operator_catalog_hash: ...
seed: 17
host: ...
gpu: ...
status: running|completed|failed
checkpoint: ...
metrics_file: ...
stdout_log: ...
```

## 22.3 配置冻结

推荐 Hydra 配置结构：

```text
configs/
├── data/
├── model/
├── evidence/
├── guideline/
├── compiler/
├── calibration/
├── experiment/
└── hardware/
```

最终论文中的每一行结果必须能由：

```bash
uv run g2lc reproduce --table-id T3 --row-id R7
```

或等价脚本生成。

## 22.4 结果表生成

禁止手工复制数字到论文。统一：

```bash
uv run python scripts/build_paper_tables.py \
  --registry runs/run_registry.parquet \
  --output artifacts/tables

uv run python scripts/build_paper_figures.py \
  --registry runs/run_registry.parquet \
  --output artifacts/figures
```

---

# 23. 分阶段任务规划：任务、输入、输出与验收标准

> 下述周次是单人全职的建议节奏；多人协作可并行，但依赖关系不能跳过。任何阶段未通过验收，不进入下一阶段的大规模训练。

## 阶段 A：项目初始化与数据申请（第 1–2 周）

### A-01 建仓与环境

**任务**：

- 创建 `g2lc-dr` 仓库；
- 初始化 Python 3.11、`uv`、PyTorch、OR-Tools、Z3、Hydra；
- 建立 pre-commit、ruff、mypy、pytest；
- 创建 CI；
- 加入数据许可证与不上传原始数据的约束。

**输出**：

- `pyproject.toml`；
- `Makefile`；
- `.pre-commit-config.yaml`；
- `.github/workflows/ci.yml`；
- `README.md`；
- `STATUS.md`。

**验收**：

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest -q
```

全部通过。

### A-02 同时提交数据申请

按优先级：

1. MESSIDOR-1 原图；
2. FGADR Seg-set；
3. Retinal-Lesions；
4. 其他需要协议的数据。

**输出**：

- `docs/data_access_log.md`；
- 每个数据集申请日期、状态、许可、联系人；
- 不保存或公开私人邮件内容。

### A-03 下载公开数据与校验

- MMRDR；
- DDR；
- IDRiD；
- DeepDRiD；
- MAPLES 标签；
- MAPLES Python 包。

**验收**：

- 原始文件只读；
- 每个归档计算 SHA-256；
- `data/licenses.csv` 完整；
- `g2lc data audit` 能显示文件数与缺失项。

## 阶段 B：文献与主张冻结（第 1–3 周，可与 A 并行）

### B-01 近三年系统查新

检索：

```text
("clinical guideline" OR grading standard OR referral rule)
AND
(annotation design OR label design OR concept completeness OR executable)
AND
(medical imaging OR diabetic retinopathy)
```

数据库：

- Web of Science；
- Scopus；
- PubMed；
- Google Scholar；
- IEEE Xplore；
- ACM DL；
- ScienceDirect；
- arXiv；
- 专利数据库。

**输出**：

- `docs/novelty_matrix.csv`；
- 每项相邻工作是否涉及：指南族、标注反编译、成本、证书、同病例多指南、未见指南。

### B-02 Claim freeze

形成 `docs/claim_contract.md`：

- 可以说什么；
- 不能说什么；
- 每条 claim 需要的理论/实验支撑；
- 何时降级主张。

**验收**：

- DAPHNE、VLM-GCR、CBM、RETFound/FLAIR 与 G2LC 的边界清楚；
- 不再使用无证据的绝对“first”。

## 阶段 C：证据本体与指南 DSL（第 3–5 周）

### C-01 本体 schema

实现：

- `EvidencePredicate`；
- `Domain`；
- `ObservableModality`；
- `ValueType`；
- `ParentChildRelation`；
- `Provenance`。

**输出**：

- `knowledge/evidence_ontology.yaml`；
- JSON Schema；
- 语义校验器。

### C-02 指南 DSL

实现：

- AND/OR/NOT；
- 数值阈值；
- 象限数量；
- 三值逻辑；
- 规则优先级；
- 版本与来源；
- action/grade 输出。

### C-03 转写指南

依次：

1. MESSIDOR；
2. Canadian/MAPLES；
3. ICDR；
4. NHS DES 2025。

### C-04 指南单元测试

每条规则至少：

- 正例；
- 负例；
- 边界例；
- UNKNOWN 例；
- 冲突例。

**验收 Gate C**：

```bash
uv run g2lc guideline validate knowledge/guidelines
uv run pytest tests/guidelines -q
```

- 零未覆盖语法错误；
- 零内部矛盾；
- 所有测试通过；
- 所有条款有出处与版本。

## 阶段 D：标注算子格与 G2LC 编译器（第 5–8 周）

### D-01 算子 catalog

编码：

- presence；
- ordinal burden；
- exact count；
- quadrant count；
- point；
- mask；
- spatial relation；
- quality；
- anatomical structure。

### D-02 推导图

例如：

```text
mask → count → count_bin → presence
mask + fovea → distance_to_fovea
mask → quadrant_count
```

### D-03 精确求解器

- CP-SAT 变量与约束；
- lazy counterexample generation；
- Z3 可执行性反例；
- optimality certificate。

### D-04 近似求解器

- 贪心最大收益/成本；
- 支配消除；
- 缓存反例；
- 近似界或经验 gap。

### D-05 证书

实现：

- executable；
- incomplete；
- out-of-spec；
- minimal repair。

**验收 Gate D**：

- 小型随机问题上与 brute force 100% 一致；
- 1000 个 property-based tests 通过；
- 错误“可执行”证书为 0；
- exact 与 greedy 都能输出可独立验证的 JSON 证书；
- 复杂度曲线可生成。

## 阶段 E：Oracle 实验（第 8–10 周）

### E-01 数据标签转换

从 MAPLES/FGADR/IDRiD 等派生 S0–S6。

### E-02 规则重放

- GT evidence → MESSIDOR action；
- GT evidence → Canadian action；
- GT evidence → 其他可执行指南；
- 保存每个病例规则追踪。

### E-03 同病例跨指南

比较：

- grade mapping；
- per-guideline oracle；
- all evidence；
- DAPHNE-style；
- G2LC minimum。

### E-04 成本实验

- 相对成本；
- 时间校准成本；
- 稳定性惩罚；
- 成本敏感性。

**验收 Gate E（Go/No-Go）**：

至少满足：

1. G2LC 找到的方案不是“所有掩膜全选”；
2. 与全掩膜相比存在有意义的成本节省；
3. Oracle G2LC 明显优于直接等级映射；
4. 缺失证据故障注入能准确恢复缺失集合；
5. 不支持的指南被判为 OOS；
6. MAPLES 同病例结果支持“等级语义不能直接转换”的核心动机。

若不满足：

- 收缩指南族；
- 改用 clause-level executability；
- 调整证据离散阈值；
- 将结论限定为 R0–R2/可转诊任务；
- 不进入大规模视觉模型阶段。

## 阶段 F：数据工程与视觉证据模型（第 9–14 周）

### F-01 统一 manifest

- 所有标签三值化；
- 加 provenance；
- 检查患者/眼别；
- 去重；
- 生成 split lock。

### F-02 预处理

- 视网膜圆盘裁剪；
- 保留病灶细节；
- 质量审计；
- 不使用会消除出血/渗出的强颜色变换。

### F-03 训练证据模型

顺序：

1. quality；
2. image-level evidence；
3. segmentation；
4. anatomy；
5. calibration；
6. ensemble。

### F-04 模型选择

主证据模型按：

1. 最差域平均 AUPRC；
2. 校准；
3. 证据覆盖；
4. 计算成本；

而不是只按源域 QWK。

**验收 Gate F**：

- 稀有病灶 AUPRC 高于 prevalence 基线；
- 验证域校准可接受；
- 没有数据泄漏；
- UNKNOWN 不参与负损失；
- 证据模型输出可被规则追踪。

## 阶段 G：近三年基线复现（第 12–17 周，可与 F 后半并行）

### G-01 官方仓库锁定

对每个 R1：

- fork 或 submodule；
- 锁 commit；
- 记录依赖；
- 只写数据 adapter，不任意改核心算法。

### G-02 统一训练

优先完成：

- RETFound；
- GDRNet；
- CLIP-DR；
- DECO；
- DG-ADR；
- FLAIR；
- CBM；
- DAPHNE-style。

### G-03 复现核验

先在作者原始或最接近设置上检查数量级，再迁移到本研究统一划分。

**验收 Gate G**：

- 每个 R1 基线可从干净环境启动；
- 失败方法有错误日志与合理说明；
- 不用论文数字替代失败运行；
- 主表至少包含 6 个近三年强方法和 4 个概念/规则基线。

## 阶段 H：完整主实验、消融与统计（第 17–21 周）

按顺序：

1. P0 编译器；
2. P1 标注设计；
3. P2 Oracle；
4. P3 同病例多指南；
5. P4 端到端；
6. P5 未见指南；
7. P6 OOS/缺失证据；
8. P7 多专家；
9. P8 预算；
10. P9 域偏移；
11. A01–A38 消融；
12. Bootstrap 与显著性检验。

**验收 Gate H**：

- 主结论在至少 3 个随机种子趋势一致；最终补齐 5 个；
- 最差域结果不被平均值掩盖；
- OOS false executable rate 接近 0；
- G2LC 相比 DAPHNE-style 的优势主要来自标注设计/证书，而非更大 backbone；
- Oracle 与 predicted evidence 差距被明确分解。

## 阶段 I：论文与开源审计（第 21–24 周）

### I-01 论文结构

1. Introduction；
2. Related Work；
3. Problem Formulation；
4. Guideline/Annotation Knowledge Representation；
5. G2LC Compiler and Certificates；
6. DR-G2LC Benchmark Protocol；
7. Experiments；
8. Clinical/Knowledge-system Analysis；
9. Limitations；
10. Conclusion。

### I-02 开源包

应公开：

- 代码；
- 指南 DSL；
- 证据本体；
- 合法可公开的派生 metadata；
- 数据下载/申请脚本和说明；
- split 哈希；
- 复现实验配置；
- 结果表脚本；
- 证书独立验证器。

不得公开：

- 受限原图；
- 违反许可的重分发副本；
- 可识别患者信息；
- 未获许可的数据衍生物。

### I-03 最终查新

投稿前再检索 2026 年最新工作，更新：

- `novelty_matrix.csv`；
- Related Work；
- “to the best of our knowledge” 的精确范围。

---

# 24. 首次启动后的 72 小时任务清单

## Day 1

```bash
mkdir g2lc-dr && cd g2lc-dr
git init
uv init --python 3.11
```

完成：

- 仓库骨架；
- CI；
- schemas；
- synthetic fixture；
- `STATUS.md`；
- 数据申请登记。

## Day 2

完成：

- `EvidencePredicate`；
- `AnnotationOperator`；
- `Guideline`；
- YAML/JSON Schema；
- 三值逻辑；
- 第一套 synthetic guideline；
- Z3 反例检查原型。

## Day 3

完成：

- CP-SAT 最小算子求解；
- brute-force 对照；
- missing evidence 注入测试；
- OOS 测试；
- CLI：

```bash
uv run g2lc guideline validate examples/guidelines
uv run g2lc compile examples/project.yaml
uv run g2lc certificate verify runs/example/certificate.json
```

### 72 小时完成标准

- 不能只有 README 和伪代码；
- 必须有可运行 CLI；
- 至少 30 个测试；
- exact solver 在 synthetic fixture 上返回已知最优解；
- 删除一个必要算子后能够返回最小缺失集合；
- 加入未知谓词后返回 `OUT_OF_SPEC`。

---

# 25. 论文预期表格与图形

## 25.1 主文表格

### Table 1：相邻工作能力矩阵

列：

```text
multi-guideline
annotation reverse compilation
annotation granularity
cost/stability
executability certificate
missing evidence
same-case validation
held-out guideline
```

行：DAPHNE、CBM、VLM-GCR、G2LC。

### Table 2：数据集证据支持矩阵

列出每个数据集的：

- grade system；
- lesion presence；
- count；
- quadrant；
- mask；
- anatomy；
- quality；
- annotator；
- access/license；
- overlap family。

### Table 3：G2LC 编译结果

每套指南/指南族：

- 选中算子；
- cost；
- GER；
- missing evidence；
- runtime。

### Table 4：Oracle 同病例跨指南

- grade mapping；
- per-guideline；
- all evidence；
- DAPHNE-style；
- G2LC minimum。

### Table 5：端到端与近三年方法

- ERM；
- RETFound；
- GDRNet；
- CLIP-DR；
- DECO；
- DG-ADR；
- FLAIR；
- CBM；
- DAPHNE；
- G2LC。

### Table 6：消融

至少包含 A01、A02、A03、A04、A09、A10、A11、A28、A32。

### Table 7：安全性与证书

- CCC；
- selective risk；
- OOS F1；
- false executable；
- missing evidence exact match。

## 25.2 主文图形

1. **Figure 1**：指南反向编译标注体系的整体概念图；
2. **Figure 2**：证据本体、算子格、指南规则和证书；
3. **Figure 3**：反例分离求解流程；
4. **Figure 4**：MAPLES 同病例不同指南决策示例；
5. **Figure 5**：Annotation Cost–Guideline Coverage；
6. **Figure 6**：Risk–Coverage；
7. **Figure 7**：误差分解：Oracle vs Predicted vs Direct grade；
8. **Figure 8**：缺失证据与 OOS 案例。

## 25.3 补充材料

- 完整规则表；
- 所有 DSL 文件；
- 算子成本敏感性；
- 所有随机种子；
- 各病灶指标；
- 数据去重报告；
- 失败案例；
- 基线复现差异；
- 编译器复杂度证明；
- 证书样例。

---

# 26. 风险登记与补救路线

| 风险 | 影响 | 提前检测 | 首选补救 | 不允许的补救 |
|---|---|---|---|---|
| MESSIDOR 申请失败 | 同病例多指南证据减弱 | 第 1 周申请 | 使用合法持有的 MESSIDOR；联系 MAPLES 作者；以规则级 synthetic + 公开标签做方法验证并降低临床主张 | 从非官方镜像违规下载 |
| FGADR 申请失败 | IRMA/NV mask 缺失 | 第 1 周申请 | Retinal-Lesions；MMRDR presence；TJDR；把高级病灶降为存在性 | 伪造像素标签 |
| Retinal-Lesions 失败 | PDR 细粒度不足 | 同上 | FGADR + MMRDR；限定 R0–R2/可转诊任务 | 声称完整 PDR 指南执行 |
| Oracle 规则无法复现专家等级 | 核心假设受损 | Gate E | 改为区间/选择性决策；限定可形式化条款；报告规则-专家差异 | 继续调神经网络掩盖问题 |
| 最小方案总是全标注 | 成本创新弱 | EX01/EX02 | 引入粒度、推导和稳定性；扩大指南族；改研究问题为 Pareto 设计 | 人工改成本让结果好看 |
| 新指南谓词公开数据完全没有 | 不可执行 | 编译器 OOS | 输出 OOS + 最小补充算子；作为正面结果 | 忽略谓词强制预测 |
| 高级病灶预测太差 | 端到端性能低 | F 阶段 | 以 Oracle 证明方法；端到端限定可靠病灶；增加拒识 | 用目标测试标签训练 |
| MAPLES 样本量小 | 统计功效有限 | 预先功效分析 | 配对 Bootstrap；主打同病例设计；增加规则级/多域验证 | 夸大临床推广性 |
| DDR 与 MMRDR 重复 | 数据泄漏 | 去重审计 | 合并为一个 source family | 当作独立训练/测试域 |
| 近三年代码不可运行 | 比较不足 | G 阶段 | 锁容器；R2 重实现；透明标记 R3 | 抄论文数字当统一实验 |
| 没有眼科专家合作者 | 医学可信度下降 | 早期确认 | 使用官方指南、公开专家数据；只做计算验证；争取低工作量规则审核 | 用 LLM 代替专家真值 |
| 算力不足 | 基线不完整 | 资源审计 | linear probe、LoRA、小 backbone、分阶段训练 | 只跑弱基线 |

## 26.1 没有私人专家标注时的最终判断

不会破坏核心创新，但必须做以下替代：

1. 公开专家标签承担图像真值；
2. 官方指南承担规则真值；
3. MAPLES 多专家子集承担稳定性估计；
4. MMRDR/FGADR/Retinal-Lesions 承担高级病灶监督；
5. 论文明确是 retrospective computational validation；
6. 不声称 prospective clinical validation。

最小专家投入建议不是重新标图，而是请 1 名视网膜专科医生审核：

- 指南—谓词矩阵；
- 规则 DSL；
- 20 个边界单元测试；
- 哪些谓词在 CFP 上不可观察。

这属于低工作量、高价值审核，不是新建标注子集的硬门槛。

---

# 27. 复现、伦理与 KBS 投稿检查表

## 27.1 数据与许可

- [ ] 每个数据集记录官方来源、许可和申请日期；
- [ ] 不上传受限原图；
- [ ] 不把 DDR/MMRDR-CFP 当独立域；
- [ ] 有患者 ID 时按患者划分；
- [ ] 所有测试图像与训练图像做精确/近似去重；
- [ ] 保存 manifest/hash，不保存身份信息；
- [ ] 遵守非商业用途限制。

## 27.2 方法正确性

- [ ] 指南 DSL 有版本和条款出处；
- [ ] 三值逻辑处理 UNKNOWN；
- [ ] 可执行证书由独立检查器验证；
- [ ] 小问题与 brute force 一致；
- [ ] OOS 不强制预测；
- [ ] missing evidence 集合最小性可验证；
- [ ] 近似算法报告 optimality gap。

## 27.3 实验完整性

- [ ] Oracle 先于视觉模型；
- [ ] MAPLES 全部锁定；
- [ ] 近三年强基线至少 6 个；
- [ ] 概念/规则基线至少 4 个；
- [ ] 标注设计基线至少 5 个；
- [ ] 安全拒识基线至少 3 个；
- [ ] 5 seeds；
- [ ] 95% CI；
- [ ] 最差域；
- [ ] 成本敏感性；
- [ ] 多专家稳定性；
- [ ] 全部核心消融。

## 27.4 论文叙事

- [ ] 唯一创新是 guideline-to-label compilation；
- [ ] 不把 backbone、conformal、DG 写成独立贡献；
- [ ] 明确区别 DAPHNE；
- [ ] 明确区别 CBM/VLM-GCR；
- [ ] 明确“预声明证据语言”的边界；
- [ ] 报告不可执行与失败案例；
- [ ] 不使用绝对首创措辞；
- [ ] KBS 贡献覆盖知识表示、推理、决策支持和视觉验证。

## 27.5 开源复现

- [ ] 一条命令安装；
- [ ] 一条命令运行 synthetic demo；
- [ ] 一条命令验证证书；
- [ ] 数据下载/申请说明；
- [ ] 锁定环境；
- [ ] 配置与结果 hash；
- [ ] 自动生成论文表图；
- [ ] 模型卡、数据卡、限制说明。

---

# 28. Codex 启动提示词使用方法

项目根目录建议同时放置：

```text
G2LC_DR_KBS_Research_Plan_CN.md
CODEX_START_PROMPT_G2LC.txt
```

在 Codex 中打开一个空目录，将 `CODEX_START_PROMPT_G2LC.txt` 的全部内容作为首次任务。首次运行的目标不是马上训练模型，而是：

1. 建立可维护仓库；
2. 实现指南/证据/标注 schema；
3. 实现 synthetic fixture；
4. 实现 CP-SAT + Z3 编译器；
5. 实现证书及独立验证器；
6. 通过测试后再创建数据 adapters；
7. 数据未到位时不得伪造真实实验结果。

建议每次 Codex 继续执行前使用：

```text
Read G2LC_DR_KBS_Research_Plan_CN.md and STATUS.md first. Continue from the first incomplete task whose dependencies are satisfied. Implement and test it; do not merely describe it. Never fabricate datasets, labels, metrics, or completed experiments. Update STATUS.md, CHANGELOG.md, and the runbook before stopping.
```

完整首次启动 Prompt 已另存为同目录的 `CODEX_START_PROMPT_G2LC.txt`。

---

# 29. 官方数据与代码入口汇总

## 29.1 数据

- DDR：https://github.com/nkicsl/DDR-dataset
- MMRDR 论文：https://www.nature.com/articles/s41597-026-07005-9
- MMRDR Figshare：https://figshare.com/articles/dataset/MMRDR/29423747
- MMRDR 评价代码：https://github.com/Vladimirovich2019/MMRDR_Evaluation
- IDRiD：https://idrid.grand-challenge.org/Data/
- IDRiD IEEE DataPort：https://ieee-dataport.org/open-access/indian-diabetic-retinopathy-image-dataset-idrid
- DeepDRiD：https://github.com/deepdrdoc/DeepDRiD
- FGADR：https://csyizhou.github.io/FGADR/
- MAPLES-DR 文档：https://liv4d.github.io/MAPLES-DR/en/
- MAPLES-DR 标签：https://figshare.com/articles/dataset/_b_MAPLES-DR_b_MESSIDOR_Anatomical_and_Pathological_Labels_for_Explainable_Screening_of_Diabetic_Retinopathy/24328660
- MESSIDOR-1 图像申请：https://www.adcis.net/en/third-party/messidor/
- Retinal-Lesions：https://github.com/WeiQijie/retinal-lesions
- GDRBench 数据准备：https://github.com/chehx/DGDR
- NHS DES 分级标准：https://www.gov.uk/government/publications/diabetic-eye-screening-retinal-image-grading-criteria

## 29.2 近三年方法

- RETFound：https://github.com/RViMLab/RETFound_MAE
- GDRNet：https://github.com/chehx/DGDR
- UrFound：https://github.com/yukkai/UrFound
- CLIP-DR：https://github.com/Qinkaiyu/CLIP-DR
- DECO：https://github.com/richard-peng-xia/DECO
- DG-ADR：https://github.com/sharonchokuwa/dg-adr
- FLAIR：https://github.com/jusiro/FLAIR
- ConceptExplanations-DR：https://github.com/andreastoraas/conceptexplanations_dr_grading
- DAPHNE：https://www.nature.com/articles/s41433-021-01415-2
- VLM-GCR：https://ojs.aaai.org/index.php/AAAI/article/view/39948
- KBS 2025 DR ensemble：DOI 10.1016/j.knosys.2025.114581

## 29.3 关键注意事项

1. 官方入口、文件结构和许可证可能更新；下载当天再次核对 README/数据卡。
2. gated 数据必须按官网协议申请，不使用来历不明镜像。
3. MESSIDOR-1 与 MESSIDOR-2 不可混用；MAPLES 对应的是原 MESSIDOR 图像集合。
4. MMRDR-CFP 源自 OIA-DDR，必须与 DDR 合并为同一来源家族并做去重。
5. FGADR 当前公开重点是 Seg-set；Grade-set 的公开状态应在申请时再次确认。
6. 公开数据可支撑方法学创新，但不能替代前瞻性临床验证。

---

# 30. 最终项目完成定义（Definition of Done）

只有满足以下全部条件，项目才算达到可投稿状态：

1. 四套指南完成版本化 DSL 与来源追踪；
2. G2LC exact/scalable 编译器和独立证书验证器完成；
3. 可执行、缺失证据、OOS 三类证书均通过故障注入；
4. Oracle MAPLES 同病例多指南实验成立；
5. 最小标注方案显著节省成本且非平凡；
6. 端到端视觉证据模型完成并报告 Oracle gap；
7. 至少 6 个近三年强方法完成统一复现；
8. DAPHNE、CBM、VLM-GCR 等最相邻基线被正面对比；
9. 完成 P0–P9 和最低消融集合；
10. 5 seeds、95% CI、患者级统计、最差域与多重校正完整；
11. 数据泄漏、许可、规则来源和测试锁定审计通过；
12. 代码、配置、证书与合法 metadata 可复现；
13. 论文不依赖“新 backbone”或模块叠加来支撑创新；
14. 最终查新未发现直接覆盖完整 claim 的同期工作；
15. KBS 稿件清楚展示：知识表示、知识推理、知识工程、决策支持和医学影像实证。

