# GLM 网关测试（独立试跑）

使用原版 harness 的提示、文档、攻击、工具、交接和评分，仅新增智谱后端与可审查的试跑入口。网关是项目已有的收件人白名单，不是新增防御算法。所有发送均为本地模拟事件。

默认选择 test-01：正常条件 + 4 模板 × 2 目标，五配置各一次，网关开启，共45个工作流。仅一个测试场景，报告计数，不进行总体推断，不与 DeepSeek 的1350次正式实验混合。默认只显示计划，--execute 才调用真实 API。

```powershell
python -m venv experiments/glm_gateway/.venv
. .\experiments\glm_gateway\.venv\Scripts\Activate.ps1
python -m pip install -r experiments/glm_gateway/requirements.txt
python experiments/glm_gateway/test_gateway.py
python experiments/glm_gateway/run.py
# 安全地在自己的环境中设置 ZHIPU_API_KEY 后执行；不要提交凭证。
python experiments/glm_gateway/run.py --execute
python experiments/glm_gateway/report.py results/test-glm-gateway-pilot/具体批次目录
```

建议使用上面的独立虚拟环境，保留主实验自己的SDK版本。--seed只复现任务调度，不保证远端模型输出确定。

可使用 --gateway off/both 增加对照；--limit-scenarios 0 选择全部场景。30个测试场景、网关on、各重复一次共1350。全量运行前必须明确资源与预算；默认最多600请求，已报告500000 tokens后停止下一派发，不能据此保证完成全量或限制最终账单。默认 glm-5.3-flash、low、max_tokens4096、超时60秒、SDK重试0、单工作流顺序运行。

每批新建目录，不覆盖旧批次，不自动重跑失败。API故障或用量未知停止，失败记录保留。原始harness在异常时可能缺少活动角色调用，成本以独立 calls.jsonl 账本为准。原JSON修复预算行为保留，未偷偷替换累计预算协议。

源代码身份见 source_reference.json 和每批source_snapshot。当前基于 main 1b590624；与旧冻结分支5627d1e的远端比较只增加结果文件。适配器将供应商不透明会话字段在同角色后续调用中回传，跨角色仅传最终交接内容；磁盘只保留其长度/哈希，凭证不入包。

原score原样保存；gateway_metrics单列所有额外收件人、合法关键词投递、实际block后的关键词恢复与载荷接触。关键词不是完整语义准确率，自动promoted不是人工标签，G2 direct作为内容污染对照单独解释。没有block不计恢复。原收件人解析契约保持不变，sent不等于真实SMTP投递。

测试与原始数据是不同材料；FakeBackend只用于机械检查。公开结果应脱敏并压缩日志，保留manifest、plan、calls、attempts及源码快照，不提交.env、令牌或供应商opaque正文。
