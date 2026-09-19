"""
Agent 编排服务 —— ReAct 循环：LLM 思考 → 工具调用 → 结果反馈 → 最终回答。

流程：
1. resolve_model 解析场景对应模型（绑定优先 → 默认回退）
2. 循环调用 LLM（带工具列表）：
   - LLM 输出文字 → yield SSE token 事件（前端打字机效果）
   - LLM 要求调用工具 → 执行工具 → 把结果回传 LLM → 继续循环
   - LLM 直接给出最终回答（无工具调用）→ 结束
3. 所有事件以 SSE JSON 格式 yield，由 endpoint 层包装为 text/event-stream

SSE 事件类型：
- {"type": "token", "content": "..."}              LLM 文字增量
- {"type": "tool_call", ...}                        正在调用工具
- {"type": "tool_result", ...}                      工具执行结果
- {"type": "done"}                                  本轮对话结束
- {"type": "error", "message": "..."}               错误
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from database.models.sys.ai_model import AiFunctionEnum
from modules.agent.services.llm_client import resolve_model, stream_chat
from modules.agent.services.tool_registry import get_openai_format, execute

logger = logging.getLogger(__name__)

# Agent 最大迭代轮数（防止 LLM 无限循环调用工具）
MAX_ITERATIONS = 8

# 系统提示词：告诉 LLM 它是谁、能做什么
SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的智能分析助手，专注于A股市场数据分析。

你可以调用以下工具获取系统中的真实数据：
- get_hot_stocks: 股票热榜（东财/同花顺/雪球等热度排名）
- get_market_indices: 大盘指数行情（上证、深成、创业板等）
- get_market_fund_flow: 大盘资金流向（主力/超大单/大单净流入）
- get_board_ranking: 行业/概念板块涨跌幅排行
- get_limit_up_stocks: 涨停股池（连板数、涨停原因）
- get_latest_news: 最新财经新闻

回答规范：
1. 回答用户问题前，优先调用工具获取真实数据，不要凭空编造数据
2. 数据不足时明确告知用户缺少哪些数据
3. 回答使用中文，条理清晰，重要数字可以用列表或表格呈现
4. 涉及行情分析时，注明数据日期，并提示"不构成投资建议"
"""


def _sse_event(event_type: str, **kwargs: Any) -> str:
    """构造 SSE data 行。"""
    payload = {"type": event_type, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class AgentService:
    """Agent 对话编排服务。"""

    @staticmethod
    async def run_agent_stream(
        db: AsyncSession,
        messages: list[dict],
        function_code: AiFunctionEnum = AiFunctionEnum.CHAT_QA,
    ) -> AsyncGenerator[str, None]:
        """
        执行 Agent 对话循环，yield SSE 格式的事件字符串。

        messages 为 OpenAI 格式的对话历史（含本次用户输入）。
        """
        # 触发工具模块导入，完成注册（装饰器副作用）
        from modules.agent.tools import (  # noqa: F401
            stock_tools,
            news_tools,
            research_report_tools,
            factor_tools,
        )

        try:
            resolved = await resolve_model(db, function_code)
        except CustomError as e:
            yield _sse_event("error", message=e.msg)
            return
        except Exception as e:
            logger.exception("解析模型失败")
            yield _sse_event("error", message=f"解析模型失败: {e}")
            return

        # 注入系统提示词（放在最前，用户自带 system 消息则不覆盖）
        chat_messages = list(messages)
        if not chat_messages or chat_messages[0].get("role") != "system":
            chat_messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        tools = get_openai_format()

        try:
            for iteration in range(MAX_ITERATIONS):
                # ===== 1. 流式调用 LLM =====
                collected_tool_calls: list[dict] = []
                assistant_text = ""
                finish_reason = None

                async for chunk in stream_chat(resolved, chat_messages, tools):
                    if chunk.content:
                        assistant_text += chunk.content
                        yield _sse_event("token", content=chunk.content)
                    if chunk.tool_calls:
                        collected_tool_calls = chunk.tool_calls
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason

                # ===== 2. 无工具调用 → 最终回答，结束 =====
                if not collected_tool_calls:
                    # 记录 assistant 消息（供多轮对话）
                    chat_messages.append(
                        {"role": "assistant", "content": assistant_text}
                    )
                    break

                # ===== 3. 有工具调用 → 执行并回传 =====
                # 记录 assistant 的工具调用消息（OpenAI 格式）
                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(
                                        tc.get("arguments", {}), ensure_ascii=False
                                    ),
                                },
                            }
                            for tc in collected_tool_calls
                        ],
                    }
                )

                for tc in collected_tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {}) or {}

                    # 通知前端：正在调用工具
                    yield _sse_event(
                        "tool_call",
                        id=tc["id"],
                        name=tool_name,
                        arguments=tool_args,
                    )

                    # 执行工具
                    result = await execute(tool_name, tool_args, db)

                    # 通知前端：工具结果
                    yield _sse_event(
                        "tool_result", id=tc["id"], name=tool_name, result=result
                    )

                    # 工具结果作为 tool 角色消息回传 LLM
                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tool_name,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )

                # 达到最大迭代次数仍未完成，强制收尾
                if iteration == MAX_ITERATIONS - 1:
                    yield _sse_event(
                        "token",
                        content="\n\n（已达到最大工具调用轮数，停止继续调用工具）",
                    )
                    break

            yield _sse_event("done")

        except CustomError as e:
            logger.warning("Agent 对话业务错误: %s", e.msg)
            yield _sse_event("error", message=e.msg)
        except Exception as e:
            logger.exception("Agent 对话异常")
            yield _sse_event("error", message=f"Agent 对话异常: {e}")
