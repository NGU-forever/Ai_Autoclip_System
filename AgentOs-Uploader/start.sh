#!/bin/bash
#
# AgentOS Uploader - 本地独立启动脚本
# 支持一键启动服务和依赖，无需 Docker Compose YML 文件
#
# 使用方法:
#   ./start.sh                    # 启动所有服务和依赖
#   ./start.sh --stop             # 停止所有服务和依赖
#   ./start.sh --status           # 查看服务状态
#   ./start.sh --init             # 仅初始化数据库
#   ./start.sh --worker           # 同时启动 Celery Worker
#   ./start.sh --help             # 查看所有选项
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Docker 容器名称
POSTGRES_CONTAINER="uploader-postgres-local"
REDIS_CONTAINER="uploader-redis-local"

# 默认端口映射 (避免与系统已有服务冲突)
POSTGRES_PORT="5433"
REDIS_PORT="6380"
UPLOADER_PORT="8002"

# 打印横幅
print_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              AgentOS Uploader - 本地启动工具                  ║"
    echo "║                                                              ║"
    echo "║  依赖服务自动管理: PostgreSQL + Redis (Docker)                ║"
    echo "║  支持平台: 抖音 | 视频号 | 小红书                             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        echo "💡 请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! docker version &> /dev/null; then
        print_error "Docker 未运行"
        exit 1
    fi
}

# 检查容器是否正在运行
container_running() {
    local name=$1
    docker ps --filter "name=$name" --format "{{.Names}}" | grep -q "^${name}$"
}

# 检查容器是否存在
container_exists() {
    local name=$1
    docker ps -a --filter "name=$name" --format "{{.Names}}" | grep -q "^${name}$"
}

# 启动 PostgreSQL
start_postgres() {
    echo "🐘 启动 PostgreSQL..."
    
    # 创建数据目录
    local data_dir="$PROJECT_ROOT/.data/postgres"
    mkdir -p "$data_dir"
    
    if container_running "$POSTGRES_CONTAINER"; then
        echo "   ✅ PostgreSQL 已在运行"
        return 0
    fi
    
    if container_exists "$POSTGRES_CONTAINER"; then
        echo "   🔄 启动已有容器..."
        docker start "$POSTGRES_CONTAINER" > /dev/null
    else
        echo "   🆕 创建新容器..."
        docker run -d \
            --name "$POSTGRES_CONTAINER" \
            -e POSTGRES_USER=uploader \
            -e POSTGRES_PASSWORD=uploader \
            -e POSTGRES_DB=uploader \
            -p "${POSTGRES_PORT}:5432" \
            -v "$data_dir:/var/lib/postgresql/data" \
            pgvector/pgvector:pg15-trixie > /dev/null
    fi
    
    # 等待启动
    echo "   ⏳ 等待 PostgreSQL 就绪..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if docker exec "$POSTGRES_CONTAINER" pg_isready -U uploader &> /dev/null; then
            echo "   ✅ PostgreSQL 已就绪"
            return 0
        fi
        sleep 1
        ((retries--))
    done
    
    print_error "PostgreSQL 启动超时"
    return 1
}

# 启动 Redis
start_redis() {
    echo "🔴 启动 Redis..."
    
    if container_running "$REDIS_CONTAINER"; then
        echo "   ✅ Redis 已在运行"
        return 0
    fi
    
    if container_exists "$REDIS_CONTAINER"; then
        echo "   🔄 启动已有容器..."
        docker start "$REDIS_CONTAINER" > /dev/null
    else
        echo "   🆕 创建新容器..."
        docker run -d \
            --name "$REDIS_CONTAINER" \
            -p "${REDIS_PORT}:6379" \
            redis:7-alpine > /dev/null
    fi
    
    # 等待启动
    echo "   ⏳ 等待 Redis 就绪..."
    local retries=10
    while [ $retries -gt 0 ]; do
        if docker exec "$REDIS_CONTAINER" redis-cli ping &> /dev/null; then
            echo "   ✅ Redis 已就绪"
            return 0
        fi
        sleep 1
        ((retries--))
    done
    
    print_error "Redis 启动超时"
    return 1
}

# 停止依赖服务
stop_deps() {
    echo "🛑 停止依赖服务..."
    
    for container in "$POSTGRES_CONTAINER" "$REDIS_CONTAINER"; do
        if container_running "$container"; then
            echo "   🛑 停止 $container..."
            docker stop "$container" > /dev/null 2>&1 || true
        fi
    done
    
    print_success "依赖服务已停止"
}

