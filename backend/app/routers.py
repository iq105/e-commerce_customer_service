from backend.app.graph.state import CustomerServiceState
from backend.app.nodes.extract import is_modify_address_msg
from backend.app.trace import tlog


def route_by_risk(state: CustomerServiceState) -> str:
    if state.get("risk_level", 0) >= 7:
        return "escalate"
    return "continue"


def route_by_intent(state: CustomerServiceState) -> str:
    intent = state.get("intent", "chat")
    order_id = state.get("order_id")
    retry = state.get("retry_count", 0)
    pending = state.get("pending_slot")
    new_addr = state.get("new_address")

    # 改地址场景（写操作，优先于普通 logistics）
    if is_modify_address_msg(state["messages"][-1].content) or pending == "new_address":
        if order_id and new_addr:
            return "modify_address"
        if retry >= 2:
            return "escalate"
        return "ask_order"

    tlog("routers", f"route_by_intent intent={intent}, order_id={order_id}, retry={retry}, pending_slot={pending}")

    # 优先级 1：正在等用户补订单号 → 只看有没有订单号
    if pending == "order_id":
        if order_id:
            return "query_order"
        if retry >= 2:
            return "escalate"
        return "ask_order"

    # 优先级 2：售后 → 独立子图（退换货、退款、维修）
    if intent == "aftersale":
        return "aftersale_subgraph" if order_id else "ask_order"

    # 优先级 3：物流 → 并行查订单 + 物流（fanout）
    if intent == "logistics":
        return "fanout" if order_id else "ask_order"

    # 优先级 4：售前 → 多 Agent 协作（Supervisor 分发）
    if intent == "presale":
        return "supervisor"

    # 优先级 5：投诉/情绪激烈 → 转人工
    if intent == "complaint":
        return "escalate"

    return "chatbot"


def route_after_tool(state: CustomerServiceState) -> str:
    """工具节点后判断是否降级"""
    if state.get("tool_failed"):
        return "fallback"
    return "continue"