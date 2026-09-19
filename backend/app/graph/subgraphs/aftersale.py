from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from tenacity import stop_after_attempt, wait_exponential, retry, RetryError

from backend.app.config import NO_RETRY, REFUND_APPROVAL_THRESHOLD
from backend.app.graph.state import CustomerServiceState
from backend.app.memory.checkpointer import checkpointer
from backend.app.memory.store import store
from backend.app.nodes.fallback import fallback_node
from backend.app.nodes.modify_address import modify_address_node
from backend.app.routers import route_after_tool
from backend.app.trace import tlog


# ---------- 子图节点 ----------

# def query_order_node(state: CustomerServiceState):
#     """查订单信息"""
#     from backend.app.tools.order import query_order
#     oid = state.get("order_id")
#     print(f"[aftersale.query_order] order_id={oid}")
#     info = query_order.invoke({"order_id": oid})
#     return {"order_info": info}

def query_order_node(state: CustomerServiceState):
    """查订单，带降级"""
    oid = state.get("order_id")
    tlog("aftersale", f"query_order order_id={oid}")

    # 方式 1：手动 try/except + 降级
    try:
        from backend.app.tools.order import query_order
        info = query_order.invoke({"order_id": oid})
        return {"order_info": info, "tool_failed": False}
    except Exception as e:
        tlog("aftersale", f"query_order 失败: {e}，走降级")
        return {"order_info": None, "tool_failed": True, "fallback_reason": f"订单查询失败: {e}", }


# 方式 2：用 tenacity 做更精细的重试 + 降级
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=False, )
def _query_order_with_retry(oid):
    from backend.app.tools.order import query_order
    return query_order.invoke({"order_id": oid})


def query_order_node_v2(state: CustomerServiceState):
    oid = state.get("order_id")
    tlog("aftersale", f"query_order_v2 order_id={oid}")

    try:
        info = _query_order_with_retry(oid)
        return {"order_info": info, "tool_failed": False}
    except RetryError as e:
        tlog("aftersale", f"query_order_v2 重试耗尽，降级")
        return {"order_info": None, "tool_failed": True, "fallback_reason": str(e), }


def check_policy_node(state: CustomerServiceState):
    """校验退款政策"""

    info = state.get("order_info") or {}
    tlog("aftersale", f"check_policy info={info}")

    if info.get("error"):
        return {"refund_status": "rejected", "messages": [AIMessage(content=f"无法处理：{info['error']}")], }

    refundable = info.get("refundable")
    if refundable is False:
        return {"refund_status": "rejected", "messages": [AIMessage(content="该订单不支持退款，请联系人工。")], }

    return {"refund_amount": info.get("amount", 0), "refund_reason": "用户申请退款", "refund_status": "pending", }


def propose_node(state: CustomerServiceState):
    """向用户提出退款方案，等待确认"""
    amount = state.get("refund_amount")
    oid = state.get("order_id")
    return {"messages": [AIMessage(content=f"订单 {oid} 可退款 {amount} 元。确认要退款吗？回复「确认」继续。")], }


def confirm_node(state: CustomerServiceState):
    """★ Interrupt：等待用户确认退款"""
    tlog("aftersale", "confirm 触发 interrupt，等待用户确认")

    decision = interrupt({"type": "user_confirm", "action": "refund", "order_id": state.get("order_id"),
                          "amount": state.get("refund_amount"), "question": "确认退款吗？", })

    # 恢复后执行到这里，decision 是前端传回的值
    tlog("aftersale", f"confirm 用户回复: {decision}")

    if decision.get("confirmed"):
        return {"user_confirmed": True}
    else:
        return {"user_confirmed": False, "refund_status": "cancelled",
                "messages": [AIMessage(content="已取消退款。如有其他问题请告诉我。")], }


def check_amount_node(state: CustomerServiceState):
    """金额超过阈值 → 需要人工审批"""
    amount = state.get("refund_amount", 0)
    threshold = REFUND_APPROVAL_THRESHOLD

    if amount > threshold:
        tlog("aftersale", f"check_amount {amount} > {threshold}，需人工审批")
        return {"refund_status": "need_human_approval"}
    else:
        tlog("aftersale", f"check_amount {amount} <= {threshold}，直接执行")
        return {"human_approved": True}


