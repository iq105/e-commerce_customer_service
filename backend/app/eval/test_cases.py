# backend/app/eval/test_cases.py

TEST_CASES = [
    # ==================== A. 基础意图分类 ====================
    {
        "id": "tc_01",
        "input": "你好",
        "expected_intent": "chat",
        "expected_contains": ["客服"],
    },
    {
        "id": "tc_02",
        "input": "iPhone 16 Pro 有货吗",
        "expected_intent": "presale",
    },
    {
        "id": "tc_03",
        "input": "查订单 12345 的物流",
        "expected_intent": "logistics",
        "expected_contains": ["12345"],
    },
    {
        "id": "tc_04",
        "input": "我要退款",
        "expected_intent": "aftersale",
    },
    {
        "id": "tc_05",
        "input": "你们太差了！我要投诉！",
        "expected_intent": "complaint",
        "expected_risk_gte": 7,
    },
    {
        "id": "tc_06",
        "input": "再不处理我就打12315投诉",
        "expected_risk_gte": 7,
    },

    # ==================== B. 订单号提取与追问 ====================
    {
        "id": "tc_10",
        "input": ["查一下我的订单", "不知道", "算了不知道"],
        "expected_has_interrupt": False,
        "expected_contains": ["人工"],
    },
    {
        "id": "tc_11",
        "input": ["退款", "订单号 67890"],
        "expected_has_interrupt": True,
    },
    {
        "id": "tc_12",
        "input": "订单号是 abc123456xyz",
        "expected_contains": ["没有查询到"],
    },

    # ==================== C. 物流并行查询 ====================
    {
        "id": "tc_20",
        "input": "查一下订单 12345 的物流",
        "expected_contains": ["12345"],
    },
    {
        "id": "tc_21",
        "input": "查一下订单 99999 的物流",
        "expected_contains": ["99999"],
    },

    # ==================== D. 售前多Agent ====================
    {
        "id": "tc_30",
        "input": "有什么优惠活动吗",
        "expected_intent": "presale",
    },

    # ==================== E. 售后退款 ====================
    {
        "id": "tc_40",
        "input": ["退款", "订单号 67890"],
        "expected_has_interrupt": True,
    },
    {
        "id": "tc_41",
        "input": ["退款", "订单号 12345"],
        "expected_has_interrupt": True,
    },
    {
        "id": "tc_42",
        "input": ["退款", "订单号 67890"],
        "resume_values": {"user_confirm": {"confirmed": False}},
        "expected_contains": ["取消"],
    },
    {
        "id": "tc_43",
        "input": ["退款", "订单号 12345"],
        "resume_values": {"user_confirm": {"confirmed": True}, "human_approval": {"approved": False}},
        "expected_contains": ["未通过"],
    },

    # ==================== F. 工具查询 ====================
    {
        "id": "tc_50",
        "input": "查订单 12345",
        "expected_contains": ["12345"],
    },
    {
        "id": "tc_51",
        "input": "查订单 99999",
        "expected_contains": ["99999"],
    },
    {
        "id": "tc_52",
        "input": "我有什么优惠券可以用",
        "expected_contains": ["优惠券"],
    },
]
