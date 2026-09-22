"""agent_kit.py —— 智能体评测公共件

被 test_agent_langgraph.py / test_agent_langchain.py 共用，包含：
  1. 业务模型（智能体大脑）与裁判模型（评测用）
  2. 三个业务工具：查天气 / 查航班 / 订机票
  3. 数据集（Golden 里带 expected_tools，即「这道题应该调哪些工具」）
  4. 四层指标：任务拆分 / 计划执行 / 工具调用 / 整体完成度
  5. 把 LangChain 消息里的真实工具调用提取成 deepeval 的 ToolCall
"""

import os
from typing import Any, Dict, List

from deepeval.dataset import EvaluationDataset, Golden
from deepeval.metrics import (
    ArgumentCorrectnessMetric,
    PlanAdherenceMetric,
    PlanQualityMetric,
    StepEfficiencyMetric,
    TaskCompletionMetric,
    ToolCorrectnessMetric,
)
from deepeval.models import LocalModel
from deepeval.test_case import ToolCall

GATEWAY_BASE_URL = "https://oneai.17usoft.com/v1"
GATEWAY_MODEL = "chengxin-basic"
GATEWAY_API_KEY = os.getenv("LOCAL_MODEL_API_KEY")

# ---------------------------------------------------------------------------
# 1. 两个模型：一个负责干活，一个负责打分
# ---------------------------------------------------------------------------

# 裁判模型：deepeval 的指标用它来评分
EVAL_MODEL = LocalModel(
    model=GATEWAY_MODEL,
    base_url=GATEWAY_BASE_URL,
    api_key=GATEWAY_API_KEY,
    temperature=0.0,
    generation_kwargs={
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
    },
)


def build_chat_model():
    """智能体大脑：LangChain 的 ChatOpenAI 指向同一个 OpenAI 兼容网关。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=GATEWAY_MODEL,
        base_url=GATEWAY_BASE_URL,
        api_key=GATEWAY_API_KEY,
        temperature=0.0,
    )


SYSTEM_PROMPT = (
    "你是差旅助手。收到任务后先把它拆成最少的必要步骤，再依次调用工具完成。\n"
    "规则：\n"
    "1. 订票必须先用 search_flights 查到航班号，再用 book_flight 下单，不要凭空编造航班号。\n"
    "2. 只问天气就只调 get_weather，不要顺带查航班。\n"
    "3. 工具返回结果后，用一句中文把最终结论回复用户。"
)

# ---------------------------------------------------------------------------
# 2. 业务工具（用假数据模拟，方便复现）
# ---------------------------------------------------------------------------

_WEATHER = {"苏州": "晴，26℃", "上海": "多云，28℃", "北京": "小雨，22℃"}
_FLIGHTS = {
    ("上海", "北京"): [
        {"flight_no": "MU5101", "depart": "08:00", "price": 780},
        {"flight_no": "CA1832", "depart": "13:30", "price": 620},
    ]
}


def get_weather(city: str) -> str:
    """查询某个城市当天的天气。参数 city 为中文城市名，例如「苏州」。"""
    return f"{city}今天{_WEATHER.get(city, '晴，25℃')}"


def search_flights(origin: str, destination: str, date: str) -> str:
    """查询两地之间某天的航班列表。参数为出发城市、到达城市、日期(如 2026-09-20)。"""
    flights = _FLIGHTS.get((origin, destination), [])
    if not flights:
        return f"{date} {origin}到{destination}没有查到航班"
    items = [
        f"{f['flight_no']} {f['depart']}起飞 票价{f['price']}元" for f in flights
    ]
    return f"{date} {origin}→{destination} 可选航班：" + "；".join(items)


def book_flight(flight_no: str, passenger: str) -> str:
    """按航班号为指定乘客下单出票。参数为航班号和乘客姓名。"""
    return f"已为{passenger}预订{flight_no}，订单号 ORD{abs(hash(flight_no)) % 10000:04d}"


TOOLS = [get_weather, search_flights, book_flight]

# ---------------------------------------------------------------------------
# 3. 数据集：Golden = 一道待测题，expected_tools = 这道题应该调哪些工具
# ---------------------------------------------------------------------------


def build_dataset() -> EvaluationDataset:
    return EvaluationDataset(
        goldens=[
            Golden(
                input="帮我查一下苏州今天的天气",
                expected_output="苏州今天晴，26℃",
                expected_tools=[ToolCall(name="get_weather")],
            ),
            Golden(
                input="帮我订一张2026-09-20从上海到北京最便宜的机票，乘客叫张三",
                expected_output="已为张三预订最便宜的航班 CA1832（票价620元）",
                expected_tools=[
                    ToolCall(name="search_flights"),
                    ToolCall(name="book_flight"),
                ],
            ),
        ]
    )


# ---------------------------------------------------------------------------
# 4. 指标：分层评测智能体
# ---------------------------------------------------------------------------


def build_metrics(verbose: bool = True) -> List[Any]:
    """四层指标，全部挂在 trace（整条链路）上。

    verbose=True 时，每个指标会把中间步骤打印到终端：
    抽出的任务/计划、工具比对过程、最终分数和理由。
    """
    return [
        # 1) 任务拆分质量：从 trace 抽计划 → 裁判模型按完整/逻辑/效率打分
        PlanQualityMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
        # 2) 计划执行：从 trace 抽计划 → 对照实际执行是否听话
        PlanAdherenceMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
        # 3) 工具选择：期望工具 vs 实际工具，纯代码集合比对（数学公式）
        ToolCorrectnessMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
        # 4) 工具参数：裁判模型对每次调用投 yes/no，再算正确比例
        ArgumentCorrectnessMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
        # 5) 任务完成度：从 trace 抽 task/outcome → 裁判模型给 0~1
        TaskCompletionMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
        # 6) 步骤效率：看有没有多余调用，裁判模型按五档锚点打分
        StepEfficiencyMetric(
            threshold=0.5, model=EVAL_MODEL, verbose_mode=verbose
        ),
    ]


# ---------------------------------------------------------------------------
# 5. 从 LangChain 消息里还原「实际调用了哪些工具」
# ---------------------------------------------------------------------------


def extract_tool_calls(messages: List[Any]) -> List[ToolCall]:
    """把 AIMessage.tool_calls + ToolMessage 结果合并成 deepeval 的 ToolCall。"""
    outputs: Dict[str, Any] = {}
    for msg in messages:
        if getattr(msg, "type", None) == "tool":
            outputs[getattr(msg, "tool_call_id", "")] = msg.content

    calls: List[ToolCall] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            calls.append(
                ToolCall(
                    name=call["name"],
                    input_parameters=call.get("args") or {},
                    output=outputs.get(call.get("id", "")),
                )
            )
    return calls


def final_answer(messages: List[Any]) -> str:
    """取最后一条非空的助手回复作为智能体的最终输出。"""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "ai" and (msg.content or "").strip():
            return msg.content
    return ""
