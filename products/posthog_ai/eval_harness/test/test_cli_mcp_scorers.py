"""Unit tests for MCP workflow scorers that consume sandboxed-agent logs."""

from __future__ import annotations

import json

from products.posthog_ai.evals.cli_mcp.scorers import LastTargetTool


def _tool_call(call_id: str, command: str) -> list[str]:
    return [
        json.dumps(
            {
                "notification": {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call",
                            "toolCallId": call_id,
                            "rawInput": {"command": command},
                            "_meta": {"claudeCode": {"toolName": "mcp__posthog__exec"}},
                        }
                    },
                }
            }
        ),
        json.dumps(
            {
                "notification": {
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": call_id,
                            "status": "completed",
                            "rawOutput": "ok",
                        }
                    },
                }
            }
        ),
    ]


def test_last_target_tool_fails_when_a_different_tool_is_called_after_the_target() -> None:
    raw_log = "\n".join(
        [
            *_tool_call("retention", "call query-retention {}"),
            *_tool_call("sql", "call execute-sql {}"),
        ]
    )

    result = LastTargetTool()._run_eval_sync(
        {"raw_log": raw_log},
        expected={"last_target_tool": {"tool": "query-retention"}},
    )

    assert result.score == 0.0
    assert result.metadata["last_tool"] == "execute-sql"


def test_last_target_tool_passes_when_the_expected_tool_is_called_last() -> None:
    raw_log = "\n".join(
        [
            *_tool_call("sql", "call execute-sql {}"),
            *_tool_call("retention", "call query-retention {}"),
        ]
    )

    result = LastTargetTool()._run_eval_sync(
        {"raw_log": raw_log},
        expected={"last_target_tool": {"tool": "query-retention"}},
    )

    assert result.score == 1.0
