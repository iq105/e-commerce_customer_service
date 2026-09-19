# e-commerce_customer_service

#### 介绍

电商客服系统 二、LangGraph 知识点 → 电商场景映射表 LangGraph 知识点 电商客服落地场景 StateGraph / 状态定义
会话状态：用户ID、订单上下文、意图、情绪 条件边 Conditional Edge 意图路由：售前/售后/物流/投诉 循环 Loop 多轮澄清、追问、重试
子图 Subgraph 订单查询、退款、物流各成独立子图 工具节点 ToolNode 查订单、改地址、发起退款、查物流 Checkpointer 会话持久化、断点续聊
Store（长期记忆） 用户偏好、历史投诉、VIP等级 Human-in-the-loop 退款审批、投诉升级、敏感操作确认 中断 Interrupt 支付前确认、提交前二次确认
流式输出 Streaming token 级流式 + 节点级进度 并行 Parallel 同时查订单+物流+优惠券 时间旅行 Time Travel 复现用户会话，做质检和调试
重试/错误处理 工具调用失败降级 多 Agent 协作 售前 Agent、售后 Agent、主管 Agent Command / Send API 动态分发任务给子 Agent
递归限制 / 超时 防死循环，防对话卡死

#### 软件架构

软件架构说明

#### 安装教程

1. xxxx
2. xxxx
3. xxxx

#### 使用说明

1. xxxx
2. xxxx
3. xxxx

#### 参与贡献

七、分阶段落地路线 阶段 目标 覆盖知识点 P0 单轮 FAQ 问答 StateGraph、ToolNode、Checkpointer P1 多意图路由 + 多轮
条件边、循环、Streaming P2 售后子图 + 工具调用 Subgraph、ToolNode、错误重试 P3 人工审批 + 二次确认 Interrupt、Command、HITL P4
长期记忆 + 个性化 Store、Memory P5 多 Agent + 并行 Supervisor、Send API、并行边 P6 质检 + 调优 Time
Travel、LangSmith、Metrics 八、几个关键设计建议 1:意图路由不要只靠 LLM：先用规则/小模型做粗筛，LLM 只处理模糊 case，省成本。 2:
风险分级独立于意图：投诉、退款、大额操作走独立风险通道，别混在意图里。 3:子图要能独立测试：每个子图单独 compile () 后可以脱离主图跑单测。
4:Checkpointer 用 Postgres 而非内存：电商会话必须持久化，Redis 只做缓存。 5:Interrupt 只用于"写操作"前：查询类不要
interrupt，否则体验很差。 6:递归限制一定要设：LLM 路由容易死循环，recursion_limit=25 是安全值。 7:LangSmith 从 P0 就接：后期调
prompt 和排查 bug 全靠它。 8:Store 的 namespace 设计： ("users", uid) / ("orders", oid) / ("faq", category) 分开。

如果你想要，我可以进一步给你： 完整可运行的最小 demo 代码（含 Postgres checkpointer + interrupt + 子图） 某个子图的详细实现（比如退款流程）
多 Agent Supervisor 的完整实现 前端 WebSocket 对接方案 你更想先深入哪一块？

#### 测试

##### A. 意图分类与风险路由

场景 输入 预期意图 预期行为 A1 闲聊    "你好"    chat → chatbot 直接回复 A2 售前咨询    "iPhone 16 Pro 有货吗"
presale → supervisor → presale_agent A3 物流查询（带单号）    "查订单 12345 的物流"    logistics → fanout 并行查询 A4 售后退款
"我要退款"    aftersale → ask_order（缺单号） A5 投诉情绪    "你们太差了！我要投诉！"    complaint → escalate 转人工 A6
高风险直接转人    "再不处理我就打12315"    — risk_level≥7 → classify 直接 escalate
验证方式：看服务端日志 [route_by_intent] 和 [supervisor] 的输出。

##### B. 订单号提取与追问（防死循环）

场景 输入序列 预期行为 B1 直接给单号    "查订单 12345"    extract_order → 识别成功 → 继续流程 B2 不给单号追问
"查一下我的订单" → "不知道" → "算了不知道"    第1次 ask_order → 第2次 ask_order → 第3次（retry≥2）→ escalate B3 中途补单号
"退款" → "订单号 67890"    第1轮 ask_order → 第2轮补上 → 继续售后子图 B4 正则兜底    "订单号是 abc123456xyz"    LLM
提取失败 → 正则 \b\d{5,20}\b 兜底 → 识别到 123456 验证方式：看日志 [ask_order] retry_count= 递增；B2 最终转人工。

##### C. 物流并行查询（fanout）

场景 输入 预期节点序列 C1 正常并行    "查一下订单 12345 的物流"    fanout → query_order_task + query_logistics_task →
aggregate → chatbot C2 工具失败降级    "查一下订单 12345 的物流"（触发30%随机失败时） 重试3次后仍失败 → 降级为 error
字段 → aggregate → chatbot 回复"暂时无法查询"
C3 不存在的订单    "查一下订单 99999 的物流"    fanout → 两个子任务均返回 error → chatbot 回复"未找到订单"
验证方式：节点序列（NODE_HINTS提示）+ 最终回复内容；C2 反复跑几次应有 30% 概率触发降级。

