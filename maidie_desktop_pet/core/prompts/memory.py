"""集中构造长期 Memory 信息抽取提示词。

持久化 Memory 流程调用本模块生成 prompt，使抽取规则不散落到存储或 Session 代码；
这里不执行 LLM 请求，也不写入数据库。
"""

MEMORY_EXTRACTION_SYSTEM_PROMPT = "你是严格的非敏感记忆提取器。"


def build_memory_extraction_prompt(message: str, response: str) -> str:
    """把一轮对话包装为要求结构化、最小化记忆的抽取 prompt。"""
    return (
        "从下面这一轮对话中提取值得长期记住的用户事实和偏好。"
        "不要提取密码、API Key、令牌、身份证件、银行卡、联系方式、地址、"
        "健康隐私或其他敏感信息。临时问题和助手自己的内容不要记忆。"
        "只返回 JSON：{\"facts\":[{\"key\":\"\",\"value\":\"\","
        "\"importance\":0.7}],\"preferences\":[{\"key\":\"\","
        "\"value\":\"\",\"importance\":0.9}]}。没有内容时数组为空。\n"
        f"用户：{message}\n助手：{response}"
    )
