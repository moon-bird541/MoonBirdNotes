"""专业 Agent 实现；每个 Agent 必须显式声明可用工具能力。"""

from .knowledge import (
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    KNOWLEDGE_AGENT_PROMPT_VERSION,
    KnowledgeAgent,
    KnowledgeAgentConfig,
    KnowledgeAgentError,
    KnowledgeAgentLlmUsage,
    KnowledgeAgentResult,
    KnowledgeSource,
    get_knowledge_agent,
    run_knowledge_agent,
)

__all__ = [
    'KNOWLEDGE_AGENT_SYSTEM_PROMPT',
    'KNOWLEDGE_AGENT_PROMPT_VERSION',
    'KnowledgeAgent',
    'KnowledgeAgentConfig',
    'KnowledgeAgentError',
    'KnowledgeAgentLlmUsage',
    'KnowledgeAgentResult',
    'KnowledgeSource',
    'get_knowledge_agent',
    'run_knowledge_agent',
]
