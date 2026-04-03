#!/usr/bin/env python3
"""
AgentOS Uploader - 本地独立启动脚本
支持一键启动服务和依赖，无需 Docker Compose YML 文件

特点:
- 使用 Python 直接管理 Docker 容器启动
- PostgreSQL 和 Redis 自动在 Docker 中启动
- 支持一键启动、停止、状态检查

使用方法:
    python start.py                    # 启动所有服务和依赖
    python start.py --stop             # 停止所有服务和依赖
    python start.py --status           # 查看服务状态
    python start.py --init             # 仅初始化数据库
    python start.py --worker           # 同时启动 Celery Worker
    python start.py --help             # 查看所有选项
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()

# Docker 容器名称
POSTGRES_CONTAINER = "uploader-postgres-local"
REDIS_CONTAINER = "uploader-redis-local"

# 默认端口映射 (避免与系统已有服务冲突)
POSTGRES_PORT = "5433"
REDIS_PORT = "6380"
UPLOADER_PORT = "8002"


def print_banner():
    """打印启动横幅"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║              AgentOS Uploader - 本地启动工具                  ║
║                                                              ║
║  依赖服务自动管理: PostgreSQL + Redis (Docker)                ║
║  支持平台: 抖音 | 视频号 | 小红书                             ║
╚══════════════════════════════════════════════════════════════╝
""")


def run_command(cmd: List[str], capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """运行命令"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        if not capture:
            print(f"命令失败: {' '.join(cmd)}")
        raise