##### D. 售前多 Agent（supervisor）

场景 输入 预期节点序列 D1 首轮售前    "有什么优惠活动吗"    supervisor → presale_agent → supervisor（收尾）→ save_memory
D2 多轮售前    "iPhone 有货吗" → "价格多少"    第1轮正常走完；第2轮仍走 supervisor → presale_agent（classify 重置
supervisor_round） D3 售前+优惠券    "有什么优惠券可以用"    supervisor → presale_agent（prompt 含 coupons=[]） 验证方式：节点序列中
supervisor 出现 2 次（分发 + 收尾），但无死循环（不超过 recursion_limit=25）。

##### E. 售后退款全流程（子图 + interrupt）

这是最复杂的路径，涉及多个 interrupt 和条件分支：

场景 输入序列 预期节点序列 验证点 E1 小额退款成功    "退款" → 提供单号 → 页面点"确认"    aftersale_subgraph:
query_order → check_policy → propose → confirm (interrupt) → check_amount → execute_refund 金额≤5000，直接执行；页面弹出确认按钮
E2 大额需人工审批 同 E1，但用订单12345（8999元>5000） ... → confirm → check_amount → human_approval (interrupt) →
execute_refund 页面弹出"等待人工审批"，点"通过"后执行 E3 用户拒绝退款    "退款" → 提供单号 → 页面点"取消"    ... →
confirm → reject refund_status=cancelled，回复"已取消退款"
E4 人工拒绝审批 同 E2，页面点"拒绝"    ... → human_approval → reject refund_status=rejected，回复"未通过审批"
E5 不可退订单 需改数据：把 FAKE_ORDERS 的某订单 refundable 改为 False ... → check_policy → reject 回复"该订单不支持退款"
E6 查询失败降级 正常退款流程，但 query_order 抛异常 ... → query_order → fallback tool_failed=True → fallback_node →
escalate 转人工 验证方式：

E1/E2：页面 UI 弹出按钮（interrupt 类型分别为 user_confirm / human_approval） E3/E4：点按钮后 resume，看最终 refund_status
E6：触发 query_order 随机失败时应走降级

##### F. 工具调用与降级

场景 输入 预期行为 F1 有订单的普通查询    "查订单 12345"    chatbot → tools (query_order) → 回复订单详情 F2 不存在的订单
"查订单 99999"    tools 返回 error → chatbot 回复"未找到订单"
F3 订单查询超时 连续 3 次触发 30% 随机失败 route_after_tool → fallback → escalate F4 查询优惠券    "我有什么优惠券"
chatbot → tools (query_coupons) → 回复优惠券列表 验证方式：反复输入 F1 约 10 次，观察 F3 是否触发降级路径。

##### G. 多轮对话与记忆

场景 输入序列 预期行为 G1 记忆跨轮    "查订单 12345" → "那它什么时候到"    第1轮保存 intent=logistics,
order_id=12345；第2轮 load_memory 读到 profile，有订单号可直接查 G2 画像更新 连续 2 次投诉 "我要投诉！"    save_memory 累加
complaint_count=2 → 第3次 load_memory 读到 complaint_count G3 新用户无记忆 用全新 user_id（如 u_new）测试 profile={},
history_count=0 验证方式：日志 [load_memory] user=..., profile={...} 显示跨轮数据变化。

##### H. 并发与边界

场景 操作 预期行为 H1 快速连发 快速连续发 2 条消息 第2条消息在第1条处理完后才开始（WebSocket 串行） H2 长文本输入 输入 500
字以上的问题 不崩溃，正常分类和处理 H3 空消息 不输入直接回车 前端空输入不发送（JS 已拦截） H4 并行子任务延迟 需大量数据触发网络延迟
fanout 并行同时处理，不互相阻塞 最小验证路径（快速确认一切正常） 闲聊 → "你好" → 看到回复 物流 → "查订单 12345 的物流" →
看到订单信息 售前 → "有什么优惠活动吗" → 看到售前回复 退款 → "退款" → "67890" → 页面点确认 → 看到退款成功 这 4 条覆盖了
5 种意图中的 4 种 + 所有核心路径（fanout、supervisor、aftersale 子图、interrupt）。

要不要我把这些写进 backend/app/eval/test_cases.py，用你现有的评估框架自动跑一轮？

#### 特技

1. 使用 Readme\_XXX.md 来支持不同的语言，例如 Readme\_en.md, Readme\_zh.md
2. Gitee 官方博客 [blog.gitee.com](https://blog.gitee.com)
3. 你可以 [https://gitee.com/explore](https://gitee.com/explore) 这个地址来了解 Gitee 上的优秀开源项目
4. [GVP](https://gitee.com/gvp) 全称是 Gitee 最有价值开源项目，是综合评定出的优秀开源项目
5. Gitee 官方提供的使用手册 [https://gitee.com/help](https://gitee.com/help)
6. Gitee 封面人物是一档用来展示 Gitee 会员风采的栏目 [https://gitee.com/gitee-stars/](https://gitee.com/gitee-stars/)
