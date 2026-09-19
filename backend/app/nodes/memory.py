from langgraph.prebuilt import ToolRuntime

from backend.app.graph.state import CustomerServiceState
from backend.app.trace import tlog


def load_memory_node(state: CustomerServiceState, runtime: ToolRuntime):
    """从 Store 读用户画像"""
    user_id = state.get("user_id")
    namespace = ("users", user_id)

    # 读单个 key
    store = runtime.store
    profile_item = store.get(namespace, "profile")
    profile = profile_item.value if profile_item else {}

    # 语义搜索历史记录
    history = store.search(namespace, query="投诉 退款 物流", limit=3)

    tlog("memory", f"load user={user_id}, profile={profile}, history_count={len(history)}")

    return {"user_profile": profile, "user_history": [h.value for h in history], }


def save_memory_node(state: CustomerServiceState, runtime: ToolRuntime):
    """会话结束时写回用户画像"""
    user_id = state.get("user_id")
    namespace = ("users", user_id)

    intent = state.get("intent")
    store = runtime.store
    old = store.get(namespace, "profile")
    profile = old.value if old else {}

    # 更新画像
    profile["last_intent"] = intent
    if intent == "complaint":
        profile["complaint_count"] = profile.get("complaint_count", 0) + 1

    store.put(namespace, "profile", profile)

    # 记录本次会话摘要
    store.put(namespace, f"session_{state.get('session_id')}", {"intent": intent, "order_id": state.get("order_id"),
                                                                "timestamp": __import__(
                                                                    "datetime").datetime.now().isoformat(), }, )

    return {}