def check_docker() -> bool:
    """检查 Docker 是否安装并运行"""
    try:
        run_command(["docker", "version"], capture=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def container_exists(name: str) -> bool:
    """检查容器是否存在"""
    try:
        result = run_command(
            ["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}"],
            capture=True
        )
        return name in result.stdout
    except:
        return False


def container_running(name: str) -> bool:
    """检查容器是否正在运行"""
    try:
        result = run_command(
            ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"],
            capture=True
        )
        return name in result.stdout
    except:
        return False


def start_postgres():
    """启动 PostgreSQL 容器"""
    print("🐘 启动 PostgreSQL...")
    
    # 数据目录
    data_dir = PROJECT_ROOT / ".data" / "postgres"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    if container_running(POSTGRES_CONTAINER):
        print("   ✅ PostgreSQL 已在运行")
        return True
    
    if container_exists(POSTGRES_CONTAINER):
        print("   🔄 启动已有容器...")
        run_command(["docker", "start", POSTGRES_CONTAINER], capture=True)
    else:
        print("   🆕 创建新容器...")
        run_command([
            "docker", "run", "-d",
            "--name", POSTGRES_CONTAINER,
            "-e", "POSTGRES_USER=uploader",
            "-e", "POSTGRES_PASSWORD=uploader",
            "-e", "POSTGRES_DB=uploader",
            "-p", f"{POSTGRES_PORT}:5432",
            "-v", f"{data_dir}:/var/lib/postgresql/data",
            "pgvector/pgvector:pg15-trixie"
        ], capture=True)
    
    # 等待启动
    print("   ⏳ 等待 PostgreSQL 就绪...")
    for i in range(30):
        time.sleep(1)
        try:
            result = run_command(
                ["docker", "exec", POSTGRES_CONTAINER, "pg_isready", "-U", "uploader"],
                capture=True, check=False
            )
            if result.returncode == 0:
                print("   ✅ PostgreSQL 已就绪")
                return True
        except:
            pass
    
    print("   ❌ PostgreSQL 启动超时")
    return False


def start_redis():
    """启动 Redis 容器"""
    print("🔴 启动 Redis...")
    
    if container_running(REDIS_CONTAINER):
        print("   ✅ Redis 已在运行")
        return True
    
    if container_exists(REDIS_CONTAINER):
        print("   🔄 启动已有容器...")
        run_command(["docker", "start", REDIS_CONTAINER], capture=True)
    else:
        print("   🆕 创建新容器...")
        run_command([
            "docker", "run", "-d",
            "--name", REDIS_CONTAINER,
            "-p", f"{REDIS_PORT}:6379",
            "redis:7-alpine"
        ], capture=True)
    
    # 等待启动
    print("   ⏳ 等待 Redis 就绪...")
    for i in range(10):
        time.sleep(1)
        try:
            result = run_command(
                ["docker", "exec", REDIS_CONTAINER, "redis-cli", "ping"],
                capture=True, check=False
            )
            if "PONG" in result.stdout:
                print("   ✅ Redis 已就绪")
                return True
        except:
            pass
    
    print("   ❌ Redis 启动超时")
    return False


def stop_deps():
    """停止依赖服务"""
    print("🛑 停止依赖服务...")
    
    for container in [POSTGRES_CONTAINER, REDIS_CONTAINER]:
        if container_running(container):
            print(f"   🛑 停止 {container}...")
            run_command(["docker", "stop", container], capture=True, check=False)
        elif container_exists(container):
            print(f"   📦 {container} 已停止")
        else:
            print(f"   ⚪ {container} 不存在")
    
    print("✅ 依赖服务已停止")


def remove_deps():
    """删除依赖容器"""
    print("🗑️  删除依赖容器...")
    
    stop_deps()
    
    for container in [POSTGRES_CONTAINER, REDIS_CONTAINER]:
        if container_exists(container):
            print(f"   🗑️  删除 {container}...")
            run_command(["docker", "rm", container], capture=True, check=False)
    
    print("✅ 容器已删除")


def get_env_with_defaults() -> dict:
    """获取环境变量（使用默认值）"""
    env = os.environ.copy()
    
    # 设置默认连接字符串（使用 Docker 端口）
    env.setdefault(
        "DATABASE_URL",
        f"postgresql://uploader:uploader@localhost:{POSTGRES_PORT}/uploader"
    )
    env.setdefault(
        "REDIS_URL",
        f"redis://localhost:{REDIS_PORT}/0"
    )
    env.setdefault("STORAGE_ROOT", str(PROJECT_ROOT / "storage"))
    env.setdefault("UPLOADER_HEADLESS", "false")
    env.setdefault("SECRET_KEY", "local-dev-secret-key")
    
    return env


def init_storage():
    """初始化存储目录"""
    print("📁 初始化存储目录...")
    
    storage_root = PROJECT_ROOT / "storage"
    dirs = [
        "raw",
        "intermediate", 
        "exports",
        "openstoryline",
        "uploader/cookies",
        "uploader/videos"
    ]
    
    for d in dirs:
        path = storage_root / d
        path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ {d}/")


def init_database():
    """初始化数据库"""
    print("📦 初始化数据库...")
    
    env = get_env_with_defaults()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    init_script = '''
import asyncio
import sys
sys.path.insert(0, ".")

async def init():
    try:
        from src.db import init_db
        await init_db()
        print("✅ 数据库表结构初始化完成")
        return True
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(init())
sys.exit(0 if result else 1)
'''
    
    result = subprocess.run(
        [sys.executable, "-c", init_script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    return result.returncode == 0


def start_uploader_server(host: str, port: str, reload: bool = True):
    """启动 Uploader 服务"""
    print(f"\n🚀 启动 Uploader 服务...")
    print(f"   📍 http://{host}:{port}")
    print(f"   📚 API 文档: http://{host}:{port}/docs")
    print(f"   🎨 前端界面: http://{host}:{port}/")
    print("\n按 Ctrl+C 停止服务\n")
    
    env = get_env_with_defaults()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", port,
    ]
    
    if reload:
        cmd.append("--reload")
    
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT / "src", env=env)
    except KeyboardInterrupt:
        print("\n🛑 服务已停止")


def start_worker():
    """启动 Celery Worker"""
    print("⚙️  启动 Celery Worker...")
    
    env = get_env_with_defaults()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT}/uploader"
    
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.tasks.celery_app.celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency=1",
        "--pool=solo",
        "--hostname=uploader-worker@%h"
    ]
    
    return subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=env)


def show_status():
    """显示服务状态"""
    print("📊 服务状态\n")
    
    print("依赖服务 (Docker):")
    for name, port in [(POSTGRES_CONTAINER, POSTGRES_PORT), (REDIS_CONTAINER, REDIS_PORT)]:
        running = container_running(name)
        exists = container_exists(name)
        status = "🟢 运行中" if running else ("🟡 已停止" if exists else "⚪ 不存在")
        port_info = f" (端口: {port})" if running else ""
        print(f"   {name}: {status}{port_info}")
    
    print("\n存储目录:")
    storage_root = PROJECT_ROOT / "storage"
    if storage_root.exists():
        print(f"   ✅ {storage_root}")
    else:
        print(f"   ❌ {storage_root} (不存在)")
    
    print("\n配置文件:")
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        print(f"   ✅ {env_file}")
    else:
        print(f"   ⚠️  {env_file} (不存在，将使用默认值)")


