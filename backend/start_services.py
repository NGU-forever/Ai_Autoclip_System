#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend 多服务启动脚本

同时启动：
1. 主 API 服务 (端口 8000)
2. 浏览器登录服务 (端口 8003)
3. VNC/虚拟显示器服务 (用于服务器远程浏览器)

用法:
    python start_services.py

环境变量:
    BROWSER_LOGIN_ENABLED: 是否启用浏览器登录服务 (默认: true)
    BROWSER_LOGIN_PORT: 浏览器登录服务端口 (默认: 8003)
    NOVNC_ENABLED: 是否启用 noVNC (默认: true)
    DISPLAY: X11 显示端口 (默认: :99)
"""

import multiprocessing
import os
import subprocess
import sys
import time
import signal
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 全局进程列表
processes = []


def start_xvfb():
    """启动虚拟 X 服务器"""
    display = os.environ.get("DISPLAY", ":99")
    logger.info(f"Starting Xvfb on display {display}...")
    
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1920x1080x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # 等待 Xvfb 启动
    
    if proc.poll() is None:
        logger.info(f"Xvfb started on display {display}")
        return proc
    else:
        logger.warning("Xvfb failed to start, browser may not display")
        return None


def start_x11vnc():
    """启动 VNC 服务器"""
    display = os.environ.get("DISPLAY", ":99")
    vnc_port = os.environ.get("VNC_PORT", "5900")
    
    logger.info(f"Starting x11vnc on port {vnc_port}...")
    
    proc = subprocess.Popen(
        ["x11vnc", "-display", display, "-nopw", "-forever", 
         "-rfbport", vnc_port, "-shared"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    
    if proc.poll() is None:
        logger.info(f"x11vnc started on port {vnc_port}")
        return proc
    else:
        logger.warning("x11vnc failed to start")
        return None


def start_novnc():
    """启动 noVNC (Web 版 VNC 客户端)"""
    vnc_port = os.environ.get("VNC_PORT", "5900")
    novnc_port = os.environ.get("NOVNC_PORT", "6080")
    
    logger.info(f"Starting noVNC on port {novnc_port}...")
    
    # websockify 将 WebSocket 连接到 VNC
    proc = subprocess.Popen(
        ["websockify", "--web=/usr/share/novnc", 
         f"0.0.0.0:{novnc_port}", f"localhost:{vnc_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    
    if proc.poll() is None:
        logger.info(f"noVNC started on port {novnc_port}")
        logger.info(f"Access noVNC at: http://localhost:{novnc_port}/vnc.html?autoconnect=true&resize=scale")
        return proc
    else:
        logger.warning("noVNC failed to start")
        return None


def run_main_app():
    """运行主 API 服务"""
    import uvicorn
    logger.info("Starting main API service on port 8000...")
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, log_level="info")


def run_browser_login():
    """运行浏览器登录服务"""
    import uvicorn
    port = int(os.environ.get("BROWSER_LOGIN_PORT", "8003"))
    logger.info(f"Starting browser login service on port {port}...")
    uvicorn.run("src.browser_login.server:app", host="0.0.0.0", port=port, log_level="info")


def signal_handler(signum, frame):
    """处理终止信号"""
    logger.info(f"Received signal {signum}, shutting down...")
    
    # 终止所有子进程
    for proc in processes:
        if proc and proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
    
    sys.exit(0)


def main():
    """主入口"""
    # 注册信号处理
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # 检查是否启用浏览器登录服务
    browser_login_enabled = os.environ.get("BROWSER_LOGIN_ENABLED", "true").lower() == "true"
    novnc_enabled = os.environ.get("NOVNC_ENABLED", "true").lower() == "true"
    
    if browser_login_enabled and novnc_enabled:
        logger.info("=" * 60)
        logger.info("Starting with Browser Login & Remote Desktop support")
        logger.info("=" * 60)
        
        # 启动虚拟显示器
        xvfb_proc = start_xvfb()
        if xvfb_proc:
            processes.append(xvfb_proc)
        
        # 启动 VNC
        vnc_proc = start_x11vnc()
        if vnc_proc:
            processes.append(vnc_proc)
        
        # 启动 noVNC
        novnc_proc = start_novnc()
        if novnc_proc:
            processes.append(novnc_proc)
        
        logger.info("=" * 60)
    else:
        logger.info("Starting in simple mode (no browser login)")
    
    # 使用多进程启动两个服务
    logger.info("Starting FastAPI services...")
    
    main_proc = multiprocessing.Process(target=run_main_app, name="main-api")
    processes.append(main_proc)
    main_proc.start()
    
    if browser_login_enabled:
        browser_proc = multiprocessing.Process(target=run_browser_login, name="browser-login")
        processes.append(browser_proc)
        browser_proc.start()
    
    # 等待子进程
    try:
        for proc in processes:
            if isinstance(proc, multiprocessing.Process):
                proc.join()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
