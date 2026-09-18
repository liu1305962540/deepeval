"""test_agent_langgraph.py —— LangGraph 智能体 + DeepEval 全链路监控与评测

运行：
    python test_agent_langgraph.py

链路：
    Golden(题目)
      → StateGraph 智能体（chatbot 节点 ↔ tools 节点循环）
      → CallbackHandler 把 graph/node/LLM/tool 每一步记成 span
      → update_current_trace 补齐评测要用的字段
      → evals_iterator 对整条 trace 跑六个指标
"""

from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

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

# ---------------------------------------------------------------------------
# 1. 搭图：chatbot 节点决定「要不要调工具」，tools 节点负责执行工具
# ---------------------------------------------------------------------------

llm_with_tools = build_chat_model().bind_tools(TOOLS)


def chatbot(state: MessagesState):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]
    return {"messages": [llm_with_tools.invoke(messages)]}


graph = (
    StateGraph(MessagesState)
    .add_node("chatbot", chatbot)
    .add_node("tools", ToolNode(TOOLS))
    .add_edge(START, "chatbot")
    # chatbot 输出里有 tool_calls 就去 tools 节点，否则结束
    .add_conditional_edges("chatbot", tools_condition)
    .add_edge("tools", "chatbot")
    .compile()
)


# ---------------------------------------------------------------------------
# 2. 批量评测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dataset = build_dataset()

    for golden in dataset.evals_iterator(
        metrics=build_metrics(),
        async_config=AsyncConfig(run_async=False),
        display_config=DisplayConfig(inspect_after_run=False),
        # 网关偶尔超时，单个指标失败不要中断整轮评测
        error_config=ErrorConfig(ignore_errors=True),
    ):
        result = graph.invoke(
            {"messages": [{"role": "user", "content": golden.input}]},
            # 这一行就是「全链路监控」的开关
            config={"callbacks": [CallbackHandler(name="差旅助手")]},
        )

        messages = result["messages"]
        # 把评测要用的字段写回当前 trace：
        # tools_called 用于工具类指标，expected_* 来自 Golden
        update_current_trace(
            input=golden.input,
            output=final_answer(messages),
            expected_output=golden.expected_output,
            tools_called=extract_tool_calls(messages),
            expected_tools=golden.expected_tools,
        )
