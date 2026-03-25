"""
OpenStoryline Bridge Service

提供业务逻辑层，管理会话、节点执行和产物存储
"""

import os
import uuid
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool

from src.storyline.client import StorylineMCPClient, get_storyline_client
from src.storyline.schemas import (
    StorylineSessionCreate,
    StorylineSessionResponse,
    StorylineSessionDetail,
    NodeExecutionRequest,
    NodeExecutionResponse,
    NodeExecutionResult,
    ArtifactInfo,
    RenderVideoRequest,
    RenderVideoResponse,
    QuickWorkflowRequest,
    QuickWorkflowResponse,
    StorylineCallbackRequest,
    NODE_PRESETS,
)
from src.config import settings
from src.database import get_redis_client
from src.exceptions import NotFoundException, AppException

logger = logging.getLogger(__name__)


class StorylineService:
    """Storyline 桥接服务"""

    def __init__(self, client: StorylineMCPClient = Depends(get_storyline_client)):
        self.client = client
        self.storage_root = Path(settings.storage_root) / "storyline"
        self.storage_root.mkdir(parents=True, exist_ok=True)
    
    # ============================================================
    # 会话管理
    # ============================================================
    
    async def create_session(
        self,
        request: StorylineSessionCreate
    ) -> StorylineSessionResponse:
        """创建新的剪辑会话"""
        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        artifacts_dir = self.storage_root / session_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存源素材
        if request.source_media:
            media_file = artifacts_dir / "source_media.json"
            with open(media_file, 'w') as f:
                json.dump(request.source_media, f)
        
        # 保存配置
        config = {
            **(request.config or {}),
            "output_resolution": request.output_resolution,
            "aspect_ratio": request.aspect_ratio,
            "output_format": request.output_format,
        }
        config_file = artifacts_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)
        
        # 创建会话元数据
        session_data = {
            "session_id": session_id,
            "name": request.name,
            "description": request.description,
            "status": "created",
            "source_media": request.source_media,
            "artifacts_dir": str(artifacts_dir),
            "config": config,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        # 保存会话信息
        meta_file = artifacts_dir / "session.json"
        with open(meta_file, 'w') as f:
            json.dump(session_data, f, default=str)
        
        logger.info(f"Created storyline session: {session_id}")
        return StorylineSessionResponse(**session_data)
    
    async def get_session(self, session_id: str) -> StorylineSessionDetail:
        """获取会话详情"""
        session_dir = self.storage_root / session_id
        if not session_dir.exists():
            raise NotFoundException(f"Session {session_id} not found")
        
        # 读取会话元数据
        meta_file = session_dir / "session.json"
        with open(meta_file, 'r') as f:
            session_data = json.load(f)
        
        # 读取产物列表
        artifacts = await self._list_artifacts(session_id)
        
        # 读取执行历史
        history = await self._list_executions(session_id)
        
        # 读取当前时间线
        timeline = await self._get_current_timeline(session_id)
        
        return StorylineSessionDetail(
            **session_data,
            artifacts=artifacts,
            current_timeline=timeline,
            node_execution_history=history
        )
    
    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[StorylineSessionResponse]:
        """列出会话"""
        sessions = []
        
        for session_dir in sorted(self.storage_root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not session_dir.is_dir():
                continue
            
            meta_file = session_dir / "session.json"
            if meta_file.exists():
                with open(meta_file, 'r') as f:
                    session_data = json.load(f)
                
                # 过滤用户ID
                if user_id and session_data.get("user_id") != user_id:
                    continue
                
                sessions.append(StorylineSessionResponse(**session_data))
        
        return sessions[offset:offset + limit]
    
    async def delete_session(self, session_id: str) -> Dict[str, str]:
        """删除会话"""
        import shutil
        
        session_dir = self.storage_root / session_id
        if not session_dir.exists():
            raise NotFoundException(f"Session {session_id} not found")
        
        shutil.rmtree(session_dir)
        logger.info(f"Deleted storyline session: {session_id}")
        
        return {"message": f"Session {session_id} deleted"}
    
    # ============================================================
    # 节点执行
    # ============================================================
    
    async def execute_node(
        self,
        session_id: str,
        request: NodeExecutionRequest,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> NodeExecutionResponse:
        """执行节点"""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        
        # 验证会话存在
        session_dir = self.storage_root / session_id
        if not session_dir.exists():
            raise NotFoundException(f"Session {session_id} not found")
        
        # 创建执行记录
        execution_data = {
            "execution_id": execution_id,
            "session_id": session_id,
            "node_name": request.node_name,
            "status": "running",
            "input_artifact_id": request.artifact_id,
            "output_artifact_id": None,
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "error_message": None,
        }
        
        # 保存执行记录
        await self._save_execution(session_id, execution_data)
        
        # 更新会话状态
        await self._update_session_status(session_id, "running")
        
        # 异步执行节点
        if background_tasks:
            background_tasks.add_task(
                self._run_node_async,
                session_id,
                execution_id,
                request
            )
        else:
            # 同步执行
            await self._run_node_async(session_id, execution_id, request)
        
        return NodeExecutionResponse(**execution_data)
    
    async def _run_node_async(
        self,
        session_id: str,
        execution_id: str,
        request: NodeExecutionRequest
    ):
        """异步运行节点"""
        try:
            logger.info(f"Running node {request.node_name} for session {session_id}")
            
            # 调用 MCP 客户端
            client_method = getattr(self.client, request.node_name, None)
            if client_method is None:
                raise AppException(f"Unknown node: {request.node_name}", status_code=400)
            
            result = await client_method(
                session_id=session_id,
                artifact_id=request.artifact_id,
                **request.input
            )
            
            # 处理结果
            output_artifact_id = result.get("artifact_id")
            
            # 更新执行记录
            execution_data = {
                "execution_id": execution_id,
                "status": "completed",
                "output_artifact_id": output_artifact_id,
                "completed_at": datetime.utcnow(),
            }
            await self._save_execution(session_id, execution_data)
            
            # 发布 SSE 事件
            await self._publish_event(session_id, {
                "type": "node_completed",
                "execution_id": execution_id,
                "node_name": request.node_name,
                "artifact_id": output_artifact_id,
                "output": result
            })
            
            # 发送回调
            if request.callback_url:
                await self._send_callback(request.callback_url, {
                    "execution_id": execution_id,
                    "session_id": session_id,
                    "node_name": request.node_name,
                    "status": "completed",
                    "artifact_id": output_artifact_id,
                    "output": result
                })
            
        except Exception as e:
            logger.error(f"Node execution failed: {e}")
            
            # 更新执行记录为失败
            execution_data = {
                "execution_id": execution_id,
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.utcnow(),
            }
            await self._save_execution(session_id, execution_data)
            
            # 发布失败事件
            await self._publish_event(session_id, {
                "type": "node_failed",
                "execution_id": execution_id,
                "node_name": request.node_name,
                "error": str(e)
            })
    
    async def get_execution(
        self,
        session_id: str,
        execution_id: str
    ) -> NodeExecutionResult:
        """获取执行结果"""
        execution = await self._load_execution(session_id, execution_id)
        if not execution:
            raise NotFoundException(f"Execution {execution_id} not found")
        
        # 读取输入输出数据
        input_data = {}
        output_data = {}
        
        if execution.get("input_artifact_id"):
            input_data = await self._load_artifact(session_id, execution["input_artifact_id"])
        
        if execution.get("output_artifact_id"):
            output_data = await self._load_artifact(session_id, execution["output_artifact_id"])
        
        return NodeExecutionResult(
            **execution,
            input=input_data,
            output=output_data
        )
    
    # ============================================================
    # 渲染视频
    # ============================================================
    
    async def render_video(
        self,
        session_id: str,
        request: RenderVideoRequest,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> RenderVideoResponse:
        """渲染视频"""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        
        # 构造渲染参数
        render_config = {
            "mode": "auto",
            "crf": request.crf,
            "font_size": request.font_size,
            "bgm_volume_scale": request.bgm_volume_scale,
            "tts_volume_scale": request.tts_volume_scale,
            "include_video_audio": request.include_video_audio,
            "video_volume_scale": request.video_volume_scale,
        }
        
        if request.aspect_ratio:
            render_config["aspect_ratio"] = request.aspect_ratio
        if request.output_max_dimension_px:
            render_config["output_max_dimension_px"] = request.output_max_dimension_px
        if request.clip_compose_mode:
            render_config["clip_compose_mode"] = request.clip_compose_mode
        if request.bg_color:
            render_config["bg_color"] = request.bg_color
        
        # 异步渲染
        if background_tasks and not request.wait_for_completion:
            background_tasks.add_task(
                self._render_video_async,
                session_id,
                execution_id,
                request.timeline_artifact_id,
                render_config
            )
            
            return RenderVideoResponse(
                execution_id=execution_id,
                status="running",
                started_at=datetime.utcnow()
            )
        else:
            # 同步等待渲染完成
            result = await self._render_video_async(
                session_id,
                execution_id,
                request.timeline_artifact_id,
                render_config
            )
            return result
    
    async def _render_video_async(
        self,
        session_id: str,
        execution_id: str,
        timeline_artifact_id: Optional[str],
        render_config: Dict[str, Any]
    ) -> RenderVideoResponse:
        """异步渲染视频"""
        try:
            result = await self.client.render_video(
                session_id=session_id,
                artifact_id=timeline_artifact_id,
                **render_config
            )
            
            # 提取输出信息
            output = result.get("tool_excute_result", {})
            video_path = output.get("video_path")
            video_url = output.get("video_url")
            
            return RenderVideoResponse(
                execution_id=execution_id,
                status="completed",
                output_video_url=video_url,
                output_video_path=video_path,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Video render failed: {e}")
            return RenderVideoResponse(
                execution_id=execution_id,
                status="failed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
    
    # ============================================================
    # 快捷工作流
    # ============================================================
    
    async def quick_workflow(
        self,
        request: QuickWorkflowRequest,
        background_tasks: BackgroundTasks
    ) -> QuickWorkflowResponse:
        """一键工作流"""
        # 创建会话
        session = await self.create_session(StorylineSessionCreate(
            name=request.name,
            source_media=request.source_media,
            output_config=request.output_config
        ))
        
        # 定义执行步骤
        steps = [
            {"node": "load_media", "name": "加载素材"},
            {"node": "split_shots", "name": "分镜切割"},
            {"node": "understand_clips", "name": "内容理解"},
            {"node": "generate_script", "name": "生成脚本"},
            {"node": "generate_voiceover", "name": "AI配音"},
            {"node": "select_bgm", "name": "选择配乐"},
            {"node": "plan_timeline", "name": "规划时间线"},
            {"node": "render_video", "name": "渲染视频"},
        ]
        
        # 异步执行完整流程
        background_tasks.add_task(
            self._run_full_workflow,
            session.session_id,
            request,
            steps
        )
        
        return QuickWorkflowResponse(
            workflow_execution_id=f"wf_{uuid.uuid4().hex[:12]}",
            session_id=session.session_id,
            status="running",
            message="工作流已启动",
            estimated_duration_seconds=600,
            steps=steps
        )
    
    async def _run_full_workflow(
        self,
        session_id: str,
        request: QuickWorkflowRequest,
        steps: List[Dict[str, str]]
    ):
        """运行完整工作流"""
        last_artifact_id = None
        
        for step in steps:
            node_name = step["node"]
            
            try:
                # 构造节点输入
                node_input = {"mode": "auto"}
                
                if node_name == "generate_script":
                    node_input["user_request"] = request.user_requirements or ""
                elif node_name == "select_bgm":
                    node_input["user_request"] = request.user_requirements or ""
                
                # 执行节点
                result = await getattr(self.client, node_name)(
                    session_id=session_id,
                    artifact_id=last_artifact_id,
                    **node_input
                )
                
                last_artifact_id = result.get("artifact_id")
                
                # 发布进度
                await self._publish_event(session_id, {
                    "type": "workflow_progress",
                    "step": step["name"],
                    "status": "completed"
                })
                
            except Exception as e:
                logger.error(f"Workflow step failed: {step['name']}, error: {e}")
                await self._publish_event(session_id, {
                    "type": "workflow_failed",
                    "step": step["name"],
                    "error": str(e)
                })
                break
    
    # ============================================================
    # 回调处理
    # ============================================================
    
    async def handle_callback(self, request: StorylineCallbackRequest) -> Dict[str, str]:
        """处理 Storyline 回调"""
        logger.info(f"Received callback for execution {request.execution_id}")
        
        # 更新执行记录
        execution_data = {
            "execution_id": request.execution_id,
            "status": request.status,
            "output_artifact_id": request.artifact_id,
            "completed_at": request.timestamp if request.status == "completed" else None,
        }
        await self._save_execution(request.session_id, execution_data)
        
        # 发布 SSE 事件
        await self._publish_event(request.session_id, {
            "type": f"node_{request.status}",
            "execution_id": request.execution_id,
            "node_name": request.node_name,
            "progress": request.progress_percent,
            "output": request.output
        })
        
        return {"status": "received"}
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    async def _save_execution(self, session_id: str, execution_data: Dict[str, Any]):
        """保存执行记录"""
        session_dir = self.storage_root / session_id
        executions_dir = session_dir / "executions"
        executions_dir.mkdir(exist_ok=True)
        
        execution_id = execution_data["execution_id"]
        execution_file = executions_dir / f"{execution_id}.json"
        
        # 如果存在则合并
        if execution_file.exists():
            with open(execution_file, 'r') as f:
                existing = json.load(f)
            existing.update(execution_data)
            execution_data = existing
        
        with open(execution_file, 'w') as f:
            json.dump(execution_data, f, default=str)
    
    async def _load_execution(self, session_id: str, execution_id: str) -> Optional[Dict[str, Any]]:
        """加载执行记录"""
        execution_file = self.storage_root / session_id / "executions" / f"{execution_id}.json"
        if execution_file.exists():
            with open(execution_file, 'r') as f:
                return json.load(f)
        return None
    
    async def _list_executions(self, session_id: str) -> List[Dict[str, Any]]:
        """列出执行记录"""
        executions_dir = self.storage_root / session_id / "executions"
        if not executions_dir.exists():
            return []
        
        executions = []
        for exec_file in executions_dir.glob("*.json"):
            with open(exec_file, 'r') as f:
                executions.append(json.load(f))
        
        return sorted(executions, key=lambda x: x.get("started_at", ""), reverse=True)
    
    async def _list_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        """列出产物"""
        artifacts_dir = self.storage_root / session_id / "artifacts"
        if not artifacts_dir.exists():
            return []
        
        artifacts = []
        for art_file in artifacts_dir.glob("*.json"):
            with open(art_file, 'r') as f:
                artifacts.append(json.load(f))
        
        return sorted(artifacts, key=lambda x: x.get("created_at", ""), reverse=True)
    
    async def _load_artifact(self, session_id: str, artifact_id: str) -> Dict[str, Any]:
        """加载产物"""
        art_file = self.storage_root / session_id / "artifacts" / f"{artifact_id}.json"
        if art_file.exists():
            with open(art_file, 'r') as f:
                return json.load(f)
        return {}
    
    async def _update_session_status(self, session_id: str, status: str):
        """更新会话状态"""
        session_file = self.storage_root / session_id / "session.json"
        if session_file.exists():
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session_data["status"] = status
            session_data["updated_at"] = datetime.utcnow().isoformat()
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, default=str)
    
    async def _get_current_timeline(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取当前时间线"""
        # 查找最新的 plan_timeline 产物
        executions = await self._list_executions(session_id)
        for exec in executions:
            if exec.get("node_name") == "plan_timeline" and exec.get("status") == "completed":
                if exec.get("output_artifact_id"):
                    return await self._load_artifact(session_id, exec["output_artifact_id"])
        return None
    
    async def _publish_event(self, session_id: str, event: Dict[str, Any]):
        """发布 SSE 事件"""
        redis = get_redis_client()
        if redis:
            channel = f"storyline_stream:{session_id}"
            await redis.publish(channel, json.dumps(event, default=str))
    
    async def _send_callback(self, callback_url: str, data: Dict[str, Any]):
        """发送回调"""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                await client.post(callback_url, json=data, timeout=10.0)
        except Exception as e:
            logger.warning(f"Callback failed: {e}")
