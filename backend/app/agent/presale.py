from langchain_core.messages import AIMessage, SystemMessage

from backend.app.graph.state import CustomerServiceState

from backend.app.graph.llm import model
PRESALE_PROMPT = """你是电商售前顾问，负责商品咨询、价格、优惠、库存问题。
用户画像：{profile}
可用优惠券：{coupons}
请专业、热情地回答，不要编造库存和价格。
"""


def _load_coupons(state: CustomerServiceState):
    """售前专员自取优惠券数据（fanout 不覆盖 presale，避免依赖死路径）"""
    user_id = state.get("user_id")
    if not user_id:
        return "暂无用户信息"
    try:
        from backend.app.tools.coupons import query_coupons
        result = query_coupons.invoke({"user_id": user_id})
        if isinstance(result, dict) and "error" in result:
            return f"查询失败：{result['error']}"
        return result
    except Exception as e:
        return f"查询失败：{e}"


def presale_agent_node(state: CustomerServiceState):
    profile = state.get("user_profile", {})
    coupons = _load_coupons(state)

    resp = model.invoke(
        [SystemMessage(content=PRESALE_PROMPT.format(profile=profile, coupons=coupons)), *state["messages"], ])
    return {"messages": [AIMessage(content=resp.content)]}