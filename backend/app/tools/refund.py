from datetime import datetime
import uuid

from langchain_core.tools import tool

@tool
def execute_refund(order_id: str, amount: float, reason: str) -> dict:
    """执行退款操作。仅在用户确认且（如需要）人工审批通过后调用。

    Args:
        order_id: 订单号
        amount: 退款金额
        reason: 退款原因
    """
    refund_id = f"RF{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    return {
        "refund_id": refund_id,
        "order_id": order_id,
        "amount": amount,
        "status": "已提交",
        "message": f"退款 {amount} 元已提交，3-5 个工作日到账",
    }