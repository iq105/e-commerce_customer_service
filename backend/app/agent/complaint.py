from langchain_core.messages import AIMessage, SystemMessage

from backend.app.graph.llm import model
from backend.app.graph.state import CustomerServiceState


COMPLAINT_PROMPT = """你是投诉处理专员，用户情绪激动，你需要：
1. 先道歉、共情，不要辩解。
2. 承认问题，给出具体补偿方案（优惠券/积分）。
3. 如果涉及监管投诉、媒体曝光，立即转人工。

用户历史投诉次数：{complaint_count}
"""


def complaint_agent_node(state: CustomerServiceState):
    profile = state.get("user_profile", {})
    resp = model.invoke(
        [SystemMessage(content=COMPLAINT_PROMPT.format(complaint_count=profile.get("complaint_count", 0))),
         *state["messages"], ])
    return {"messages": [AIMessage(content=resp.content)]}
