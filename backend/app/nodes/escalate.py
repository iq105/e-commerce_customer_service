from langchain_core.messages import AIMessage

from backend.app.config import RISK_ESCALATE_THRESHOLD
from backend.app.graph.state import CustomerServiceState


def escalate_node(state: CustomerServiceState):
    intent = state.get("intent")
    risk = state.get("risk_level", 0)

    if intent == "complaint" or risk >= RISK_ESCALATE_THRESHOLD:
        msg = "非常抱歉给您带来不好的体验，已为您转接人工客服（工号 A1024），请稍候。"
    else:
        msg = "这个问题我帮您转接人工客服处理，请稍候。"

    return {"messages": [AIMessage(content=msg)]}
