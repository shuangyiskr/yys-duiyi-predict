# 阴阳师对弈竞猜预测 Skill

这是一个面向《阴阳师》对弈竞猜的非官方开源 Skill。它把**本轮截图核对、资料缺口检查和战斗推演**串成一条可复查的流程，减少智能体凭记忆认御魂、补技能或跳过自动战斗规则的情况。

**使用流程：**红蓝截图 → 核对式神、八项面板和御魂 → 载入本地技能、御魂及自动战斗资料 → 标记缺口与条件分支 → 输出推演；需要时再用多模型票据复核。

它适合处理以下问题：

- **输入容易错：**截图识别后逐格核对名称、数值和御魂图案，不把低置信度识别当成已确认事实。
- **机制容易漏：**按本轮相关资料检查技能升级、御魂效果、鬼火与自动选技能、选目标规则；缺项和冲突明确列出。
- **结论难追溯：**关键行动附来源与鬼火账；随机或未知机制保留分支，多模型分歧可输出 `undecided`。

已在 Windows + Python 3.11 验证。仓库不附带可直接使用的游戏资料，首次使用需准备、导入并核对本地数据。输入核验不能保证资料真实、完整或与当前客户端一致；推演结果不是已校准的胜率。

仓库不附带游戏图片、批量技能或御魂文案；仓库脚本不会自动下载资料，也不预设第三方资料站点。资料可由使用者提供，或由调用本 Skill 的智能体利用自身工具整理；来源、适用版本和使用权限仍需核对。缺失资料会作为缺口显示，不会被自动补写。项目采用 [MIT 许可](LICENSE)；许可不授予第三方游戏内容的使用权，详见[第三方内容说明](THIRD_PARTY_NOTICES.md)。

## 安装

将本目录放进支持 SKILL.md 的智能体 skills 目录，然后在本目录运行：

Codex 用户可将公开仓库克隆到个人 skills 目录：

```powershell
git clone https://github.com/shuangyiskr/yys-duiyi-predict.git "$env:USERPROFILE\.agents\skills\yys-duiyi-predict"
cd "$env:USERPROFILE\.agents\skills\yys-duiyi-predict"
```

需要保留整个目录，包括 `SKILL.md`、`scripts/` 和 `references/`；只复制 `SKILL.md` 无法运行脚本。若安装后 Codex 未显示该 Skill，重启 Codex。其他支持 SKILL.md 的智能体请按各自的技能目录约定安装。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/bootstrap_data.py
```

最后一条只创建本地规则副本和空资料槽，并报告已有资料覆盖度；**不访问网络**。零条目并不表示准备好预测。

安装后在 Codex 中可明确调用，例如：`使用 $yys-duiyi-predict 分析本轮对弈竞猜。红方截图在 C:\path\to\red.png，蓝方截图在 C:\path\to\blue.png；先核对输入和资料缺口，再推演。` 也可直接描述任务，让智能体按 Skill 描述自行选择。调用不等于已经备齐资料；首次使用仍须按下文导入并核对本地数据。

## 先试一个虚构演示

在仓库目录运行 `python examples/synthetic_demo.py`。它只用虚构式神、技能和御魂，生成一份推演包和一张弃权票据，并用项目的票据校验器检查结构与鬼火账。命令会打印两个输出文件的临时路径、资料缺口数，以及 `ballot_valid: true`、`invalid_fire_ballot_blocked: true` 和 `prediction: abstain`；无需安装 OCR 依赖，也不会联网。

这个演示帮助检查推演包与票据流程，**没有演示截图识别，也不能给出真实对局预测**。真实对局仍需完成下面的资料导入、截图逐格核对和机制核实。

## 导入本地资料

若您有权使用相应资料，可自行整理为以下目录，然后本地导入：

```text
my-data/
  references/
    official_skills_snapshot.json
    community_soul_snapshot.json
    community_ai_snapshot.json
    wiki_skill_glossary.json
  assets/
    soul_portraits/
      御魂名.png
