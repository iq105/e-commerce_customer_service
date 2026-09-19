"""轻量日志 + trace_id 贯穿（AGENT.md §5，禁止裸 print/裸 except）。

用法：
    from backend.app.trace import tlog, set_trace_id
    set_trace_id()  # 在单次请求/轮次入口调用
    tlog("nodes/extract", "提取订单号")

tlog 自动带上当前线程的 trace_id，便于串联一次问答的完整链路。
"""
import contextvars
import inspect
import logging
import uuid

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")

_trace_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def set_trace_id(trace_id: str | None = None) -> str:
    """为当前上下文设置 trace_id；不传则自动生成（返回新值）"""
    tid = trace_id or uuid.uuid4().hex[:8]
    _trace_var.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_var.get()


def tlog(*parts):
    """带 trace_id 的日志输出（不敏感，仅链路追踪）"""
    frame = inspect.currentframe().f_back
    module = frame.f_globals.get("__name__", "?").rsplit(".", 1)[-1]
    logging.getLogger("cs").info("[%s] [%s] %s", get_trace_id(), module, " ".join(str(p) for p in parts))