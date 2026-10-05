---
name: yys-duiyi-predict
description: 读取阴阳师对弈竞猜的本轮红蓝面板，核验式神、八项数值、御魂及本地导入的技能和自动战斗资料，再推演结果；支持隔离的多模型推演与票据聚合。
---

# 对弈竞猜输入核验与推演

本 Skill 使用本轮截图和本地资料，不以猜测填补缺失技能、御魂或 AI 行为。首次使用时，可协助使用者整理和导入资料；来源、使用权限及与当前客户端版本是否一致，由使用者确认。准备好的资料可在后续轮次复用。安装及导入步骤见 [README.md](README.md)，数据格式见 [schema.md](references/schema.md)。

运行下列相对路径命令前，先定位本文件 `SKILL.md` 所在的 Skill 根目录，并将命令的工作目录设为该目录；用户的当前项目目录可能不同。截图和输出路径则按实际位置传入，避免把相对路径误认为相对用户项目。

## 本轮截图

使用本轮两张不同的红蓝截图运行 `python scripts/start_match.py 红图 蓝图 --runs-dir runs`。读取器依据表格行名和五列数值定位，不要求整张截图具有固定比例；定位失败时报告截图问题并请使用者核对，不套用其他设备的坐标。检查生成的 `match.json` 和 `soul_review.html`：逐格核对十名式神、八项数值、十个御魂图案。没有本地头像或匹配置信度不足时，御魂保持待确认，请使用者根据原图确认，并标为 `soul_status: user_confirmed`。OCR 名称未命中本地词表时，确认正式名称并标为 `name_status: confirmed`。修正后运行 `python scripts/verify_match.py match.json --intake-only`。不要借用历史轮次的阵容、结果或确认。

## 本地资料与规则

本地资料不齐时，先结合当前可用资料与工具，协助整理并导入本轮所需的技能卡、御魂效果、自动战斗行为和技能状态词释义，再检查覆盖度；仍缺失或存在来源、版本冲突的记录应明确报告。头像库用于图案匹配。资料的来源、使用权限和版本由使用者确认；Skill 仅核对结构、覆盖度和本局相关内容，不代表已经取得第三方授权或核实当前客户端版本。

若用户确认标准竞猜模式，运行 `python scripts/confirm_local_rules.py --accept-standard-duel-mode`：满级觉醒、技能满级、双方各 4 火、正常 3/4/5 回火、无阴阳师。仅在用户核实导入内容后，才分别使用 `--accept-skill-text`、`--accept-soul-text`、`--accept-community-ai`。内容指纹变化会使旧确认失效。本轮例外记录在 `match.json.rule_overrides.user_confirmed`。

## 推演输入与决策

运行 `python scripts/build_inference_bundle.py match.json --out bundle.json`，再运行 `python scripts/build_reasoning_packet.py bundle.json --out reasoning_packet.json`。优先读本轮的 `reasoning_packet.json`；`missing` 非空则停止确定性竞猜，`evidence_gaps` 逐项判断影响。按 [推演工作表](references/inference_workflow.md) 和 [战斗协议](references/battle_protocol.md) 还原先机、出手、双方鬼火、自动选技能与目标、关键技能及御魂触发。规则优先级为已确认例外、用户接受的 AI 行为记录、明确标为假设的基线。随机目标、同速、控制与伤害阈值造成结果分叉时保留分支，不替自动战斗选最优行动。

定向预测写出 `run_id`、`packet_sha256`、选择、关键步骤、不确定项和至少一条 `key_actions`，并用 `python scripts/verify_inference_trace.py reasoning_packet.json ballot.json` 做形式校验。通过只表示没有检测到结构与局部鬼火算术矛盾，不能证明胜负。没有已校准数据时不报精确胜率。

若用户要多模型推演，先说明完整 `reasoning_packet.json` 会发给配置的外部模型服务，并确认其中资料可外发。主模型先独立冻结一票，并在票据中写入实际 `model` 标识；五个子模型仅收到同一份冻结的包，不看其他模型的过程或结论。有效票按不同 `model` 标识合并，同名模型重复运行只算一个标识；不同标识不保证判断彼此独立。用户可在独立的模型权重配置中预先指定能力档位：基础 1.0、中等 1.2、强 1.5；未配置时按基础档，不因主模型身份自动加权，也不接受模型自报权重。已知同系列模型可在 model_families 中合并为一个来源，取最高档权重；意见冲突则该来源弃权。任一票缺失标识则不自动给方向。自动给方向须至少四个不同标识、胜方获得全部权重至少 60%，且占定向权重严格超过三分之二；弃权计入全部权重，不计入定向权重。`evidence_gaps` 还须逐项复核为不影响胜负，记录用 `gap_review.json` 绑定本轮 `run_id` 和 `packet_sha256`。否则结果为 `undecided`，说明票数、权重、分歧和待核证据。这些档位和门槛未经历史对局校准，权重份额不代表胜率。详见 [数据约定](references/schema.md)。临近封盘时及时给出带条件的单模型判断。
