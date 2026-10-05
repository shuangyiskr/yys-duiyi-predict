<h1 align="center">阴阳师对弈竞猜预测 Skill</h1>
<p align="center"><strong>让 AI 先读对这一局，再认真推演胜负。</strong></p>
<p align="center">从红蓝阵容截图出发，核对面板、御魂与机制资料，追踪自动战斗的关键分支。</p>
<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#项目亮点">项目亮点</a> ·
  <a href="#资料准备">资料准备</a> ·
  <a href="#参与改进">参与改进</a>
</p>
<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-2d6a4f"></a>
  <img alt="Python: 3.11" src="https://img.shields.io/badge/Python-3.11-3776ab">
  <img alt="Status: open source" src="https://img.shields.io/badge/Status-open%20source-7952b3">
</p>

---

直接让 AI 看两张图选红蓝，最容易出错的地方往往发生在推演之前：式神名字和御魂图案认错、面板漏读、技能升级没合并，或者把自动战斗当成玩家手动操作。本项目把这些信息整理成**可核对的本局输入包**，再要求推演给出行动、鬼火、目标与依据。它是《阴阳师》的非官方开源项目，不承诺每局都能预测成功。

## 项目亮点

| 截图输入 | 机制输入 | 推演输出 |
| :--- | :--- | :--- |
| 从手机、平板或模拟器截图定位阵容表，读取十名式神和八项面板 | 对照本地导入的技能、御魂效果与自动战斗规则，列出缺口 | 追踪关键出手、鬼火与目标选择，说明结论依赖哪些条件 |
| 不要求整张截图有固定宽高比；低置信度结果进入核对 | 资料可在后续轮次复用；版本和来源需核实 | 遇到随机目标、冲突资料或关键未知项时保留分支 |

### 设计重点

输入核验、可追溯的推演过程，以及在证据不足时明确指出卡在哪里。可选用多个模型独立阅读同一份推演包，再汇总票据；票数不等于胜率。

> 首次使用时，可以让你的 AI 智能体协助整理和导入资料；来源、使用权限及当前版本需要你确认。准备好后，后续每轮可以复用。

## 快速开始

把整个仓库放进支持 `SKILL.md` 的智能体技能目录。Codex 用户可以在 PowerShell 中运行：

```powershell
git clone https://github.com/shuangyiskr/yys-duiyi-predict.git "$env:USERPROFILE\.agents\skills\yys-duiyi-predict"
cd "$env:USERPROFILE\.agents\skills\yys-duiyi-predict"
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/bootstrap_data.py
```

最后一条建立本地资料槽并报告覆盖度；`0` 表示相应资料尚未准备。请保留整个仓库，单独复制 `SKILL.md` 无法运行脚本。其他智能体按其技能目录约定安装。项目已在 Windows 与 Python 3.11 下验证。

安装后，把红蓝双方的**阵容详情截图**交给智能体：

> 使用 `$yys-duiyi-predict` 分析本轮对弈竞猜。红方截图在 `C:\path\to\red.png`，蓝方截图在 `C:\path\to\blue.png`。请先核对截图和本局资料，补齐可用资料，再推演；不能核实的地方请列出来。

支持自动选择 Skill 的智能体也可以直接接收这段任务描述。第一次准备资料、核对御魂通常更费时；后续轮次可复用已确认的本地资料。

<details>
<summary><strong>想先看一个不依赖游戏资料的演示？</strong></summary>

```powershell
python examples/synthetic_demo.py
```

演示用虚构数据验证一笔正确的鬼火账，并拦下故意写错的票据。它展示推演校验方式，不是真实对局预测；最终输出 `prediction: abstain`。

</details>

## 资料准备

仓库提供数据接口与导入工具，不随附游戏技能文案、御魂图片或自动战斗资料。资料可以分批整理到本地目录：

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

这些文件名是程序接口名称，不指定资料来源。四个 JSON 的顶层依次需要 `heroes`、`souls`、`heroes`、`heroes` 对象；头像是与对弈面板对应的 80×80 PNG。字段见[数据约定](references/schema.md)。导入命令：

