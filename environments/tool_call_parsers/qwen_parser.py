"""
Qwen 2.5 tool call parser.

Uses the same <tool_call> format as IO.
Registered as a separate parser name for clarity when using --tool-parser=qwen.
"""

from environments.tool_call_parsers import register_parser
from environments.tool_call_parsers.io_parser import IOToolCallParser


@register_parser("qwen")
class QwenToolCallParser(IOToolCallParser):
    """
    Parser for Qwen 2.5 tool calls.
    Same <tool_call>{"name": ..., "arguments": ...}</tool_call> format as IO.
    """

    pass  # Identical format -- inherits everything from IO
