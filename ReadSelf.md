pip install -U deepeval
pip install "portalocker[win32]"
deepeval test run test_chatbot.py



GEval 源码把 criteria、evaluation_params


evaluation_params  程序上决定取 LLMTestCase 的哪些属性  ✅ 硬绑定（代码级）

criteria  	 自然语言告诉裁判怎么评  ❌ 不硬绑定，靠语义

class SingleTurnParams(Enum):
    INPUT = "input"
    ACTUAL_OUTPUT = "actual_output"
    EXPECTED_OUTPUT = "expected_output"