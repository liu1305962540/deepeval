"""test_evals_iterator.py

演示：用本地 dataset（一组 Golden）+ @observe 追踪应用
+ evals_iterator 批量端到端评测。

和 test_chatbot.py 的区别：
- chatbot：手动构造 1 条 LLMTestCase，直接 assert_test
- 本文件：准备多条 Golden（标准题库），循环跑你的 app，
  DeepEval 从 trace 自动拼出 test case 再打分
"""

import os

from deepeval.dataset import EvaluationDataset, Golden
from deepeval.evaluate import AsyncConfig, DisplayConfig
from deepeval.metrics import GEval
from deepeval.models import LocalModel
from deepeval.test_case import SingleTurnParams
from deepeval.tracing import observe, update_current_trace

# ---------- 裁判模型（和 test_chatbot 一样用你的网关）----------
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

# ---------- 模拟你的 chatbot（真实场景换成 API 调用）----------
FAQ = {
    "如果这双鞋不合脚怎么办？": "您可以在30天内申请全额退款，不收取任何额外费用。",
    "运费谁出？": "全国包邮，运费由我们承担。",
}


@observe()
def app(user_input: str, expected_output: str | None = None) -> str:
    """被测应用：根据用户问题返回答案，并用 update_current_trace 写进追踪。"""
    answer = FAQ.get(user_input, "抱歉，我暂时无法回答这个问题。")
    # 把 input / output / expected_output 挂到当前 trace，供评测指标使用
    update_current_trace(
        input=user_input,
        output=answer,
        expected_output=expected_output,
    )
    return answer


# ---------- Dataset：一组 Golden（标准题库）----------
# Golden ≈「还没跑出 actual_output 的测试题」
# 跑完 app 后，DeepEval 会把它变成完整的 LLMTestCase
dataset = EvaluationDataset(
    goldens=[
        Golden(
            input="如果这双鞋不合脚怎么办？",
            expected_output="我们提供30天无理由全额退款，不额外收费。",
        ),
        Golden(
            input="运费谁出？",
            expected_output="我们承担运费，全国包邮。",
        ),
    ]
)

# ---------- 评测指标 ----------
correctness = GEval(
    name="正确性",
    criteria="判断「实际输出」是否与「期望输出」在语义上一致，信息是否准确、完整。",
    evaluation_params=[
        SingleTurnParams.ACTUAL_OUTPUT,
        SingleTurnParams.EXPECTED_OUTPUT,
    ],
    threshold=0.5,
    model=EVAL_MODEL,
)

# ---------- 批量评测：对 dataset 里每一道题跑一次 app ----------
if __name__ == "__main__":
    for golden in dataset.evals_iterator(
        metrics=[correctness],
        async_config=AsyncConfig(run_async=False),  # 同步，方便理解
        display_config=DisplayConfig(inspect_after_run=False),  # 跑完不弹交互
    ):
        # golden.input → 喂给你的 app；评测在循环结束后自动发生
        app(golden.input, expected_output=golden.expected_output)