```

文件名是现有程序的数据接口名称，**不指定资料来源**。四个 JSON 的顶层必须分别含 `heroes`、`souls`、`heroes`、`heroes` 对象；头像必须是 80×80 PNG，名称与御魂名相同。具体字段见 [数据约定](references/schema.md)。资料可以分批导入：

```powershell
.\.venv\Scripts\python scripts/bootstrap_data.py --source-dir C:\path\to\my-data
```

导入器只读本地文件，检查 JSON 基本结构与 PNG 尺寸；已有不同内容时会拒绝覆盖，需要用户明确加 `--replace`。更新资料后，先重新检查覆盖度，再确认当前文案是否适用于客户端。没有头像时仍可读取截图和生成核对页，但御魂名称需逐项人工确认。

## 确认本地规则

若您确认当前竞猜为满级觉醒、技能满级、双方各 4 火、正常 3/4/5 回火且无阴阳师参战，执行：

```powershell
.\.venv\Scripts\python scripts/confirm_local_rules.py --accept-standard-duel-mode
```

`--accept-skill-text`、`--accept-soul-text`、`--accept-community-ai` 分别表示使用者已核实导入的对应资料。确认与资料指纹绑定，内容变化后须重核。确认标记不等于程序独立核验了资料真实性。

## 读取与推演

```powershell
.\.venv\Scripts\python scripts/start_match.py 红方.png 蓝方.png --runs-dir runs
```

它生成本轮 `match.json` 和 `soul_review.html`。先核对十名式神、八项面板和十个御魂；未确认项修正 `match.json` 并保留原图指纹，随后执行：

```powershell
.\.venv\Scripts\python scripts/verify_match.py runs/本轮目录/match.json --intake-only
.\.venv\Scripts\python scripts/build_inference_bundle.py runs/本轮目录/match.json --out runs/本轮目录/bundle.json
.\.venv\Scripts\python scripts/build_reasoning_packet.py runs/本轮目录/bundle.json --out runs/本轮目录/reasoning_packet.json
```

`missing` 非空时不得给确定性竞猜。`evidence_gaps` 要逐项判断是否影响胜负。推演智能体读本轮 `reasoning_packet.json`，不得套用历史场次；规则见 [SKILL.md](SKILL.md) 和 [推演工作表](references/inference_workflow.md)。

多模型配置示例在 `references/panel_config.example.json`；密钥只放本地环境变量。运行 `run_independent_panel.py` 会把**完整 `reasoning_packet.json`** 发送给所配置的五个模型服务，其中可能包含使用者导入的技能、御魂、AI 文案和本轮面板数据。请先确认资料允许传给这些服务，并只配置可信的 HTTPS 地址。脚本拒绝非 HTTPS 地址、URL 内的账号密码和服务重定向；本地截图文件不会由该脚本直接上传。调用外部模型可能产生费用。单模型本地推演和 `bootstrap_data.py` 不会因安装而自动调用模型服务。

如需多模型推演，先按 [票据格式](references/schema.md)让主智能体独立保存 `master_ballot.json`，其中须有实际 `model` 标识；将配置示例复制为本地 `panel_config.json` 并填入自己的模型服务配置与密钥环境变量。然后运行：

```powershell
.\.venv\Scripts\python scripts/run_independent_panel.py runs/本轮目录/reasoning_packet.json panel_config.json --master-ballot master_ballot.json --out-dir ballots
.\.venv\Scripts\python scripts/aggregate_votes.py master_ballot.json ballots --packet runs/本轮目录/reasoning_packet.json --out result.json
```

若推演包含 `evidence_gaps`，还需按 [数据约定](references/schema.md)逐项写出本轮 `gap_review.json`，在第二条命令中添加 `--gap-review gap_review.json`；否则聚合结果会保持 `undecided`。

多模型聚合不预设主模型或子模型的准确率权重。每张票须写实际 `model` 标识；每个不同标识最多算一个来源，同名模型重复运行不会增加票数。模型标识只能帮助识别同名重复运行，不能证明不同模型的判断彼此独立。任一票缺失标识时不自动给方向。自动方向须至少四个不同标识，胜方得到全部标识至少三分之二支持，且得到定向标识至少四分之三支持；弃权也计入全部标识。若输入包列有 `evidence_gaps`，还须用 `aggregate_votes.py --gap-review` 逐项记录其对本局胜负的影响。否则结果为 `undecided`，并给出待复核原因。这些门槛是保守的决策规则，未经历史对局校准；票数不等于胜率。

维护者的打包说明见 [发布文档](docs/releasing.md)。

仓库的资料边界见 [第三方内容说明](THIRD_PARTY_NOTICES.md)。
