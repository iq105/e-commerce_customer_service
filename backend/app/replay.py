import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import argparse

from backend.app.graph.main_graph import graph


def list_history(thread_id: str):
    """列出所有 checkpoint"""
    config = {"configurable": {"thread_id": thread_id}}
    history = list(graph.get_state_history(config))
    print(f"共 {len(history)} 个 checkpoint\n")

    for i, state in enumerate(history):
        msgs = state.values.get("messages", [])
        last = msgs[-1] if msgs else None
        print(f"[{i}] checkpoint_id={state.config['configurable']['checkpoint_id']}")
        print(f"    intent={state.values.get('intent')}, "
              f"order_id={state.values.get('order_id')}, "
              f"refund_status={state.values.get('refund_status')}")
        if last:
            print(f"    last_msg: {last.type}: {str(last.content)[:60]}")
        print()


def replay_from(thread_id: str, checkpoint_id: str):
    """从某个 checkpoint 重新执行"""
    config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id, }}
    print(f"从 checkpoint {checkpoint_id} 重新执行...\n")

    for event in graph.stream(None, config=config, stream_mode="values"):
        msgs = event.get("messages", [])
        if msgs:
            last = msgs[-1]
            print(f"{last.type}: {str(last.content)[:100]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        list_history(args.thread)
    elif args.checkpoint:
        replay_from(args.thread, args.checkpoint)

"""
# 列出会话所有 checkpoint（在工作区根目录运行）
python -m backend.app.replay --thread session_p3_001 --list

# 复现第 3 轮
python -m backend.app.replay --thread session_p3_001 --checkpoint abc123
"""