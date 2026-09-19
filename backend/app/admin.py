import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import argparse

from backend.app.graph.main_graph import graph


def show_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)

    print(f"=== Thread: {thread_id} ===")
    print(f"next: {state.next}")
    print(f"created_at: {state.created_at}")
    print(f"\n--- state.values ---")
    for k, v in state.values.items():
        if k == "messages":
            print(f"messages: [{len(v)} 条]")
            for m in v[-3:]:
                print(f"  {m.type}: {str(m.content)[:80]}")
        else:
            print(f"{k}: {v}")


def update_state(thread_id: str, key: str, value: str, as_node: str):
    config = {"configurable": {"thread_id": thread_id}}

    # 类型转换（简单处理）
    try:
        value = int(value)
    except ValueError:
        try:
            value = float(value)
        except ValueError:
            pass

    new_config = graph.update_state(
        config,
        {key: value},
        as_node=as_node,   # ★ 假装是某个节点改的
    )
    print(f"✅ 已更新 {key}={value} (as_node={as_node})")
    print(f"新 checkpoint: {new_config['configurable']['checkpoint_id']}")


def list_history(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    for i, state in enumerate(graph.get_state_history(config)):
        cid = state.config["configurable"]["checkpoint_id"]
        print(f"[{i}] checkpoint={cid}, next={state.next}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", required=True)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"))
    parser.add_argument("--as-node", default="extract_order")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    if args.show:
        show_state(args.thread)
    elif args.set:
        update_state(args.thread, args.set[0], args.set[1], args.as_node)
    elif args.history:
        list_history(args.thread)
    else:
        parser.print_help()


"""
# 查看 state（在工作区根目录运行）
python -m backend.app.admin --thread session_p4_001 --show

# 修正 order_id
python -m backend.app.admin --thread session_p4_001 --set order_id 67890 --as-node extract_order

# 查看历史
python -m backend.app.admin --thread session_p4_001 --history



graph.get_state(config) 读当前 state。

graph.update_state(config, values, as_node=...) 写 state，会创建新 checkpoint。

as_node 表示"假装这个值是这个节点产生的"，影响后续路由和 reducer。

更新后，下次 graph.stream(None, config) 会从新 checkpoint 继续。
"""