import time
from collections import defaultdict
from langchain_core.callbacks import BaseCallbackHandler


class MetricsCallback(BaseCallbackHandler):
    """收集节点耗时、token、工具调用，用于本地观测"""

    def __init__(self):
        self.node_times = defaultdict(list)
        self.llm_calls = 0
        self.llm_tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.tool_calls = []
        self.errors = []
        self._starts = {}
        self._llm_starts = {}

    # ---------- 节点级 ----------
    def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
        self._starts[run_id] = time.time()

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        name = kwargs.get("name") or "unknown"
        if run_id in self._starts:
            self.node_times[name].append(time.time() - self._starts[run_id])

    def on_chain_error(self, error, *, run_id, **kwargs):
        name = kwargs.get("name") or "unknown"
        self.errors.append({"node": name, "error": str(error)[:200]})

    # ---------- LLM 级 ----------
    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self.llm_calls += 1
        self._llm_starts[run_id] = time.time()

    def on_llm_end(self, response, *, run_id, **kwargs):
        usage = {}
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {}) or {}
        self.llm_tokens["prompt"] += usage.get("prompt_tokens", 0)
        self.llm_tokens["completion"] += usage.get("completion_tokens", 0)
        self.llm_tokens["total"] += usage.get("total_tokens", 0)

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.errors.append({"node": "llm", "error": str(error)[:200]})

    # ---------- 工具级 ----------
    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = kwargs.get("name") or serialized.get("name", "unknown")
        self.tool_calls.append({"name": name, "input": input_str[:100], "status": "start"})

    def on_tool_end(self, output, *, run_id, **kwargs):
        name = kwargs.get("name") or "unknown"
        for tc in reversed(self.tool_calls):
            if tc["name"] == name and tc["status"] == "start":
                tc["status"] = "ok"
                tc["output"] = str(output)[:100]
                break

    def on_tool_error(self, error, *, run_id, **kwargs):
        name = kwargs.get("name") or "unknown"
        for tc in reversed(self.tool_calls):
            if tc["name"] == name and tc["status"] == "start":
                tc["status"] = "fail"
                tc["error"] = str(error)[:200]
                break
        self.errors.append({"node": f"tool:{name}", "error": str(error)[:200]})

    # ---------- 汇总 ----------
    def summary(self) -> dict:
        avg_node = {k: round(sum(v) / len(v), 3) for k, v in self.node_times.items()}
        return {"llm_calls": self.llm_calls, "llm_tokens": self.llm_tokens, "tool_calls": len(self.tool_calls),
            "tool_failures": sum(1 for t in self.tool_calls if t["status"] == "fail"), "avg_node_time": avg_node,
            "errors": self.errors, }

    def print_summary(self):
        s = self.summary()
        print("\n" + "=" * 50)
        print("📊 Metrics")
        print(f"  LLM 调用: {s['llm_calls']} 次, token: {s['llm_tokens']}")
        print(f"  工具调用: {s['tool_calls']} 次, 失败: {s['tool_failures']} 次")
        print(f"  节点平均耗时: {s['avg_node_time']}")
        if s["errors"]:
            print(f"  ⚠️ 错误: {s['errors']}")
        print("=" * 50 + "\n")
