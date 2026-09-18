"""test_agent_langchain.py —— LangChain 智能体 + DeepEval 全链路监控与评测

和 test_agent_langgraph.py 评的是同一批题、同一套指标，
区别只是智能体用 LangChain 的 create_agent 而不是手写 StateGraph。
CallbackHandler 的用法完全一样（LangGraph 本身也走 LangChain 回调）。

运行：
    python test_agent_langchain.py
"""

from langchain.agents import create_agent

from deepeval.evaluate import AsyncConfig, DisplayConfig, ErrorConfig
from deepeval.integrations.langchain import CallbackHandler
from deepeval.tracing import update_current_trace

from agent_kit import (
    SYSTEM_PROMPT,
    TOOLS,
    build_chat_model,
    build_dataset,
    build_metrics,
    extract_tool_calls,
    final_answer,
)

# 一行搭出 ReAct 式智能体：自己决定调哪个工具、调几次
agent = create_agent(
    model=build_chat_model(),
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
)


if __name__ == "__main__":
    dataset = build_dataset()

    for golden in dataset.evals_iterator(
        metrics=build_metrics(),
        async_config=AsyncConfig(run_async=False),
        display_config=DisplayConfig(inspect_after_run=False),
        # 网关偶尔超时，单个指标失败不要中断整轮评测
        error_config=ErrorConfig(ignore_errors=True),
    ):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": golden.input}]},
            config={"callbacks": [CallbackHandler(name="差旅助手")]},
        )

        messages = result["messages"]
        update_current_trace(
            input=golden.input,
            output=final_answer(messages),
            expected_output=golden.expected_output,
            tools_called=extract_tool_calls(messages),
            expected_tools=golden.expected_tools,
        )
