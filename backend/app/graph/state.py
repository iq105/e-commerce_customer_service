import operator
from typing import TypedDict, Annotated, Literal

from langchain_core.messages import AnyMessage

Intent = Literal["presale", "logistics", "aftersale", "complaint", "chat"]


class CustomerServiceState(TypedDict):
    # Annotated[list, add_messages] 是 LangGraph 状态合并的核心。没有它，每次节点返回的 messages 会覆盖而不是追加。
    messages: Annotated[list[AnyMessage], operator.add]
    user_id: str
    session_id: str

    # 风险
    risk_level: int  # 0-10，越高越需要人工
    intent: Intent | None
    human_approved: bool | None

    # 记忆
    user_profile: dict

    # 控制
    retry_count: int  # 追问次数，防死循环，是防死循环的关键，追问超过 N 次就转人工。
    supervisor_round: int  # Supervisor 分发轮次，防止多 Agent 死循环

    # P1 新增
    order_id: str | None
    pending_slot: str | None  # 用来标记"还缺什么参数"，让图知道该走追问还是走工具。
    new_address: str | None  # 改地址目标（logistics 改地址场景）

    # P2 新增 —— 售后流程
    order_info: dict | None  # 子图查到的订单快照
    refund_amount: float | None  # 退款金额
    refund_reason: str | None  # 退款原因
    user_confirmed: bool | None  # 用户是否确认
    refund_id: str | None  # 退款单号
    refund_status: str | None  # pending / approved / rejected / done

    # P3 新增
    user_history: list
    parallel_results: Annotated[list, operator.add]   # ★ 并行结果累加
