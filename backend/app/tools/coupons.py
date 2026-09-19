from langchain_core.tools import tool


@tool
def query_coupons(user_id: str) -> dict:
    """查询用户可用优惠券。

    Args:
        user_id: 用户ID
    """
    FAKE_COUPONS = {"u_001": [{"code": "C20", "desc": "满100减20"}, {"code": "C100", "desc": "满500减100"}, ], }
    return {"user_id": user_id, "coupons": FAKE_COUPONS.get(user_id, [])}
