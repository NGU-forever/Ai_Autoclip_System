# -*- coding: utf-8 -*-
"""
浏览器登录服务 - 为服务器环境提供浏览器登录功能

该模块允许在 headless 服务器上通过额外端口提供浏览器登录服务，
配合 VNC/RDP 等远程桌面方案使用。
"""

from .server import create_browser_login_app, start_browser_login_server

__all__ = ["create_browser_login_app", "start_browser_login_server"]
