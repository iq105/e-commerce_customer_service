from langgraph.types import RetryPolicy

# 通用重试策略：3 次，指数退避
DEFAULT_RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0, jitter=True,
    retry_on=(Exception,), )

# 工具节点重试更激进
TOOL_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0,
    retry_on=(ConnectionError, TimeoutError, Exception), )

# 写操作不重试（避免重复退款）
NO_RETRY = RetryPolicy(max_attempts=1)

# 退款金额人工审批阈值（元）：超阈值必须人工审批
REFUND_APPROVAL_THRESHOLD = 5000

# 风险分级阈值：risk_level >= 该值直接转人工（escalate）
RISK_ESCALATE_THRESHOLD = 7

# fallback 降级/模拟风险分
FALLBACK_RISK_LEVEL = 8

# 图执行递归上限（LangGraph recursion_limit）
RECURSION_LIMIT = 25
