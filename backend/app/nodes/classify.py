from langchain_core.messages import SystemMessage

from backend.app.graph.llm import model
from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog

CLASSIFY_PROMPT = """你是电商客服的意图分类器。请把用户最新一句话分类到以下之一：

- presale：售前咨询（商品、价格、优惠、库存）
- logistics：物流/订单查询（查订单、查快递、改地址）
- aftersale：售后（退换货、维修、发票）
- complaint：投诉/差评/情绪激烈
- chat：寒暄、闲聊、其他

同时评估风险等级 risk_level（0-10）：
- 0-3：普通咨询
- 4-6：涉及退款/改地址等写操作
- 7-10：投诉、辱骂、要求赔偿、监管投诉

只输出 JSON，格式：
{{"intent": "...", "risk_level": 0, "reason": "..."}}

用户最新消息：{user_msg}
"""

# 意图，正确做法是先使用正则匹配，匹配不上使用大模型兜底
def classify_node(state: CustomerServiceState):
    # 上轮在向用户追问订单号/新地址 → 本轮保留原意图，避免把"订单号 67890"重新分类成物流
    if state.get("pending_slot") in ("order_id", "new_address"):
        return {}

    user_msg = state["messages"][-1].content

    resp = model.invoke([SystemMessage(content=CLASSIFY_PROMPT.format(user_msg=user_msg))])

    import json, re
    text = resp.content.strip()
    # 容错：剥掉 markdown 代码块
    text = re.sub(r"^```json|```$", "", text, flags=re.M).strip()
    try:
        data = json.loads(text)
    except Exception as e:
        tlog("classify", f"意图分类 JSON 解析失败（回退 chat），原始输出={resp.content[:100]!r}，err={e}")
        data = {"intent": "chat", "risk_level": 0}

    if data.get("intent") not in ("presale", "logistics", "aftersale", "complaint", "chat"):
        tlog("classify", f"模型返回非法意图 {data.get('intent')}，回退 chat")
        data["intent"] = "chat"

    return {"intent": data.get("intent", "chat"), "risk_level": data.get("risk_level", 0),
            "supervisor_round": 0,  # 每轮重置，避免跨多轮残留导致死循环判断失效
            }
