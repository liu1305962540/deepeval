"""test_agent_langchain.py —— LangChain 智能体 + DeepEval 全链路监控与评测

运行：
    python test_agent_langchain.py

本脚本会打印：
  1. 智能体实际调用了哪些工具、最终回答是什么
  2. 每个指标的中间过程（verbose_mode）——抽出的计划、比对结果、分数理由
  3. 最终汇总表
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


def _print_agent_run(golden, messages, tools_called):
    """把「智能体这一步实际干了什么」打清楚，方便对照后面的指标日志。"""
    sep = "=" * 72
    print(f"\n{sep}")
    print("【智能体执行过程】")
    print(sep)
    print(f"用户问题: {golden.input}")
    print(f"期望答案: {golden.expected_output}")
    print(
        "期望工具: "
        + ", ".join(t.name for t in (golden.expected_tools or []))
    )
    print("-" * 72)
    if not tools_called:
        print("实际工具调用: （无）")
    else:
        print("实际工具调用:")
        for i, t in enumerate(tools_called, 1):
            print(f"  {i}. {t.name}")
            print(f"     参数: {t.input_parameters}")
            print(f"     返回: {t.output}")
    print("-" * 72)
    print(f"最终回答: {final_answer(messages)}")
    print(sep)
    print(
        "【接下来开始评测】"
        "每个指标会打印 Verbose Logs："
        "中间抽出了什么 → 用什么方法判 → 分数和理由"
    )
    print(sep + "\n")


if __name__ == "__main__":
    dataset = build_dataset()

    print(
        """
评测方法速查（每个指标结束后会打详细 Verbose Logs）：
  Plan Quality        从 trace 抽任务+计划 → 裁判模型按完整/逻辑/效率五档打分
  Plan Adherence      从 trace 抽计划 → 对照执行轨迹，看有没有按计划走
  Tool Correctness    期望工具 vs 实际工具，代码集合比对（不花 token）
  Argument Correctness 裁判模型对每次工具参数投 yes/no，再算正确比例
  Task Completion     从 trace 抽 task/outcome → 裁判模型给 0~1 完成度
  Step Efficiency     从 trace 看步骤是否最少，裁判模型按五档打分
"""
    )

    for golden in dataset.evals_iterator(
        metrics=build_metrics(verbose=True),
        async_config=AsyncConfig(run_async=False),
        display_config=DisplayConfig(
            inspect_after_run=False,
            verbose_mode=True,
            truncate_passing_cases=False,
        ),
        # 网关偶尔超时，单个指标失败不要中断整轮评测
        error_config=ErrorConfig(ignore_errors=True),
    ):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": golden.input}]},
            config={"callbacks": [CallbackHandler(name="差旅助手")]},
        )

        messages = result["messages"]
        tools_called = extract_tool_calls(messages)
        _print_agent_run(golden, messages, tools_called)

        # 把评测要用的字段写回当前 trace，供六个指标使用
        update_current_trace(
            input=golden.input,
            output=final_answer(messages),
            expected_output=golden.expected_output,
            tools_called=tools_called,
            expected_tools=golden.expected_tools,
        )
