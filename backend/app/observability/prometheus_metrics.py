"""Prometheus metrics（可选，不装 prometheus_client 则跳过）"""

try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server

    SESSION_TOTAL = Counter("cs_session_total", "会话总数", ["intent", "channel"])
    HUMAN_HANDOFF = Counter("cs_human_handoff_total", "转人工次数", ["reason"])
    NODE_LATENCY = Histogram("cs_node_latency_seconds", "节点耗时", ["node"], buckets=(0.1, 0.5, 1, 2, 5, 10, 30), )
    TOOL_CALLS = Counter("cs_tool_calls_total", "工具调用", ["tool", "status"])
    LLM_TOKENS = Counter("cs_llm_tokens_total", "LLM token", ["type"])
    ACTIVE_SESSIONS = Gauge("cs_active_sessions", "活跃会话数")


    def start_metrics_server(port: int = 8000):
        start_http_server(port)
        print(f"[metrics] Prometheus /metrics at :{port}")

except ImportError:
    print("[metrics] prometheus_client 未安装，跳过")


    def start_metrics_server(port: int = 8000):
        pass


    SESSION_TOTAL = HUMAN_HANDOFF = NODE_LATENCY = None
    TOOL_CALLS = LLM_TOKENS = None
    ACTIVE_SESSIONS = None
