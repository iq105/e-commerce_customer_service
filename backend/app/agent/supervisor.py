from langchain_core.messages import SystemMessage
from langgraph.types import Command

from backend.app.config import RISK_ESCALATE_THRESHOLD
from backend.app.graph.llm import model
from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog

SUPERVISOR_PROMPT = """你是电商客服团队的主管。根据用户问题和对话历史，
决定交给哪个专员处理。

可选专员：
- presale_agent：售前咨询（商品、价格、优惠、库存）
- aftersale_subgraph：售后（退换货、退款、维修）
- complaint_agent：投诉、情绪激烈、要求赔偿
- FINISH：任务完成，结束

只输出专员名字，不要其他内容。

用户最新消息：{user_msg}
当前意图：{intent}
当前风险：{risk}
"""

_VALID_AGENTS = {"presale_agent", "aftersale_subgraph", "complaint_agent"}


def supervisor_node(state: CustomerServiceState):
    round_ = state.get("supervisor_round", 0)

    # 专员已执行一轮 → 直接收尾，防止 presale/complaint_agent ↔ supervisor 死循环
    if round_ >= 1:
        tlog("supervisor", f"专员已执行（第 {round_} 轮），收尾")
        return Command(goto="save_memory")

    user_msg = state["messages"][-1].content
    intent = state.get("intent", "chat")
    risk = state.get("risk_level", 0)

    # 规则优先：高风险直接投诉 Agent
    if risk >= RISK_ESCALATE_THRESHOLD or intent == "complaint":
        next_agent = "complaint_agent"
    elif intent == "aftersale":
        next_agent = "aftersale_subgraph"
    elif intent == "presale":
        next_agent = "presale_agent"
    else:
        # 让 LLM 决定
        resp = model.invoke(
            [SystemMessage(content=SUPERVISOR_PROMPT.format(user_msg=user_msg, intent=intent, risk=risk))])
        next_agent = resp.content.strip()
        if next_agent not in _VALID_AGENTS:  # 兜底：LLM 输出 FINISH 等非法目标 → 直接收尾
            next_agent = "save_memory"

    tlog("supervisor", f"分发给 {next_agent}（第 {round_ + 1} 轮）")
    return Command(goto=next_agent, update={"supervisor_round": round_ + 1})

"""
Command(goto=..., update=...) 是 LangGraph 的动态路由指令，既能指定下一个节点，又能更新 state。
Supervisor 返回 Command 而不是普通 state dict。
规则 + LLM 混合决策，规则优先，省 LLM 调用。
supervisor_round 记录分发轮次，专员执行后回到 Supervisor 时收尾，避免死循环。
"""