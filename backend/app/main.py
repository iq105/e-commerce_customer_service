import sys
from pathlib import Path

# 允许从任意目录运行（如 python backend/app/main.py），也能找到 backend 包
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from backend.app.config import RECURSION_LIMIT
from backend.app.graph.main_graph import graph
from backend.app.observability.langsmith import MetricsCallback

NODE_HINTS = {"classify": "🤔 正在理解您的问题...", "extract_order": "🔍 正在识别订单号...", "tools": "🔎 正在查询订单...",
              "aftersale_subgraph": "📦 正在处理售后...", "escalate": "📞 正在转接人工...", "fanout": "⚡ 正在并行查询...",
              "aggregate": "📊 正在汇总结果...", }


def print_interrupt(interrupts):
    for it in interrupts:
        value = it.value
        itype = value.get("type")
        print("\n" + "=" * 50)

        if itype == "user_confirm":
            print(f"【等待用户确认】{value.get('question')}")
            print(f"  订单: {value.get('order_id')}  金额: {value.get('amount')}")
            ans = input("确认退款吗？(yes/no): ").strip().lower()
            return {"confirmed": ans in ("yes", "y", "确认", "是")}

        elif itype == "human_approval":
            print(f"【等待人工审批】{value.get('assignee')}")
            print(f"  订单: {value.get('order_id')}  金额: {value.get('amount')}")
            print(f"  原因: {value.get('reason')}")
            ans = input("审批 (approve/reject): ").strip().lower()
            return {"approved": ans in ("approve", "approved", "通过")}

        print("=" * 50 + "\n")
    return None


def run_graph(input_data, config):
    """跑一轮图，处理 interrupt 循环"""
    current_input = input_data
    cb = MetricsCallback()
    run_config = {**config, "callbacks": [cb]}
    while True:
        interrupts = None

        for mode, chunk in graph.stream(current_input, config=run_config, stream_mode=["updates"], ):
            if mode == "updates":
                for node_name, node_output in chunk.items():
                    if node_name == "__interrupt__":
                        continue

                    # 节点提示
                    hint = NODE_HINTS.get(node_name)
                    if hint:
                        print(hint)

                    # 节点产生的 AI 消息（chatbot / 子图 / escalate / ask_order）
                    if not node_output:
                        continue
                    for msg in node_output.get("messages", []):
                        if (isinstance(msg, AIMessage) and msg.content and not msg.tool_calls):
                            print(f"客服: {msg.content}")

                # interrupt 检测
                if "__interrupt__" in chunk:
                    interrupts = chunk["__interrupt__"]
        # ★ 检查是否停在静态中断点
        state = graph.get_state(config)
        if state.next:  # 有 next 说明还没执行完
            next_node = state.next[0]
            print(f"\n⏸ 图暂停在: {next_node}")

            # 静态中断不通过 __interrupt__ 传值，需要人工决定是否继续
            ans = input(f"是否继续执行 {next_node}？(yes/no): ").strip().lower()
            if ans not in ("yes", "y"):
                print("已取消执行")
                break

            # ★ 用 None 恢复（不添加新消息，直接继续）
            current_input = None
        else:
            break
        if not interrupts:
            break

        resume_value = print_interrupt(interrupts)
        if resume_value is None:
            break
        current_input = Command(resume=resume_value)
    cb.print_summary()

def chat():
    user_id = "u_001"
    thread_id = "session_p2_001"

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT, "timeout": 60,
              "metadata": {"user_id": user_id, "channel": "web",  # web / app / phone
                           "tenant_id": "shop_001",  # 多租户
                           "env": "prod", }, "tags": ["ecom-cs", "v1.2"], }

    print("小X客服已上线，输入 quit 退出\n")

    while True:
        user_input = input("用户: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        run_graph({"messages": [HumanMessage(content=user_input)], "user_id": user_id}, config, )
        print()


if __name__ == "__main__":
    chat()
