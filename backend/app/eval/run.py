import sys
import io
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time

from backend.app.eval.evaluator import check_rules, llm_judge, run_case
from backend.app.eval.test_cases import TEST_CASES


def main():
    from backend.app.graph.main_graph import graph

    passed = 0
    failed = 0
    total_time = 0.0

    for case in TEST_CASES:
        t0 = time.perf_counter()
        state, _ = run_case(case, graph)
        elapsed = time.perf_counter() - t0
        total_time += elapsed

        errors = check_rules(case, state)
        ai_reply = ""
        msgs = state.get("messages", []) if state else []
        for m in reversed(msgs):
            if hasattr(m, "content") and m.content:
                ai_reply = m.content
                break

        llm_score = None
        if not errors:
            llm_score = llm_judge(case["input"] if isinstance(case["input"], str) else case["input"][0], ai_reply)

        status = "PASS" if not errors else "FAIL"
        print(f"[{case['id']}] {status} ({elapsed:.1f}s)")

        if errors:
            print(f"  rules: {errors}")
            print(f"  reply: {ai_reply[:120]}")
            failed += 1
        else:
            if llm_score and "error" not in llm_score:
                avg = sum(v for k, v in llm_score.items() if isinstance(v, int)) / 4
                print(f"  llm_score: {avg:.1f}/5  detail={llm_score}")
            passed += 1

    print(f"\n=== SUMMARY: {passed}/{passed + failed} passed, avg {total_time / len(TEST_CASES):.1f}s/case ===")


if __name__ == "__main__":
    main()