```powershell
.\.venv\Scripts\python scripts/bootstrap_data.py --source-dir C:\path\to\my-data
```

导入器检查基本结构与图片尺寸，已有不同内容时拒绝覆盖；明确需要替换时再加 `--replace`。没有头像也可以生成截图核对页，但御魂名称须逐项确认。确认当前竞猜符合标准模式后，可运行：

```powershell
.\.venv\Scripts\python scripts/confirm_local_rules.py --accept-standard-duel-mode
```

该选项表示你确认满级觉醒、技能满级、双方各 4 火、正常 3/4/5 回火、无阴阳师参战。`--accept-skill-text`、`--accept-soul-text`、`--accept-community-ai` 分别用于确认已核实的本地资料，确认与内容指纹绑定；工具不会独立证明资料与当前客户端一致。

## 一轮推演怎样运行

```powershell
.\.venv\Scripts\python scripts/start_match.py 红方.png 蓝方.png --runs-dir runs
```

读取器根据表格行名与五列数值定位，不限制整张图的宽高比例。它生成 `match.json` 和 `soul_review.html`。核对十名式神、八项面板与十个御魂图案；修正待确认项时保留原图裁图坐标和图案指纹。随后运行：

```powershell
.\.venv\Scripts\python scripts/verify_match.py runs/本轮目录/match.json --intake-only
.\.venv\Scripts\python scripts/build_inference_bundle.py runs/本轮目录/match.json --out runs/本轮目录/bundle.json
.\.venv\Scripts\python scripts/build_reasoning_packet.py runs/本轮目录/bundle.json --out runs/本轮目录/reasoning_packet.json
```

智能体使用本轮 `reasoning_packet.json` 推演。`missing` 非空时不做确定性竞猜；`evidence_gaps` 需判断是否会改变本局结论。完整执行规则在 [SKILL.md](SKILL.md)、[推演工作表](references/inference_workflow.md)和[战斗协议](references/battle_protocol.md)。

## 可选：多模型复核

使用 `references/panel_config.example.json` 配置自己的模型服务，密钥放在本地环境变量。脚本会把完整 `reasoning_packet.json` 发送给配置的服务，其中可能包含你导入的资料文案和本局面板；使用前请确认这些资料可以外发，外部服务也可能收费。它不直接上传截图。

先由主智能体独立保存包含实际 `model` 标识的 `master_ballot.json`。将 `references/model_weights.example.json` 复制为本地 `model_weights.json`，按模型实际标识预先指定 `strong`、`medium`、`base` 档；未列出的模型按基础档计算。可选的 `model_families` 把已知同系列模型合并为一个来源，只取其中最高档权重，意见冲突则该来源弃权。档位是待实测校准的能力先验，不由模型自己在票据中填写。然后运行：

```powershell
.\.venv\Scripts\python scripts/run_independent_panel.py runs/本轮目录/reasoning_packet.json panel_config.json --master-ballot master_ballot.json --out-dir ballots
.\.venv\Scripts\python scripts/aggregate_votes.py master_ballot.json ballots --packet runs/本轮目录/reasoning_packet.json --weight-config model_weights.json --out result.json
```

如有 `evidence_gaps`，需按[票据格式](references/schema.md)记录 `gap_review.json`，并在聚合命令中加 `--gap-review gap_review.json`。同名模型重复运行只算一组；各档权重为基础 1.0、中等 1.2、强 1.5。自动给方向须至少四组，胜方获得全部权重至少 60%，且获得定向权重严格超过三分之二。不使用权重配置时，删除命令中的 `--weight-config model_weights.json`，全部模型会按基础档计算。这些权重与门槛尚未经历史对局校准，计票份额不代表胜率。

## 参与改进

这个项目仍有值得验证的机制输入问题。我们把**已由当前实现证实的缺口**、官方更新举例与可提交的改进方式放在 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎提供可复现的对局、适用玩法与版本证据，或改进数据模型和推演校验。一个具体反例，比一份泛泛的机制清单更有帮助。

代码采用 [MIT 许可](LICENSE)；游戏资料相关说明见[第三方内容说明](THIRD_PARTY_NOTICES.md)。
