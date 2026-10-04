# 数据约定

## 对局文件

顶层：`run_id`、`captured_at_utc`、`game_version`、`screenshots`、`teams.red`、`teams.blue`、可选 `rule_overrides`。每轮必须从本轮红蓝截图生成新的 `run_id`；历史对局 JSON 不可直接用于新一轮。每队恰好五名式神。每名含 `name`、`stats`、`soul_icon_id`、`soul_name`、`soul_status`、`soul_candidates`。`stats` 需有 `attack,hp,defense,speed,crit,crit_damage,effect_hit,effect_resist` 八个非负数；百分数以 75 表示 75%。`soul_name` 未核实时必须为 `null`，禁止写猜测。`soul_icon_id` 是本轮截图图案裁图的独立指纹，不等于御魂名称。自动识别时第一候选必须与 `soul_name` 一致；人工确认需标 `soul_status: user_confirmed`。非精确 OCR 姓名需人工确认并标 `name_status: confirmed`，解决对应问题后方可从 `issues` 移除。若本轮用户明确给出与常规模式不同的规则，写入 `rule_overrides.user_confirmed`，例如 `{"onmyoji_participation":"双方有阴阳师参战"}`；构建器只对本轮覆盖默认值，不回写通用规则库。

## 机制目录

`catalog.json` 包含 `game_version`、`shikigami`、`souls` 两个映射。式神以中文正式名称为键，每条含：`verified`、`version`、`source`、`skills`。每个技能至少含 `name`、`description`、`triggers`、`conditions`、`effects`、`auto_ai`、`limits`。御魂以中文正式名称为键，每条含：`verified`、`version`、`source`、`icon_ids`、`description`、`triggers`、`conditions`、`effects`、`limits`。

`verified=true` 仅表示当前条目已与明确的版本化游戏内说明核对，不表示实战机制完全无误。若战斗规则、自动施法或隐藏优先级仍不明，相关字段保持空并让核验器阻断推演。

`official_skills_snapshot.json` 是兼容现有构建器的本地技能卡接口名称，不限定提供者。顶层含 `heroes` 对象和可选的 `fetched_at_utc`、`content_version`、`version_note`。`heroes[正式名]` 含 `hero_id` 与 `skills[技能ID]`；每项技能变体含 `awake`（0 或 1）及 `data`，后者含 `name`、`consume_val`、`normaldesc`、`desc`（逐级说明数组）、可选 `extra_skills` 和 `effect_tips`。构建器在用户确认满级觉醒模式后选觉醒版本，逐级应用描述，后级同一效果数值覆盖前级。`wiki_skill_glossary.json` 同样只是兼容接口名称，顶层含 `heroes[式神名][技能名]` 的状态词释义候选数组；关联失败或不唯一时写入 `evidence_gaps`。数字效果 ID 不得凭空解释。所有内容由使用者本地提供，来源与适用版本应写入各记录的元数据。

`community_soul_snapshot.json` 顶层含 `souls[御魂名]`，每项保存 `set1`、`set2`、`set4` 中适用的字段；有 `set1` 而无 `set4` 的记录按首领御魂处理。`community_ai_snapshot.json` 顶层含 `heroes[式神名]` 的自动战斗规则候选。两个文件名仅用于兼容现有接口，不指定来源；缺规则不等于必定普攻。`duel_rules.json` 分开保存用户确认与未确认规则。只有与当前版本核对的记录才能在 `catalog.json` 中设 `verified=true`。

`assets/soul_portraits/御魂名.png` 是由使用者导入的 80×80 对弈面板同款头像。可以只导入部分；未覆盖的本轮图案保持待确认。自动识别状态 `portrait_high_confidence` 仅表示本轮截图与本地图案具有足够的视觉相似度和候选间隔，不表示御魂效果文案已获当前客户端确认。若截图模板与头像给出不同名称，状态为 `conflicting_visual_matches`，必须人工复核。旧整幅插画不得赋予自动识别状态。资料更新后用 `coverage_audit.py` 检查覆盖缺口。

