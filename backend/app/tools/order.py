# 模拟订单库（P0 先用内存，P1 再接真实 DB）
import os
import random

# 故障注入开关：仅测试/演练用，默认关闭。设置 MOCK_FAIL_RATE=0.3 可模拟 30% 概率失败。
_MOCK_FAIL_RATE = float(os.getenv("MOCK_FAIL_RATE", "0"))

from backend.app.tools.coupons import query_coupons
from backend.app.tools.logistics import query_logistics
from backend.app.tools.refund import execute_refund

FAKE_ORDERS = {"12345": {"order_id": "12345", "status": "已发货", "items": ["iPhone 16 Pro x1"], "amount": 8999,
                         "address": "成都市高新区天府大道 1 号", "logistics": "顺丰 SF1234567890，预计明天送达",
                         "refundable": True, },
               "67890": {"order_id": "67890", "status": "待付款", "items": ["AirPods Pro x1"], "amount": 1899,
                         "address": "成都市武侯区人民南路 2 号", "logistics": "未发货", "refundable": True, }, }

from langchain_core.tools import tool


@tool
def query_order(order_id: str):
    """根据订单ID查询订单状态、商品、金额、地址、物流信息

    Args:
        order_id: 订单号，订单id
        """
    if _MOCK_FAIL_RATE > 0 and random.random() < _MOCK_FAIL_RATE:
        raise ConnectionError(f"订单服务超时: {order_id}")
    order = FAKE_ORDERS.get(order_id, None)
    if not order:
        return {"error": f"未找到订单 {order_id}，请确认订单号是否正确"}
    return FAKE_ORDERS[order_id]


order_tools = [query_order, execute_refund, query_logistics, query_coupons, ]