# 删除依赖容器
remove_deps() {
    echo "🗑️  删除依赖容器..."
    
    stop_deps
    sleep 2
    
    for container in "$POSTGRES_CONTAINER" "$REDIS_CONTAINER"; do
        if container_exists "$container"; then
            echo "   🗑️  删除 $container..."
            docker rm "$container" > /dev/null 2>&1 || true
        fi
    done
    
    print_success "容器已删除"
}

# 初始化存储目录
init_storage() {
    echo "📁 初始化存储目录..."
    
    local dirs=("raw" "intermediate" "exports" "openstoryline" "uploader/cookies" "uploader/videos")
    
    for dir in "${dirs[@]}"; do
        mkdir -p "$PROJECT_ROOT/storage/$dir"
        echo "   ✅ $dir/"
    done
}

# 检查并创建 .env 文件
check_env_file() {
    local env_file="$PROJECT_ROOT/.env"
    local example_file="$PROJECT_ROOT/.env.example"
    
    if [ -f "$env_file" ]; then
        return 0
    fi
    
    if [ -f "$example_file" ]; then
        print_warning "未找到 .env 文件，正在创建..."
        
        # 修改默认端口以匹配 Docker 映射
        sed \
            -e "s/localhost:5432/localhost:${POSTGRES_PORT}/g" \
            -e "s/localhost:6379/localhost:${REDIS_PORT}/g" \
            "$example_file" > "$env_file"
        
        print_success "已创建 .env 文件"
        echo "💡 请根据需要编辑配置，特别是 SECRET_KEY"
    else
        print_error "未找到 .env.example 文件"
        exit 1
    fi
}

# 初始化数据库
init_database() {
    echo "📦 初始化数据库..."
    
    export DATABASE_URL="postgresql://uploader:uploader@localhost:${POSTGRES_PORT}/uploader"
    export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
    export STORAGE_ROOT="$PROJECT_ROOT/storage"
    export PYTHONPATH="$PROJECT_ROOT"
    
    cd "$PROJECT_ROOT"
    
    python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')

async def init():
    try:
        from src.db import init_db
        await init_db()
        print('✅ 数据库表结构初始化完成')
        return True
    except Exception as e:
        print(f'❌ 数据库初始化失败: {e}')
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(init())
sys.exit(0 if result else 1)
"
}

# 启动 Celery Worker
start_worker() {
    echo "⚙️  启动 Celery Worker..."
    
    export DATABASE_URL="postgresql://uploader:uploader@localhost:${POSTGRES_PORT}/uploader"
    export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
    export STORAGE_ROOT="$PROJECT_ROOT/storage"
    export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/uploader"
    export SECRET_KEY="${SECRET_KEY:-local-dev-secret-key}"
    
    cd "$PROJECT_ROOT"
    
    python3 -m celery \
        -A src.tasks.celery_app.celery_app \
        worker \
        --loglevel=info \
        --concurrency=1 \
        --pool=solo \
        --hostname=uploader-worker@%h &
    
    WORKER_PID=$!
    sleep 2
    
    if kill -0 $WORKER_PID 2>/dev/null; then
        print_success "Celery Worker 已启动 (PID: $WORKER_PID)"
    else
        print_error "Celery Worker 启动失败"
    fi
}

# 启动 Uploader 服务
start_uploader() {
    local host=$1
    local port=$2
    local reload=$3
    
    echo ""
    echo "🚀 启动 Uploader 服务..."
    echo "   📍 http://${host}:${port}"
    echo "   📚 API 文档: http://${host}:${port}/docs"
    echo "   🎨 前端界面: http://${host}:${port}/"
    echo ""
    echo "按 Ctrl+C 停止服务"
    echo ""
    
    export DATABASE_URL="postgresql://uploader:uploader@localhost:${POSTGRES_PORT}/uploader"
    export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
    export STORAGE_ROOT="$PROJECT_ROOT/storage"
    export PYTHONPATH="$PROJECT_ROOT"
    export SECRET_KEY="${SECRET_KEY:-local-dev-secret-key}"
    
    cd "$PROJECT_ROOT/src"
    
    local cmd="python3 -m uvicorn main:app --host $host --port $port"
    if [ "$reload" = true ]; then
        cmd="$cmd --reload"
    fi
    
    eval "$cmd"
}

