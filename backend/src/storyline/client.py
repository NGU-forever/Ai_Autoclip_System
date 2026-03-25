"""
OpenStoryline MCP Client

与 OpenStoryline MCP Server 通信的客户端
支持 HTTP/SSE 传输方式
"""

import json
import uuid
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)


class StorylineClientError(Exception):
    """Storyline 客户端错误"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class StorylineMCPClient:
    """
    OpenStoryline MCP HTTP 客户端
    
    通过 HTTP 与 OpenStoryline MCP Server 通信
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        api_key: Optional[str] = None
    ):
        self.base_url = base_url or getattr(
            settings, 
            'openstoryline_internal_url', 
            'http://storyline:7860'
        )
        self.timeout = timeout
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _call_mcp_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        调用 MCP Tool
        
        Args:
            session_id: 会话ID
            tool_name: MCP Tool 名称
            arguments: Tool 参数
            artifact_id: 产物ID（用于追踪）
        
        Returns:
            Tool 执行结果
        """
        client = await self._get_client()
        
        # 生成 artifact_id 如果没有提供
        if artifact_id is None:
            artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        
        # 构造 MCP JSON-RPC 请求
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {
                    **arguments,
                    "artifact_id": artifact_id,
                    "session_id": session_id,
                }
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-Storyline-Session-Id": session_id,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            logger.info(f"Calling MCP tool: {tool_name} for session {session_id}")
            
            response = await client.post(
                f"{self.base_url}/mcp",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 处理 MCP 响应
            if "error" in result:
                error = result["error"]
                raise StorylineClientError(
                    f"MCP Error: {error.get('message', 'Unknown error')}",
                    status_code=error.get('code', 500)
                )
            
            return result.get("result", {})
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling MCP tool {tool_name}: {e}")
            raise StorylineClientError(f"HTTP error: {str(e)}", status_code=getattr(e.response, 'status_code', None))
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}")
            raise StorylineClientError(f"Error: {str(e)}")
    
    # ============================================================
    # 核心节点调用方法
    # ============================================================
    
    async def load_media(
        self,
        session_id: str,
        mode: str = "auto",
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """加载素材"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="load_media",
            arguments={"mode": mode},
            artifact_id=artifact_id
        )
    
    async def split_shots(
        self,
        session_id: str,
        mode: str = "auto",
        min_shot_duration: int = 1000,
        max_shot_duration: int = 10000,
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """分镜切割"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="split_shots",
            arguments={
                "mode": mode,
                "min_shot_duration": min_shot_duration,
                "max_shot_duration": max_shot_duration
            },
            artifact_id=artifact_id
        )
    
    async def understand_clips(
        self,
        session_id: str,
        mode: str = "auto",
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """理解视频内容"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="understand_clips",
            arguments={"mode": mode},
            artifact_id=artifact_id
        )
    
    async def filter_clips(
        self,
        session_id: str,
        mode: str = "auto",
        user_request: str = "",
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """筛选素材"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="filter_clips",
            arguments={"mode": mode, "user_request": user_request},
            artifact_id=artifact_id
        )
    
    async def group_clips(
        self,
        session_id: str,
        mode: str = "auto",
        user_request: str = "",
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """素材分组"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="group_clips",
            arguments={"mode": mode, "user_request": user_request},
            artifact_id=artifact_id
        )
    
    async def generate_script(
        self,
        session_id: str,
        mode: str = "auto",
        user_request: str = "",
        custom_script: Optional[Dict] = None,
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成脚本"""
        arguments = {"mode": mode, "user_request": user_request}
        if custom_script:
            arguments["custom_script"] = custom_script
        
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="generate_script",
            arguments=arguments,
            artifact_id=artifact_id
        )
    
    async def generate_voiceover(
        self,
        session_id: str,
        mode: str = "auto",
        user_request: str = "",
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成配音"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="generate_voiceover",
            arguments={"mode": mode, "user_request": user_request},
            artifact_id=artifact_id
        )
    
    async def select_bgm(
        self,
        session_id: str,
        mode: str = "auto",
        user_request: str = "",
        filter_include: Optional[Dict] = None,
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """选择背景音乐"""
        arguments = {"mode": mode, "user_request": user_request}
        if filter_include:
            arguments["filter_include"] = filter_include
        
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="select_bgm",
            arguments=arguments,
            artifact_id=artifact_id
        )
    
    async def plan_timeline(
        self,
        session_id: str,
        use_beats: bool = True,
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """规划时间线"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="plan_timeline",
            arguments={"use_beats": use_beats},
            artifact_id=artifact_id
        )
    
    async def render_video(
        self,
        session_id: str,
        mode: str = "auto",
        aspect_ratio: Optional[str] = None,
        crf: int = 23,
        font_size: int = 40,
        bgm_volume_scale: float = 0.25,
        artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """渲染视频"""
        arguments = {
            "mode": mode,
            "crf": crf,
            "font_size": font_size,
            "bgm_volume_scale": bgm_volume_scale
        }
        if aspect_ratio:
            arguments["aspect_ratio"] = aspect_ratio
        
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="render_video",
            arguments=arguments,
            artifact_id=artifact_id
        )
    
    async def read_node_history(
        self,
        session_id: str,
        query_artifact_id: str
    ) -> Dict[str, Any]:
        """读取节点历史"""
        return await self._call_mcp_tool(
            session_id=session_id,
            tool_name="read_node_history",
            arguments={"query_artifact_id": query_artifact_id},
            artifact_id=None
        )


# ============================================================
# 同步包装（用于非 async 上下文）
# ============================================================

class StorylineSyncClient:
    """同步客户端包装"""
    
    def __init__(self, **kwargs):
        self._client = StorylineMCPClient(**kwargs)
        self._loop = asyncio.new_event_loop()
    
    def _run(self, coro):
        """运行协程"""
        return self._loop.run_until_complete(coro)
    
    def close(self):
        """关闭客户端"""
        self._run(self._client.close())
        self._loop.close()
    
    def load_media(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.load_media(**kwargs))
    
    def split_shots(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.split_shots(**kwargs))
    
    def understand_clips(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.understand_clips(**kwargs))
    
    def filter_clips(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.filter_clips(**kwargs))
    
    def group_clips(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.group_clips(**kwargs))
    
    def generate_script(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.generate_script(**kwargs))
    
    def generate_voiceover(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.generate_voiceover(**kwargs))
    
    def select_bgm(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.select_bgm(**kwargs))
    
    def plan_timeline(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.plan_timeline(**kwargs))
    
    def render_video(self, **kwargs) -> Dict[str, Any]:
        return self._run(self._client.render_video(**kwargs))


# 全局客户端实例
_storyline_client: Optional[StorylineMCPClient] = None


def get_storyline_client() -> StorylineMCPClient:
    """获取全局 Storyline 客户端"""
    global _storyline_client
    if _storyline_client is None:
        _storyline_client = StorylineMCPClient()
    return _storyline_client


def reset_storyline_client():
    """重置全局客户端（用于测试）"""
    global _storyline_client
    _storyline_client = None
