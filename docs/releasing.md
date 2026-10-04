# 维护者发布说明

工作区里的 `skills/`、`runs/`、旧公开版目录和旧 ZIP 不属于发布内容。首次发布时，运行 `python scripts/build_public_release.py` 生成同级的 `yys-duiyi-predict-release/` 与同名 ZIP，从生成目录创建全新、无旧提交历史的仓库。现有仓库的后续更新应在同一仓库提交，不必重新初始化。

提交前查看文件清单；不要把本地 `references/*snapshot.json`、`assets/`、截图、对局包、模型配置或环境变量文件加回去。若曾在任何仓库提交真实密钥，应先撤销或轮换密钥。
