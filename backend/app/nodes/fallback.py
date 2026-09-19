from langchain_core.messages import AIMessage

from backend.app.config import FALLBACK_RISK_LEVEL
from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog


def fallback_node(state: CustomerServiceState):
    """工具失败的统一降级出口"""
    reason = state.get("fallback_reason", "系统繁忙")

    tlog("fallback", f"降级原因: {reason}")

    msg = ("抱歉，系统暂时无法完成查询/操作。"
           "已为您转接人工客服，请稍候。")
    return {"messages": [AIMessage(content=msg)], "intent": "complaint",  # 走转人工
        "risk_level": FALLBACK_RISK_LEVEL, }
