from langchain_core.tools import tool




@tool
def query_logistics(order_id: str) -> dict:
    """查询订单物流轨迹。

    Args:
        order_id: 订单号
    """
    from backend.app.tools.order import FAKE_ORDERS
    order = FAKE_ORDERS.get(order_id)
    if not order:
        return {"error": f"未找到订单 {order_id}"}
    return {"order_id": order_id, "logistics": order.get("logistics", "无物流信息")}