# 显示服务状态
show_status() {
    echo "📊 服务状态"
    echo ""
    
    echo "依赖服务 (Docker):"
    
    # PostgreSQL 状态
    if container_running "$POSTGRES_CONTAINER"; then
        echo -e "   $POSTGRES_CONTAINER: ${GREEN}🟢 运行中${NC} (端口: $POSTGRES_PORT)"
    elif container_exists "$POSTGRES_CONTAINER"; then
        echo -e "   $POSTGRES_CONTAINER: ${YELLOW}🟡 已停止${NC}"
    else
        echo -e "   $POSTGRES_CONTAINER: ⚪ 不存在"
    fi
    
    # Redis 状态
    if container_running "$REDIS_CONTAINER"; then
        echo -e "   $REDIS_CONTAINER: ${GREEN}🟢 运行中${NC} (端口: $REDIS_PORT)"
    elif container_exists "$REDIS_CONTAINER"; then
        echo -e "   $REDIS_CONTAINER: ${YELLOW}🟡 已停止${NC}"
    else
        echo -e "   $REDIS_CONTAINER: ⚪ 不存在"
    fi
    
    echo ""
    echo "存储目录:"
    if [ -d "$PROJECT_ROOT/storage" ]; then
        echo -e "   ${GREEN}✅${NC} $PROJECT_ROOT/storage"
    else
        echo -e "   ${RED}❌${NC} $PROJECT_ROOT/storage (不存在)"
    fi
    
    echo ""
    echo "配置文件:"
    if [ -f "$PROJECT_ROOT/.env" ]; then
        echo -e "   ${GREEN}✅${NC} $PROJECT_ROOT/.env"
    else
        echo -e "   ${YELLOW}⚠️${NC}  $PROJECT_ROOT/.env (不存在，将使用默认值)"
    fi
}

# 显示帮助
show_help() {
    print_banner
    echo "使用方法: ./start.sh [选项]"
    echo ""
    echo "选项:"
    echo "  (无参数)         一键启动所有服务"
    echo "  --stop           停止所有服务和依赖"
    echo "  --status         查看服务状态"
    echo "  --restart-deps   重启依赖服务 (PostgreSQL + Redis)"
    echo "  --remove-deps    删除依赖容器 (数据会丢失)"
    echo "  --init           仅初始化数据库和存储目录"
    echo "  --worker         同时启动 Celery Worker"
    echo "  --host HOST      服务监听地址 (默认: 0.0.0.0)"
    echo "  --port PORT      服务监听端口 (默认: 8002)"
    echo "  --no-reload      禁用热重载 (生产模式)"
    echo "  --skip-deps      跳过依赖服务启动 (假设已在运行)"
    echo "  --help           显示此帮助信息"
    echo ""
    echo "使用示例:"
    echo "  ./start.sh                    # 启动所有服务"
    echo "  ./start.sh --stop             # 停止所有服务"
    echo "  ./start.sh --status           # 查看状态"
    echo "  ./start.sh --worker           # 启动服务 + Worker"
    echo ""
    echo "数据持久化:"
    echo "  - PostgreSQL 数据保存在: .data/postgres/"
    echo "  - 上传文件保存在: storage/"
}

# 主函数
main() {
    local host="0.0.0.0"
    local port="$UPLOADER_PORT"
    local reload=true
    local skip_deps=false
    local run_worker=false
    local init_only=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --stop)
                stop_deps
                exit 0
                ;;
            --status)
                show_status
                exit 0
                ;;
            --remove-deps)
                remove_deps
                exit 0
                ;;
            --restart-deps)
                stop_deps
                sleep 2
                shift
                ;;
            --init)
                init_only=true
                shift
                ;;
            --worker)
                run_worker=true
                shift
                ;;
            --host)
                host="$2"
                shift 2
                ;;
            --port)
                port="$2"
                shift 2
                ;;
            --no-reload)
                reload=false
                shift
                ;;
            --skip-deps)
                skip_deps=true
                shift
                ;;
            *)
                print_error "未知选项: $1"
                echo "使用 --help 查看帮助"
                exit 1
                ;;
        esac
    done
    
    print_banner
    
    # 检查 Docker
    check_docker
    
    # 检查 .env
    check_env_file
    
    # 初始化存储
    init_storage
    
    # 启动依赖服务
    if [ "$skip_deps" = false ]; then
        echo ""
        echo "📦 启动依赖服务..."
        echo ""
        
        if ! start_postgres; then
            exit 1
        fi
        
        if ! start_redis; then
            exit 1
        fi
        
        echo ""
        print_success "所有依赖服务已就绪"
        echo ""
    fi
    
    # 仅初始化模式
    if [ "$init_only" = true ]; then
        if init_database; then
            echo ""
            print_success "初始化完成"
        else
            echo ""
            print_error "初始化失败"
            exit 1
        fi
        exit 0
    fi
    
    # 初始化数据库
    echo ""
    if ! init_database; then
        print_warning "数据库初始化失败，继续启动服务..."
    fi
    
    # 启动 Worker (可选)
    if [ "$run_worker" = true ]; then
        start_worker
    fi
    
    # 启动服务
    start_uploader "$host" "$port" "$reload"
}

# 捕获 Ctrl+C
trap 'echo -e "\n🛑 正在关闭服务..."; exit 0' INT

# 运行主函数
main "$@"
