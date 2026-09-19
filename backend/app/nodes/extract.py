import re
from langchain_core.messages import SystemMessage

from backend.app.graph.llm import model as llm
from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog

# 改地址意图关键词（命中则走 modify_address 链路）
MODIFY_ADDR_HINTS = ("改地址", "修改地址", "换地址", "更换地址", "改收货地址", "修改收货地址", "换个地址",
                     "改到", "地址改为")

EXTRACT_PROMPT = """从用户消息中提取信息。
1. 订单号规则：5-20 位数字或字母数字组合。没提到订单号就返回 null。
2. 如果用户在改地址，提取目标新地址 new_address；不涉及改地址就返回 null。

只输出 JSON：
{{"order_id": "12345", "new_address": "新地址"}}
或 {{"order_id": null, "new_address": null}}

用户消息：{user_msg}
"""


def is_modify_address_msg(user_msg: str) -> bool:
    """粗略判断用户是否在改地址"""
    return any(h in user_msg for h in MODIFY_ADDR_HINTS)


def extract_order_node(state: CustomerServiceState):
    # 已经有订单号就跳过 ，这个有问题，
    #if state.get("order_id"):
    #    return {}

    user_msg = state["messages"][-1].content
    resp = llm.invoke([SystemMessage(content=EXTRACT_PROMPT.format(user_msg=user_msg))])

    import json, re
    text = re.sub(r"^```json|```$", "", resp.content.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
        oid = data.get("order_id")
        new_addr = data.get("new_address")
    except Exception as e:
        tlog("extract", f"提取 JSON 解析失败，err={e}")
        oid, new_addr = None, None

    # 兜底：正则扫订单号
    if not oid:
        m = re.search(r"\b\d{5,20}\b", user_msg)
        if m:
            oid = m.group()

    update = {}
    if oid:
        update["order_id"] = oid
    if new_addr:
        update["new_address"] = new_addr

    # 提取到了（订单号或新地址）→ 重置重试计数并清 pending
    if update:
        update["retry_count"] = 0
        update["pending_slot"] = None
    return update


def ask_order_node(state: CustomerServiceState):
    """缺订单号/地址时追问"""
    from langchain_core.messages import AIMessage
    current_retry = state.get("retry_count", 0)
    tlog("extract", f"ask_order 当前 retry_count={current_retry}, pending={state.get('pending_slot')}")

    # 改地址：已有订单号但缺地址 → 问地址；否则问订单号
    if (state.get("pending_slot") == "new_address" or is_modify_address_msg(state["messages"][-1].content)) and \
            state.get("order_id"):
        return {"messages": [AIMessage(content="请问新地址是什么呢？")], "pending_slot": "new_address",
                "retry_count": state.get("retry_count", 0) + 1, }

    return {"messages": [AIMessage(content="请提供您的订单号，我来帮您查询。")], "pending_slot": "order_id",
            "retry_count": state.get("retry_count", 0) + 1, }