def check_env_file():
    """检查并创建 .env 文件"""
    env_file = PROJECT_ROOT / ".env"
    example_file = PROJECT_ROOT / ".env.example"
    
    if env_file.exists():
        return True
    
    if example_file.exists():
        print("⚠️  未找到 .env 文件，正在创建...")
        content = example_file.read_text()
        # 修改默认端口以匹配 Docker 映射
        content = content.replace(
            "DATABASE_URL=postgresql://uploader:uploader@localhost:5432/uploader",
            f"DATABASE_URL=postgresql://uploader:uploader@localhost:{POSTGRES_PORT}/uploader"
        )
        content = content.replace(
            "REDIS_URL=redis://localhost:6379/0",
            f"REDIS_URL=redis://localhost:{REDIS_PORT}/0"
        )
        env_file.write_text(content)
        print("✅ 已创建 .env 文件")
        print("💡 请根据需要编辑配置，特别是 SECRET_KEY")
        return True
    
    return False


def main():
    parser = argparse.ArgumentParser(
        description="AgentOS Uploader 本地启动工具 - 无需 YML 配置文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python start.py                    # 一键启动所有服务
  python start.py --stop             # 停止所有服务
  python start.py --status           # 查看服务状态
  python start.py --restart-deps     # 重启依赖服务
  python start.py --init             # 仅初始化数据库
  python start.py --worker           # 同时启动 Celery Worker
  
数据持久化:
  - PostgreSQL 数据保存在: .data/postgres/
  - 上传文件保存在: storage/
        """
    )
    
    parser.add_argument("--stop", action="store_true",
                        help="停止所有服务和依赖")
    parser.add_argument("--status", action="store_true",
                        help="查看服务状态")
    parser.add_argument("--restart-deps", action="store_true",
                        help="重启依赖服务 (PostgreSQL + Redis)")
    parser.add_argument("--remove-deps", action="store_true",
                        help="删除依赖容器 (数据会丢失)")
    parser.add_argument("--init", action="store_true",
                        help="仅初始化数据库和存储目录")
    parser.add_argument("--worker", action="store_true",
                        help="同时启动 Celery Worker")
    parser.add_argument("--host", default="0.0.0.0",
                        help="服务监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", default=UPLOADER_PORT,
                        help=f"服务监听端口 (默认: {UPLOADER_PORT})")
    parser.add_argument("--no-reload", action="store_true",
                        help="禁用热重载 (生产模式)")
    parser.add_argument("--skip-deps", action="store_true",
                        help="跳过依赖服务启动 (假设已在运行)")
    
    args = parser.parse_args()
    
    print_banner()
    
    # 状态检查
    if args.status:
        show_status()
        return
    
    # 停止服务
    if args.stop:
        stop_deps()
        return
    
    # 删除容器
    if args.remove_deps:
        remove_deps()
        return
    
    # 重启依赖
    if args.restart_deps:
        stop_deps()
        time.sleep(2)
    
    # 检查 Docker
    if not check_docker():
        print("❌ Docker 未安装或未运行")
        print("💡 请先安装 Docker: https://docs.docker.com/get-docker/")
        sys.exit(1)
    
    # 检查 .env
    check_env_file()
    
    # 初始化存储
    init_storage()
    
    # 启动依赖服务
    if not args.skip_deps:
        print("\n📦 启动依赖服务...\n")
        
        if not start_postgres():
            print("❌ PostgreSQL 启动失败")
            sys.exit(1)
        
        if not start_redis():
            print("❌ Redis 启动失败")
            sys.exit(1)
        
        print("\n✅ 所有依赖服务已就绪\n")
    
    # 仅初始化模式
    if args.init:
        if init_database():
            print("\n✅ 初始化完成")
        else:
            print("\n❌ 初始化失败")
            sys.exit(1)
        return
    
    # 初始化数据库
    print("")
    if not init_database():
        print("⚠️  数据库初始化失败，继续启动服务...")
    
    # 启动 Worker (可选)
    worker_proc = None
    if args.worker:
        worker_proc = start_worker()
        time.sleep(2)
    
    # 启动服务
    try:
        start_uploader_server(
            host=args.host,
            port=args.port,
            reload=not args.no_reload
        )
    except KeyboardInterrupt:
        print("\n🛑 正在关闭服务...")
        if worker_proc:
            worker_proc.terminate()
            print("🛑 Celery Worker 已停止")
        print("✅ 服务已关闭")


if __name__ == "__main__":
    main()
