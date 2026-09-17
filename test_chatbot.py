import os

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import LocalModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

# 评测用的「裁判模型」：OpenAI 兼容网关
EVAL_MODEL = LocalModel(
    model="chengxin-basic",
    base_url="https://oneai.17usoft.com/v1",
    api_key=os.getenv("LOCAL_MODEL_API_KEY"),
    temperature=0.1,
    generation_kwargs={
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
        }
    },
)


def test_case():
    # GEval：用大模型当裁判，给 actual_output 和 expected_output 打分
    correctness_metric = GEval(
        name="正确性",
        criteria="判断「实际输出」是否与「期望输出」在语义上一致，信息是否准确、完整。",
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        threshold=0.5,
        model=EVAL_MODEL,
    )

    # 测试用例：模拟一次客服问答
    test_case = LLMTestCase(
        input="如果这双鞋不合脚怎么办？",
        # 下面是你 chatbot 实际返回的回答（这里先写死，真实场景应来自 API 调用）
        actual_output="您可以在30天内申请全额退款，不收取任何额外费用。",
        expected_output="我们提供30天无理由全额退款，不额外收费。",
        retrieval_context=[
            "所有客户均可享受30天全额退款，不收取额外费用。"
        ],
    )
    assert_test(test_case, [correctness_metric])
