from langchain_core.messages import ToolMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import CachePolicy

from backend.app.agent.complaint import complaint_agent_node
from backend.app.agent.presale import presale_agent_node
from backend.app.agent.supervisor import supervisor_node
from backend.app.config import DEFAULT_RETRY, TOOL_RETRY, NO_RETRY
from backend.app.graph.llm import model_with_tools
from backend.app.graph.state import CustomerServiceState
from backend.app.graph.subgraphs.aftersale import aftersale_subgraph
from backend.app.memory.checkpointer import checkpointer
from backend.app.memory.store import store
from backend.app.nodes.classify import classify_node
from backend.app.nodes.escalate import escalate_node
from backend.app.nodes.extract import extract_order_node, ask_order_node
from backend.app.nodes.fallback import fallback_node
from backend.app.nodes.memory import load_memory_node, save_memory_node
from backend.app.nodes.modify_address import modify_address_node
from backend.app.nodes.parallel import fanout_node, fanout_router, query_order_task, query_logistics_task, \
    query_coupons_task, aggregate_node
from backend.app.routers import route_by_risk, route_by_intent, route_after_tool
from backend.app.tools.order import order_tools

# 2. 系统提示词
SYSTEM_PROMPT = """你是XX电商的在线客服小助手，名字叫小X。

工作要求：
1. 语气亲切、专业，用"您"称呼用户。
2. 涉及订单信息时，必须基于工具返回结果回答，不要编造。
3. 退款、改地址等写操作一律走专门的流程，不要自己承诺。
4. 查不到订单时，引导用户核对订单号或转人工。
5. 用户情绪激动时先安抚。
当前用户ID：{user_id}
当前意图：{intent}
"""

# 所有 LLM 调用自动缓存（相同输入返回相同输出）。
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache

set_llm_cache(InMemoryCache())


def _sanitize_messages(messages):
    """移除孤儿 tool_calls，避免 OpenAI 400。

    规则：如果一条 AIMessage 的 tool_calls 没有全部被 ToolMessage 响应，
    就丢掉这条 AIMessage（如果它有正文则保留正文，去掉 tool_calls）。
    """
    # 1. 收集所有已响应的 tool_call_id
    responded_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}

    cleaned = []
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            all_responded = all(tc["id"] in responded_ids for tc in m.tool_calls)
            if not all_responded:
                from backend.app.trace import tlog
                tlog("main_graph", f"发现孤儿 tool_calls，丢弃: {[tc['id'] for tc in m.tool_calls]}")
                if m.content:
                    # 有正文就保留正文，去掉 tool_calls
                    cleaned.append(AIMessage(content=m.content))
                # 无正文直接丢弃
                continue
        cleaned.append(m)
    return cleaned


# 3. 客服节点：调 LLM
def chatbot_node(state: CustomerServiceState):
    messages = _sanitize_messages(state["messages"])
    # messages = state["messages"]

    # 首次进入时注入 system prompt
    if not any(m.type == "system" for m in messages):
        from langchain_core.messages import SystemMessage
        sys = SystemMessage(
            content=SYSTEM_PROMPT.format(user_id=state.get("user_id", "unknown"), intent=state.get("intent", "chat"), ))
        messages = [sys] + messages

    response = model_with_tools.invoke(messages)
    return {"messages": [response]}


# 缓存 5 分钟
CACHE_5MIN = CachePolicy(ttl=300)

builder = StateGraph(CustomerServiceState)

# 节点
builder.add_node("load_memory", load_memory_node)
builder.add_node("save_memory", save_memory_node)
builder.add_node("classify", classify_node, retry=DEFAULT_RETRY, cache_policy=CACHE_5MIN)
builder.add_node("extract_order", extract_order_node)
builder.add_node("ask_order", ask_order_node)
builder.add_node("escalate", escalate_node)
builder.add_node("chatbot", chatbot_node, retry=DEFAULT_RETRY)
builder.add_node("tools", ToolNode(order_tools), retry=TOOL_RETRY)
builder.add_node("aftersale_subgraph", aftersale_subgraph)

builder.add_node("fanout", fanout_node)
builder.add_node("query_order_task", query_order_task)
builder.add_node("query_logistics_task", query_logistics_task)
builder.add_node("query_coupons_task", query_coupons_task)
builder.add_node("aggregate", aggregate_node)
builder.add_node("supervisor", supervisor_node)
builder.add_node("presale_agent", presale_agent_node)
builder.add_node("complaint_agent", complaint_agent_node)
# 注意：execute_refund 只在 aftersale 子图/独立链里执行，主图不注册（避免孤立节点）


builder.add_node("modify_address", modify_address_node, retry=NO_RETRY)  # ★ 写操作不重试
builder.add_node("fallback", fallback_node)

# 边
builder.add_edge(START, "load_memory")
builder.add_edge("load_memory", "classify")
# builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route_by_risk, {"escalate": "escalate", "continue": "extract_order"}, )
builder.add_conditional_edges("extract_order", route_by_intent,
                              {"ask_order": "ask_order", "aftersale_subgraph": "aftersale_subgraph",
                               "query_order": "chatbot",  # 有订单号 → 让 LLM 调工具
                               "supervisor": "supervisor",  # ★ 售前走 Supervisor
                               "fanout": "fanout",  # ★ 物流走并行
                               "modify_address": "modify_address",  # ★ 改地址
                               "escalate": "escalate", "chatbot": "chatbot", }, )
# fanout 用条件边（fanout_router 返回 Send 列表）
builder.add_conditional_edges("fanout", fanout_router,
                              ["query_order_task", "query_logistics_task", "query_coupons_task"], )
# 所有并行任务 → aggregate
for n in ["query_order_task", "query_logistics_task", "query_coupons_task"]:
    builder.add_edge(n, "aggregate")

builder.add_edge("aggregate", "chatbot")

# 追问完等用户下一条消息，不在同轮内回环（否则 retry 会在一轮内涨爆直接转人工）

for n in ["escalate", "aftersale_subgraph", "ask_order", "modify_address"]:
    builder.add_edge(n, "save_memory")

# ⚠️ 重要：chatbot / tools 千万不能同时有"静态边 + 条件边"，否则 LangGraph 会 fan-out 两路全走。
# chatbot 只挂条件边：LLM 要调工具 → tools；不调 → save_memory。
builder.add_conditional_edges("chatbot", tools_condition,
                              {"tools": "tools", END: "save_memory"}, )
# tools 只挂条件边：失败 → fallback；成功 → 回 chatbot 继续。
builder.add_conditional_edges("tools", route_after_tool, {"fallback": "fallback", "continue": "chatbot"}, )

builder.add_edge("presale_agent", "supervisor")  # 循环
builder.add_edge("complaint_agent", "supervisor")  # 循环
# supervisor 通过 Command(goto=...) 决定去向：第一轮分发专员，专员完成后再回 supervisor 时收尾

builder.add_edge("save_memory", END)
builder.add_edge("fallback", "escalate")

graph = builder.compile(checkpointer=checkpointer, store=store)
