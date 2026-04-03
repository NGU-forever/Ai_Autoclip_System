#!/usr/bin/env python3
"""
AgentOS Uploader - 配置管理工具
用于查看和验证配置文件

使用方法:
    python config.py                   # 显示当前配置
    python config.py --validate        # 验证配置是否正确
    python config.py --generate        # 生成 .env 文件
"""

import argparse
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()


def load_env_file(env_file: Path) -> dict:
    """加载 .env 文件"""
    config = {}
    if not env_file.exists():
        return config
    
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip('"\'')
    
    return config


def show_config():
    """显示当前配置"""
    env_file = PROJECT_ROOT / ".env"
    example_file = PROJECT_ROOT / ".env.example"
    
    print("=" * 60)
    print("AgentOS Uploader - 当前配置")
    print("=" * 60)
    
    # 从 .env 加载
    if env_file.exists():
        print(f"\n📄 配置文件: {env_file}")
        config = load_env_file(env_file)
        
        groups = {
            "基础配置": ["PROJECT_NAME", "VERSION", "UPLOADER_PORT", "UPLOADER_HOST"],
            "数据库配置": ["DATABASE_URL", "DB_POOL_MIN_CONN", "DB_POOL_MAX_CONN"],
            "Redis 配置": ["REDIS_URL"],
            "安全配置": ["SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES"],
            "存储配置": ["STORAGE_ROOT", "RAW_DIR", "INTERMEDIATE_DIR", "EXPORTS_DIR"],
            "Uploader 配置": ["UPLOADER_CHROME_PATH", "UPLOADER_HEADLESS", "UPLOADER_COOKIES_DIR"],
            "浏览器配置": ["BROWSER_HEARTBEAT_TIMEOUT", "BROWSER_MAX_CONCURRENT_SESSIONS"],
        }
        
        for group_name, keys in groups.items():
            print(f"\n【{group_name}】")
            for key in keys:
                value = config.get(key, os.environ.get(key, ""))
                # 隐藏敏感信息
                if "SECRET" in key or "PASSWORD" in key:
                    display_value = "*" * min(len(value), 10) if value else "(未设置)"
                else:
                    display_value = value or "(使用默认值)"
                print(f"  {key}: {display_value}")
    else:
        print(f"\n⚠️  未找到 .env 文件")
    
    # 检查存储目录
    print("\n【存储目录状态】")
    storage_root = PROJECT_ROOT / "storage"
    if storage_root.exists():
        print(f"  ✅ 存储根目录: {storage_root}")
        for subdir in ["raw", "intermediate", "exports", "uploader/cookies"]:
            path = storage_root / subdir
            if path.exists():
                print(f"  ✅  {subdir}/")
            else:
                print(f"  ⚠️   {subdir}/ (不存在)")
    else:
        print(f"  ⚠️  存储根目录不存在: {storage_root}")
    
    print("\n" + "=" * 60)


def validate_config():
    """验证配置"""
    print("🔍 正在验证配置...")
    
    errors = []
    warnings = []
    
    # 检查 .env 文件
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        errors.append("缺少 .env 文件")
    else:
        config = load_env_file(env_file)
        
        # 检查必需配置
        required = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
        for key in required:
            if key not in config or not config[key]:
                errors.append(f"缺少必需配置: {key}")
        
        # 检查密钥强度
        secret_key = config.get("SECRET_KEY", "")
        if secret_key and len(secret_key) < 16:
            warnings.append("SECRET_KEY 长度建议至少 16 位")
        if secret_key and secret_key == "your-super-secret-key-change-this-in-production":
            warnings.append("SECRET_KEY 使用的是默认值，建议修改")
        
        # 检查数据库连接
        database_url = config.get("DATABASE_URL", "")
        if database_url and "localhost" in database_url:
            warnings.append("DATABASE_URL 使用 localhost，确保 PostgreSQL 已启动")
        
        # 检查 Redis 连接
        redis_url = config.get("REDIS_URL", "")
        if redis_url and "localhost" in redis_url:
            warnings.append("REDIS_URL 使用 localhost，确保 Redis 已启动")
    
    # 检查结果
    if errors:
        print("\n❌ 错误:")
        for e in errors:
            print(f"  - {e}")
    
    if warnings:
        print("\n⚠️  警告:")
        for w in warnings:
            print(f"  - {w}")
    
    if not errors and not warnings:
        print("\n✅ 配置验证通过")
        return True
    
    return len(errors) == 0


def generate_env():
    """生成 .env 文件"""
    env_file = PROJECT_ROOT / ".env"
    example_file = PROJECT_ROOT / ".env.example"
    
    if env_file.exists():
        response = input(f"⚠️  {env_file} 已存在，是否覆盖? [y/N]: ")
        if response.lower() != "y":
            print("已取消")
            return
    
    if example_file.exists():
        content = example_file.read_text()
        env_file.write_text(content)
        print(f"✅ 已生成 {env_file}")
        print("💡 请编辑该文件，修改必要的配置（如 SECRET_KEY）")
    else:
        print(f"❌ 未找到模板文件 {example_file}")


def main():
    parser = argparse.ArgumentParser(
        description="AgentOS Uploader 配置管理工具"
    )
    
    parser.add_argument("--validate", action="store_true",
                        help="验证配置是否正确")
    parser.add_argument("--generate", action="store_true",
                        help="生成 .env 文件")
    parser.add_argument("--init-storage", action="store_true",
                        help="初始化存储目录")
    
    args = parser.parse_args()
    
    if args.generate:
        generate_env()
    elif args.validate:
        validate_config()
    elif args.init_storage:
        storage_root = PROJECT_ROOT / "storage"
        dirs = ["raw", "intermediate", "exports", "openstoryline", 
                "uploader/cookies", "uploader/videos"]
        for d in dirs:
            path = storage_root / d
            path.mkdir(parents=True, exist_ok=True)
            print(f"✅ 创建目录: {path}")
    else:
        show_config()


if __name__ == "__main__":
    main()
