# -*- coding: utf-8 -*-
"""
浏览器登录服务 - FastAPI 应用

在独立端口运行，提供浏览器登录相关的 API 端点。
可以配合 noVNC 等方案在服务器上实现浏览器登录。
"""

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# 尝试导入 uploader 的浏览器模块
UPLOADER_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "AgentOs-Uploader"
if str(UPLOADER_PATH) not in sys.path:
    sys.path.insert(0, str(UPLOADER_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Browser Login Service...")
    
    # 初始化浏览器管理器
    try:
        from src.browser_login.manager import BrowserLoginManager
        manager = BrowserLoginManager()
        await manager.start()
        app.state.browser_manager = manager
        logger.info("Browser manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize browser manager: {e}")
        app.state.browser_manager = None
    
    yield
    
    logger.info("Shutting down Browser Login Service...")
    # 清理浏览器会话
    if hasattr(app.state, 'browser_manager') and app.state.browser_manager:
        try:
            await app.state.browser_manager.stop()
            logger.info("Browser manager stopped")
        except Exception as e:
            logger.error(f"Error stopping browser manager: {e}")


def create_browser_login_app() -> FastAPI:
    """创建浏览器登录服务 FastAPI 应用"""
    
    app = FastAPI(
        title="Browser Login Service",
        description="提供浏览器登录功能的独立服务",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ========== 健康检查 ==========
    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": "browser-login",
            "browser_ready": app.state.browser_manager is not None
        }
    
    # ========== 交互式浏览器登录 ==========
    
    @app.post("/api/browser-login/init")
    async def init_browser_login(
        platform: str = Query(..., description="平台：douyin、tencent 或 xhs"),
    ):
        """
        启动交互式浏览器登录会话。
        
        浏览器将在服务器上启动，用户需要通过 VNC/noVNC 等方式访问。
        登录成功后 cookie 会自动保存。
        """
        if platform not in ["douyin", "tencent", "xhs"]:
            raise HTTPException(
                status_code=400, 
                detail="不支持的平台，仅支持 douyin、tencent 或 xhs"
            )
        
        if not app.state.browser_manager:
            raise HTTPException(
                status_code=503,
                detail="浏览器管理器未初始化，请检查服务器环境"
            )
        
        try:
            # 检查是否已有已登录账号
            existing_account = await app.state.browser_manager.get_account_for_platform(platform)
            
            # 创建浏览器会话
            session = await app.state.browser_manager.create_session(platform, existing_account)
            
            if session.get('status') == 'failed':
                raise HTTPException(
                    status_code=500,
                    detail=session.get('error', '浏览器启动失败')
                )
            
            return {
                "success": True,
                "sessionId": session['sessionId'],
                "platform": platform,
                "status": session['status'],
                "message": "浏览器已启动" if not existing_account else f"已打开 {existing_account.get('user_name', '账号')} 的创作者平台",
                "existingAccount": existing_account,
            }
            
        except Exception as e:
            logger.error(f"Failed to init browser login: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/browser-login/{session_id}/status")
    async def get_login_status(session_id: str):
        """获取登录会话状态"""
        if not app.state.browser_manager:
            raise HTTPException(status_code=503, detail="浏览器管理器未初始化")
        
        session = app.state.browser_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            "success": True,
            "session": session
        }
    
    @app.post("/api/browser-login/{session_id}/close")
    async def close_browser_session(session_id: str):
        """关闭浏览器会话"""
        if not app.state.browser_manager:
            raise HTTPException(status_code=503, detail="浏览器管理器未初始化")
        
        success = await app.state.browser_manager.close_session(session_id)
        return {
            "success": success,
            "message": "会话已关闭" if success else "会话不存在"
        }
    
    @app.post("/api/browser-login/close-all")
    async def close_all_sessions():
        """关闭所有浏览器会话"""
        if not app.state.browser_manager:
            raise HTTPException(status_code=503, detail="浏览器管理器未初始化")
        
        await app.state.browser_manager.stop()
        return {
            "success": True,
            "message": "所有会话已关闭"
        }
    
    # ========== 账号管理 ==========
    
    @app.get("/api/browser-login/accounts")
    async def list_accounts():
        """获取已保存的账号列表"""
        try:
            # 使用 uploader 的数据库
            sys.path.insert(0, str(UPLOADER_PATH))
            from src.db.session import AsyncSessionLocal
            from src.db.repository import AccountRepository
            
            async with AsyncSessionLocal() as db_session:
                repo = AccountRepository(db_session)
                accounts = await repo.list_all()
                return {
                    "success": True,
                    "accounts": [
                        {
                            "id": acc.id,
                            "platform": acc.platform,
                            "userName": acc.account_name,
                            "isActive": acc.is_active,
                        }
                        for acc in accounts
                    ]
                }
        except Exception as e:
            logger.error(f"Failed to list accounts: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/browser-login/accounts/{account_id}")
    async def delete_account(account_id: str):
        """删除账号"""
        try:
            sys.path.insert(0, str(UPLOADER_PATH))
            from src.db.session import AsyncSessionLocal
            from src.db.repository import AccountRepository
            
            async with AsyncSessionLocal() as db_session:
                repo = AccountRepository(db_session)
                success = await repo.delete(account_id)
                await db_session.commit()
                return {
                    "success": success,
                    "message": "账号已删除" if success else "账号不存在"
                }
        except Exception as e:
            logger.error(f"Failed to delete account: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ========== VNC/远程桌面信息 ==========
    
    @app.get("/api/browser-login/remote-desktop")
    async def get_remote_desktop_info():
        """
        获取远程桌面访问信息。
        
        返回 noVNC 等远程桌面方案的访问地址，
        用于在服务器上查看浏览器界面。
        """
        # 从环境变量读取配置
        novnc_host = os.environ.get("NOVNC_HOST", "localhost")
        novnc_port = os.environ.get("NOVNC_PORT", "6080")
        vnc_port = os.environ.get("VNC_PORT", "5900")
        
        return {
            "success": True,
            "novnc": {
                "url": f"http://{novnc_host}:{novnc_port}/vnc.html?autoconnect=true&resize=scale",
                "host": novnc_host,
                "port": int(novnc_port),
            },
            "vnc": {
                "port": int(vnc_port),
            },
            "message": "请使用 noVNC URL 在浏览器中访问远程桌面"
        }
    
    return app


async def start_browser_login_server(host: str = "0.0.0.0", port: int = 8003):
    """
    启动浏览器登录服务（异步方式）
    
    用法:
        asyncio.run(start_browser_login_server())
    """
    import uvicorn
    
    app = create_browser_login_app()
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # 直接运行测试
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    host = os.environ.get("BROWSER_LOGIN_HOST", "0.0.0.0")
    port = int(os.environ.get("BROWSER_LOGIN_PORT", "8003"))
    
    asyncio.run(start_browser_login_server(host, port))