`ai_target_observations.json` 只保存有辨别力的抽象实测假设、样本量/证据等级及真正的社区冲突，不保存旧阵容或赛果；一次随机命中最高生命目标不构成冲突。输入包 `ai_targeting_audit[red|blue]` 按本轮正式式神名提取社区目标规则，并按当前截图面板提供敌方开局满血生命排序及可计算的目标候选；`reported_hypotheses` 单列，不能覆盖 `community_rules`。其中 `highest_current_hp_candidate` 在开局满血时可由生命面板计算，战斗开始后的当前生命须随事件更新；`random_enemy_candidate` 的候选只是可能目标，不代表均匀概率。`鬼童丸` 与 `修罗鬼童丸` 是不同键，不得共用目标规则。

## 推演包与票据

`reasoning_packet.json` 由本轮 `bundle.json` 生成，包含其规范化 SHA-256、本轮完整面板、御魂文案、每张技能的基础正文和逐级升级正文、匹配的状态词释义、AI 原始规则、战斗协议与来源。只删除重复拼接文案、网页图标 URL、OCR 临时细节等；不得删除会改变技能效果的原始字段。`opening_constraints.speed_priority_before_action_bar_changes` 是静态速度排序，不是已证明的实际行动顺序。`initial_shared_fire_per_side` 与 `refill_amounts_by_completed_cycle` 取自本轮已确认规则；结算相位若未确认仍须分支。

预测票据的顶层字段：`run_id`、`packet_sha256`、`choice` (`red|blue|abstain`)、`decisive_steps` 字符串数组、`uncertainties` 字符串数组、`key_actions` 数组。定向票至少有一条关键行动；弃权可为空。每条行动包含：`actor_side` (`red|blue`)、`actor`、`skill_id`、`target_side` (`red|blue|summon`)、`target`（群体或无选定目标时为 `null`）、`ordinary_turn_number_for_side`、`fire_before`、`fire_spent`、`fire_gained`、`fire_after`、`fire_gain_source`、`target_basis`、`contingent`、`evidence_refs`。四个鬼火数字必须为非负整数，且 `before-spent+gained=after`。`fire_gain_source` 有值时必须出现在 `evidence_refs`；普通回火引用 `rule:fire_cycle`，按第 5、10、15…次普通回合核对 3/4/5。随机目标中指定某个具体单位时必须 `contingent=true`。静态检查无法证明完整战斗过程或结论正确。

多模型票据须含实际 `model` 标识；聚合器将同名模型的重复运行合并为一个计票组，同组若互相矛盾则弃权。不同标识可能仍有共同偏差，不能据此证明判断彼此独立。任一票缺失 `model` 时不会自动给方向。聚合结果展示原始票数、合并后的计票组票数及各组成员，不输出伪精确胜率。自动方向须至少四个计票组、胜方获得全部计票组至少三分之二支持，并占定向计票组至少四分之三。这些门槛未经历史对局校准。有证据缺口时，可传 `aggregate_votes.py --gap-review gap_review.json`。复核文件顶层含本轮 `run_id`、`packet_sha256` 和 `assessments` 数组；数组须按 `reasoning_packet.json.evidence_gaps` 的原顺序逐条列出 `{"gap":"原缺口全文","outcome_sensitive":false,"reason":"为何不影响本局胜负"}`。未复核或任一项可能翻转结果时，聚合器输出 `undecided`。这份复核是可追溯的判断记录，不代表程序已独立证明机制正确。

## 证据层级

1. 当期游戏内原始截图或录像。
2. 同版本官方技能/御魂说明。
3. 其他有版本记录的资料，明确记录提供日期与无法确定的版本差异。
4. 未核实的玩家经验只能作为候选线索。

同名不同版本不得混用。保存原文与机制摘要时，摘要应能逐项回指原文的条件、触发时点和数值。
