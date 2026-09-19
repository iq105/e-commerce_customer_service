from langgraph.types import Send
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog


def _build_tasks(state: CustomerServiceState) -> list[Send]:
    """根据意图决定并行发起哪些查询。

    注意：目前只有物流意图走到 fanout（见 routers.route_by_intent）。
    presale 走 supervisor → presale_agent，由专员自取优惠券，不经过此处。
    """
    order_id = state.get("order_id")
    tasks = []

    # 物流意图 → 并行查订单 + 物流
    if state.get("intent") == "logistics" and order_id:
        tasks.append(Send("query_order_task", {"order_id": order_id}))
        tasks.append(Send("query_logistics_task", {"order_id": order_id}))

    return tasks


def fanout_node(state: CustomerServiceState):
    """节点本身只打日志，并行分流交给条件边 fanout_router"""
    tasks = _build_tasks(state)
    tlog("parallel", f"fanout 发起 {len(tasks)} 个并行任务")
    return {}


def fanout_router(state: CustomerServiceState) -> list[Send]:
    """条件边：返回 Send 列表，驱动并行执行"""
    return _build_tasks(state)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=3),
       retry=retry_if_exception_type(Exception), reraise=False)
def _query_order_with_retry(order_id: str) -> dict:
    from backend.app.tools.order import query_order
    return query_order.invoke({"order_id": order_id})


def query_order_task(state: dict):
    """并行子任务：查订单（重试后仍失败则降级为 error 字段，不让整轮报错）"""
    try:
        result = _query_order_with_retry(state["order_id"])
        return {"parallel_results": [{"type": "order", "data": result}]}
    except Exception as e:
        return {"parallel_results": [{"type": "order", "data": {"error": f"订单查询失败: {e}"}}]}


def query_logistics_task(state: dict):
    try:
        from backend.app.tools.logistics import query_logistics
        result = query_logistics.invoke({"order_id": state["order_id"]})
        return {"parallel_results": [{"type": "logistics", "data": result}]}
    except Exception as e:
        return {"parallel_results": [{"type": "logistics", "data": {"error": f"物流查询失败: {e}"}}]}


def query_coupons_task(state: dict):
    try:
        from backend.app.tools.coupons import query_coupons
        result = query_coupons.invoke({"user_id": state["user_id"]})
        return {"parallel_results": [{"type": "coupons", "data": result}]}
    except Exception as e:
        return {"parallel_results": [{"type": "coupons", "data": {"error": f"优惠券查询失败: {e}"}}]}


def aggregate_node(state: CustomerServiceState):
    """汇总并行结果"""
    results = state.get("parallel_results", [])
    tlog("parallel", f"aggregate 收到 {len(results)} 个并行结果")
    # 结果已经在 state 里，后续 chatbot 会用到
    return {}