def human_approval_node(state: CustomerServiceState):
    """★ Interrupt：等待人工审批"""
    tlog("aftersale", "human_approval 触发 interrupt，等待人工")

    decision = interrupt({"type": "human_approval", "action": "refund", "order_id": state.get("order_id"),
                          "amount": state.get("refund_amount"), "reason": state.get("refund_reason"),
                          "assignee": "工号 A1024", })

    tlog("aftersale", f"human_approval 人工回复: {decision}")

    if decision.get("approved"):
        return {"human_approved": True}
    else:
        return {"human_approved": False, "refund_status": "rejected",
                "messages": [AIMessage(content="很抱歉，您的退款申请未通过审批。")], }


def execute_refund_node(state: CustomerServiceState):
    """执行退款（确定性调用，不走 LLM）"""
    from backend.app.tools.refund import execute_refund
    tlog("aftersale", "execute_refund 执行退款")
    result = execute_refund.invoke({"order_id": state.get("order_id"), "amount": state.get("refund_amount"),
                                    "reason": state.get("refund_reason"), })
    return {"refund_id": result["refund_id"], "refund_status": "done",
            "messages": [AIMessage(content=result["message"] + f"，退款单号 {result['refund_id']}。")], }


def reject_node(state: CustomerServiceState):
    """拒绝路径的收尾节点"""
    status = state.get("refund_status")
    if status in ("cancelled", "rejected"):
        return {}  # 已在 confirm_node 输出消息
    return {"messages": [AIMessage(content="退款未完成，如需帮助请转人工。")]}


# ---------- 路由 ----------

def route_after_policy(state: CustomerServiceState) -> str:
    if state.get("refund_status") == "rejected":
        return "reject"
    return "propose"


def route_after_confirm(state: CustomerServiceState) -> str:
    if state.get("user_confirmed"):
        return "check_amount"
    return "reject"


def route_after_amount(state: CustomerServiceState) -> str:
    if state.get("human_approved") is True:
        return "execute"
    if state.get("refund_status") == "need_human_approval":
        return "human_approval"
    return "reject"


def route_after_human(state: CustomerServiceState) -> str:
    if state.get("human_approved"):
        return "execute"
    return "reject"


# ---------- 构建子图 ----------

def build_aftersale_subgraph():
    builder = StateGraph(CustomerServiceState)

    builder.add_node("query_order", query_order_node)
    builder.add_node("check_policy", check_policy_node)
    builder.add_node("propose", propose_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("check_amount", check_amount_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("execute_refund", execute_refund_node)
    builder.add_node("reject", reject_node)
    builder.add_node("fallback", fallback_node)
    builder.add_node("modify_address", modify_address_node, retry=NO_RETRY)
    builder.add_edge(START, "query_order")

    builder.add_conditional_edges("query_order", route_after_tool,
                                  {"fallback": "fallback", "continue": "check_policy"}, )
    builder.add_edge("fallback", END)  # 子图内降级

    builder.add_edge("query_order", "check_policy")

    builder.add_conditional_edges("check_policy", route_after_policy, {"propose": "propose", "reject": "reject"}, )

    builder.add_edge("propose", "confirm")

    builder.add_conditional_edges("confirm", route_after_confirm,
                                  {"check_amount": "check_amount", "reject": "reject"}, )

    builder.add_conditional_edges("check_amount", route_after_amount,
                                  {"human_approval": "human_approval", "execute": "execute_refund",
                                   "reject": "reject", }, )

    builder.add_conditional_edges("human_approval", route_after_human,
                                  {"execute": "execute_refund", "reject": "reject"}, )

    builder.add_edge("execute_refund", END)
    builder.add_edge("reject", END)

    return builder.compile(checkpointer=checkpointer, store=store)


aftersale_subgraph = build_aftersale_subgraph()
