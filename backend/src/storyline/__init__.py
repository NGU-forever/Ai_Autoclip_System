# OpenStoryline Bridge Module
# 提供与 AgentOs-OpenStoryline（OpenStoryline）MCP Server 的 HTTP Bridge API

from src.storyline.client import (
    StorylineMCPClient,
    StorylineSyncClient,
    get_storyline_client,
)
from src.storyline.service import StorylineService
from src.storyline.schemas import (
    StorylineSessionCreate,
    StorylineSessionResponse,
    NodeExecutionRequest,
    RenderVideoRequest,
    QuickWorkflowRequest,
    NODE_PRESETS,
)

__all__ = [
    "StorylineMCPClient",
    "StorylineSyncClient",
    "get_storyline_client",
    "StorylineService",
    "StorylineSessionCreate",
    "StorylineSessionResponse",
    "NodeExecutionRequest",
    "RenderVideoRequest",
    "QuickWorkflowRequest",
    "NODE_PRESETS",
]
