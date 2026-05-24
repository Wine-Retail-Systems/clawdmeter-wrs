"""Clawdmeter daemon — multi-provider LLM usage monitor.

Polls one or more LLM providers (Anthropic, Langdock, OpenCode, AWS Bedrock)
and forwards normalized usage snapshots to the Clawdmeter ESP32 firmware over
BLE.
"""

__version__ = "2.0.0"
