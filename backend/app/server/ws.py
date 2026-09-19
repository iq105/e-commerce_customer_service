import asyncio
import json
import threading
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from backend.app.config import RECURSION_LIMIT
from backend.app.graph.main_graph import graph
from backend.app.observability.langsmith import MetricsCallback

router = APIRouter()

# 并发上限：同进程最多同时跑多少个图执行线程，防止压测时线程无限增长（AGENT.md §17）
MAX_GRAPH_THREADS = 16
_thread_slots = threading.BoundedSemaphore(MAX_GRAPH_THREADS)

# 节点提示
NODE_HINTS = {
    "classify": "🤔 正在理解您的问题...",
    "extract_order": "🔍 正在识别订单号...",
    "tools": "🔎 正在查询订单...",
    "aftersale_subgraph": "📦 正在处理售后...",
    "query_order": "🔎 正在核对订单...",
    "check_policy": "📋 正在校验退款政策...",
    "propose": "",
    "confirm": "",
    "escalate": "📞 正在转接人工...",
    "supervisor": "🧑‍💼 正在分配专员...",
    "presale_agent": "🛍️ 售前顾问为您服务...",
    "fanout": "⚡ 正在并行查询...",
    "aggregate": "📊 正在汇总结果...",
    "fallback": "⚠️ 系统繁忙，正在降级...",
    "modify_address": "✏️ 正在修改地址...",
    "execute_refund": "💸 正在执行退款...",
}


def _print_summary_safe(cb: MetricsCallback):
    """MetricsCallback.print_summary 里的 emoji 在 GBK 控制台会编码崩溃，包一层保护"""
    try:
        cb.print_summary()
    except Exception as e:
        print(f"[metrics] summary print failed: {e}")


async def _stream_graph(ws: WebSocket, input_data, config, cb: MetricsCallback):
    """跑一轮图，流式推送。

    graph.compile 用的是同步 PostgresSaver/PostgresStore，切到 async 时
    aget_tuple 会抛 NotImplementedError（见 checkpoint.base），所以这里
    把同步 graph.stream 放进独立线程，用 asyncio.Queue 把事件回传给 event loop。
    """
    run_config = {**config, "callbacks": [cb]}
    interrupts = []
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _consume():
        acquired = _thread_slots.acquire(blocking=False)
        if not acquired:
            # 并发已满：不再新开线程，通知前端稍等
            asyncio.run_coroutine_threadsafe(
                queue.put(("__error__", RuntimeError("服务器繁忙，请稍后再试"))), loop).result()
            return
        try:
            for mode, chunk in graph.stream(input_data, config=run_config,
                                            stream_mode=["messages", "updates"]):
                asyncio.run_coroutine_threadsafe(queue.put((mode, chunk)), loop).result()
        except Exception as e:
            asyncio.run_coroutine_threadsafe(queue.put(("__error__", e)), loop).result()
        finally:
            _thread_slots.release()
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    threading.Thread(target=_consume, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            break
        mode, chunk = item
        if mode == "__error__":
            raise chunk

        if mode == "messages":
            msg, metadata = chunk
            node = metadata.get("langgraph_node")
            # 只推 chatbot 节点的 token（打字机效果）
            if node != "chatbot":
                continue
            if not isinstance(msg, AIMessage):
                continue
            if not msg.content or msg.tool_calls:
                continue
            await ws.send_json({
                "type": "token",
                "node": node,
                "content": msg.content,
                "msg_id": msg.id,
            })

        elif mode == "updates":
            for node_name, node_output in chunk.items():
                if node_name == "__interrupt__":
                    continue

                # 节点提示
                hint = NODE_HINTS.get(node_name)
                if hint:
                    await ws.send_json({"type": "node", "name": node_name, "hint": hint})

                # 非 chatbot 节点的 AI 消息（escalate / ask_order / 子图）
                if node_name != "chatbot" and node_output:
                    for m in node_output.get("messages", []):
                        if isinstance(m, AIMessage) and m.content and not m.tool_calls:
                            await ws.send_json({
                                "type": "assistant_message",
                                "node": node_name,
                                "content": m.content,
                            })

            # interrupt
            if "__interrupt__" in chunk:
                for it in chunk["__interrupt__"]:
                    interrupts.append(it.value)
                    await ws.send_json({
                        "type": "interrupt",
                        "value": it.value,
                    })

    # 静态中断检查
    state = graph.get_state(config)
    if state.next:
        await ws.send_json({
            "type": "static_interrupt",
            "next": list(state.next),
        })
    else:
        await ws.send_json({"type": "done"})

    return interrupts


@router.websocket("/ws/{user_id}/{session_id}")
async def ws_endpoint(websocket: WebSocket, user_id: str, session_id: str):
    await websocket.accept()
    thread_id = f"{user_id}_{session_id}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
        "timeout": 60,
        "metadata": {"user_id": user_id, "channel": "web"},
        "tags": ["ecom-cs", "websocket"],
    }

    await websocket.send_json({"type": "ready", "thread_id": thread_id})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                from backend.app.trace import set_trace_id
                set_trace_id()
                cb = MetricsCallback()
                input_data = {
                    "messages": [HumanMessage(content=data["content"])],
                    "user_id": user_id,
                }
                await _stream_graph(websocket, input_data, config, cb)
                _print_summary_safe(cb)

            elif msg_type == "resume":
                from backend.app.trace import set_trace_id
                set_trace_id()
                cb = MetricsCallback()
                value = data.get("value")
                # value=None 表示静态中断继续
                input_data = Command(resume=value) if value is not None else None
                await _stream_graph(websocket, input_data, config, cb)
                _print_summary_safe(cb)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        print(f"[ws] {user_id}/{session_id} 断开")
    except Exception as e:
        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "message": f"{type(e).__name__}: {e}"[:200]})
        except Exception as e2:
            print(f"[ws] 发送错误消息失败: {e2}")