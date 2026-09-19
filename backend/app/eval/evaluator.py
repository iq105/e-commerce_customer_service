import json
import re
import uuid
from typing import List, Dict, Any, Tuple

from langchain_core.messages import AIMessage, HumanMessage

from backend.app.config import RECURSION_LIMIT
from backend.app.graph.llm import model


def _strip_json(text: str) -> str:
    return re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()


def run_case(case: dict, graph, max_interrupts: int = 3) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Run a single test case, automatically resuming interrupts.

    Supports multi-turn inputs via list in `case["input"]`.
    Custom resume values per interrupt type can be supplied in
    `case["resume_values"]` (maps interrupt type to resume payload).
    """
    thread_id = f"eval_{case['id']}_{uuid.uuid4().hex[:6]}"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}

    final_state = None
    interrupts: List[Dict[str, Any]] = []

    inputs: List[str] = case["input"] if isinstance(case["input"], list) else [case["input"]]

    for turn_idx, text in enumerate(inputs):
        input_data: Any = {"messages": [HumanMessage(content=text)], "user_id": "eval_user"}

        # Process the current turn; may loop for interrupt/resume cycles
        for _ in range(max_interrupts + 1):
            for mode, chunk in graph.stream(input_data, config=config, stream_mode=["updates", "values"]):
                if mode == "updates":
                    if "__interrupt__" in chunk:
                        for it in chunk["__interrupt__"]:
                            interrupts.append(it.value)
                elif mode == "values":
                    final_state = chunk

            if not interrupts:
                break

            last_it = interrupts[-1]
            itype = last_it.get("type")

            # Determine resume payload
            resume_map = case.get("resume_values", {})
            if itype in resume_map:
                from langgraph.types import Command
                input_data = Command(resume=resume_map[itype])
            elif itype == "user_confirm":
                from langgraph.types import Command
                input_data = Command(resume={"confirmed": True})
            elif itype == "human_approval":
                from langgraph.types import Command
                input_data = Command(resume={"approved": True})
            else:
                break

    # 注入到 state 供 check_rules 断言（stream 返回的 dict 是独立副本）
    if final_state is not None:
        final_state["__interrupts__"] = list(interrupts)

    return final_state, interrupts


def check_rules(case: dict, state: dict) -> List[str]:
    """Rule-based assertions on the final state."""
    if state is None:
        return ["no_state"]

    msgs = state.get("messages", [])
    ai_reply = ""
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and m.content:
            ai_reply = m.content
            break

    errors: List[str] = []

    expected_intent = case.get("expected_intent")
    if expected_intent and state.get("intent") != expected_intent:
        errors.append(f"intent expected={expected_intent} got={state.get('intent')}")

    expected_risk = case.get("expected_risk_gte")
    if expected_risk is not None:
        if state.get("risk_level", 0) < expected_risk:
            errors.append(f"risk_level expected>={expected_risk} got={state.get('risk_level')}")

    expected_contains = case.get("expected_contains")
    if expected_contains:
        for kw in expected_contains:
            if kw not in ai_reply:
                errors.append(f"expected contains '{kw}' but reply={ai_reply[:120]}")
                break

    expected_interrupt = case.get("expected_has_interrupt")
    if expected_interrupt is not None:
        has_interrupt = bool(state.get("__interrupts__"))
        if expected_interrupt and not has_interrupt:
            errors.append("expected interrupt but none occurred")

    return errors


def llm_judge(question: str, answer: str) -> Dict[str, Any]:
    """Ask LLM to judge the reply quality."""
    prompt = f"""请从以下四个维度对客服回复打分（1-5分）并给出理由：
1. relevance（相关性）2. accuracy（准确性）3. tone（语气）4. completeness（完整性）

用户问题：{question}
客服回复：{answer}

返回 JSON 格式：
{{"relevance": 分数, "accuracy": 分数, "tone": 分数, "completeness": 分数, "理由": "简要说明"}}
"""
    try:
        resp = model.invoke(prompt)
        return json.loads(_strip_json(resp.content))
    except Exception as e:
        return {"error": str(e)}
