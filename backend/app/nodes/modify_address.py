from langchain_core.messages import AIMessage

from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog


def modify_address_node(state: CustomerServiceState):
    """改地址（敏感操作，编译时声明 interrupt_before）"""
    new_addr = state.get("new_address")
    oid = state.get("order_id")

    tlog("modify_address", f"订单 {oid} 改地址为 {new_addr}")

    # 模拟调用订单服务
    return {"messages": [AIMessage(content=f"订单 {oid} 的收货地址已修改为：{new_addr}")], "address_modified": True, }
