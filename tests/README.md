# 场景验证

在Codex提供的运行时中执行test_workflows.py。先设置以下环境变量：

- ARCHIVE_SKILL：本技能文件夹
- ARCHIVE_TEST_ROOT：用于测试的空工作目录，不使用真实成果目录
- ARCHIVE_NODE：当前Codex运行时的Node可执行文件
- ARCHIVE_BUILDER：build_workbook.mjs的任务内副本，旁边已建立到当前运行时node_modules的链接

测试会创建独立的PDF、真实六表Excel及模拟人工修改，保留测试目录便于复核。包含17项场景：哈希去重、同名修订、部分源件、人工字段保留、Excel原生日期、旧项目接入、PDF制作及发布中断恢复、人工改PDF保护、成品误作源件拦截、并发写入保护、合并后目录再修改、项目目录迁移，以及页码和问题清单更新。
