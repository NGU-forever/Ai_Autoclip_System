// ========================================
// AgentOS Enterprise - 用户端应用入口
// 包含：登录页、用户工作台（选择入口）、剪辑平台、分发中心
// ========================================

import { useState, type ReactNode } from 'react';
import { Routes, Route, Navigate, useNavigate, Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  Clapperboard,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  X,
  Film,
  Send,
  LogOut,
  Sparkles,
  BarChart3,
  ChevronRight,
  Video,
  Share2,
} from 'lucide-react';
import { http, setToken, setUser, clearAuth } from '../../core/api/http';
import { useToast } from '../../components/Toast';
interface LoginResponse {
  accessToken: string;
  tokenType: string;
  user: Record<string, unknown>;
}

/** 将登录接口返回的英文错误信息转为中文提示 */
function loginErrorMessage(message: string): string {
  const t = message.trim().toLowerCase();
  if (t.includes('incorrect email') || t.includes('incorrect password') || t.includes('email or password')) return '邮箱或密码错误';
  if (t.includes('could not validate credentials')) return '邮箱或密码错误';
  if (t.includes('invalid credentials')) return '邮箱或密码错误';
  if (t.includes('disabled') || t.includes('account is disabled')) return '账号已被禁用';
  if (t.includes('not enough permissions')) return '权限不足';
  return message || '登录失败，请重试';
}

// ========================================
// 登录页面
// ========================================
const UserLogin: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { showToast } = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('请填写邮箱和密码');
      return;
    }

    setLoading(true);
    try {
      const data = await http.post<LoginResponse>('/auth/login', { email, password }, { skipAuth: true });
      setToken(data.accessToken);
      setUser(data.user);
      showToast('success', '登录成功');
      const nextRaw = searchParams.get('next');
      if (nextRaw) {
        try {
          const base = nextRaw.split('#')[0];
          new URL(base);
          window.location.replace(
            `${base}#access_token=${encodeURIComponent(data.accessToken)}`,
          );
        } catch {
          navigate('/', { replace: true });
        }
      } else {
        navigate('/', { replace: true });
      }
    } catch (err) {
      const raw = err instanceof Error ? err.message : '登录失败，请重试';
      setError(loginErrorMessage(raw));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex flex-col md:flex-row overflow-hidden">
      <div className="hidden md:flex md:w-1/2 bg-text relative flex-col items-center justify-center p-12 text-bg">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(circle_at_center,var(--primary)_0,transparent_70%)]" />
        <div className="relative z-10 text-center space-y-8">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="w-24 h-24 bg-primary rounded-os-lg mx-auto flex items-center justify-center shadow-os"
          >
            <Sparkles size={46} className="text-bg" />
          </motion.div>
          <div className="space-y-4">
            <h1 className="text-5xl font-bold tracking-tight">AI <span className="text-primary">创作中心</span></h1>
            <p className="text-xl text-muted font-light max-w-md mx-auto leading-relaxed">
              智能剪辑 × 一键分发，让创作更高效
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 md:p-12">
        <motion.div
          className="w-full max-w-md"
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <div className="md:hidden text-center mb-10">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-primary rounded-os-md mb-4 shadow-os-soft">
              <Sparkles size={28} className="text-bg" />
            </div>
            <h1 className="text-2xl font-bold text-text">AI 创作中心</h1>
          </div>

          <div className="os-card p-8 md:p-10">
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-text tracking-tight">欢迎登录</h2>
              <p className="text-sm text-muted mt-2">登录后即可使用 AI 剪辑与分发服务</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs font-bold text-muted uppercase tracking-wider ml-1">邮箱地址</label>
                <div className="relative group">
                  <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@company.com"
                    className="w-full h-14 bg-surface-2 border border-border-os-weak rounded-os-sm pl-12 pr-4 text-sm text-text placeholder:text-muted focus:outline-none focus:bg-surface focus:border-primary focus:ring-4 focus:ring-primary/10 transition-all"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold text-muted uppercase tracking-wider ml-1">登录密码</label>
                <div className="relative group">
                  <Lock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="请输入密码"
                    className="w-full h-14 bg-surface-2 border border-border-os-weak rounded-os-sm pl-12 pr-12 text-sm text-text placeholder:text-muted focus:outline-none focus:bg-surface focus:border-primary focus:ring-4 focus:ring-primary/10 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-muted hover:text-text transition-colors"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="bg-red-500/10 text-red-500 text-xs font-bold px-4 py-3 rounded-os-sm flex items-center gap-2 border border-red-500/20"
                  >
                    <X size={14} />
                    {error}
                  </motion.div>
                )}
              </AnimatePresence>

              <button
                type="submit"
                disabled={loading}
                className="w-full h-14 bg-primary hover:bg-primary-dark text-bg rounded-os-sm font-bold shadow-os-soft disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3 transition-all active:scale-[0.98]"
              >
                {loading ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    正在登录...
                  </>
                ) : (
                  <>
                    <span>进入创作中心</span>
                    <ArrowRight size={18} />
                  </>
                )}
              </button>
            </form>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

// ========================================
// 用户工作台 - 选择入口页面
// ========================================
const UserDashboard: React.FC = () => {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem('current_user') || '{}');
  const userName = user?.name || '创作者';

  const handleLogout = () => {
    clearAuth();
    navigate('/login', { replace: true });
  };

  const features = [
    {
      id: 'clip',
      title: 'AI 智能剪辑',
      subtitle: '从素材到成片，全自动智能剪辑',
      description: '上传素材，AI 自动完成镜头分割、文案生成、配音、配乐、渲染成片',
      icon: Film,
      gradient: 'from-[#7467ef] to-[#9b8ff7]',
      shadow: 'shadow-[#7467ef]/30',
      link: '/clip',
      buttonText: '进入工作台',
      stats: '本月已剪辑 12 个视频',
    },
    {
      id: 'distribute',
      title: '视频分发中心',
      subtitle: '一键发布到多平台',
      description: '支持抖音、视频号、小红书等平台，浏览器自动化一键发布',
      icon: Share2,
      gradient: 'from-[#3b82f6] to-[#60a5fa]',
      shadow: 'shadow-blue-500/30',
      link: '/distribute',
      buttonText: '进入分发中心',
      stats: '已发布 8 个视频',
      external: false,
    },
  ];

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.6,
        ease: [0.215, 0.61, 0.355, 1],
      },
    },
  };

  return (
    <div className="min-h-screen bg-bg text-text overflow-hidden">
      {/* 背景装饰 */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[128px]" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[128px]" />
      </div>

      {/* Header */}
      <header className="relative z-10 h-[72px] os-glass border-b border-border-os-weak">
        <div className="max-w-7xl mx-auto px-6 h-full flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-os-sm bg-primary flex items-center justify-center shadow-os-soft">
              <Sparkles size={20} className="text-bg" />
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight">AI 创作中心</h1>
              <p className="text-[10px] text-muted uppercase tracking-wider">AgentOS Enterprise</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-2 text-sm text-muted">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              系统运行正常
            </div>
            <div className="h-6 w-px bg-border-os-weak hidden sm:block" />
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 rounded-os-sm bg-red-500/10 hover:bg-red-500/20 text-red-500 text-sm transition-all"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">退出登录</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 max-w-6xl mx-auto px-6 py-12 md:py-20">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="space-y-12"
        >
          {/* Welcome Section */}
          <motion.div variants={itemVariants} className="text-center space-y-4">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.1 }}
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-2 border border-border-os-weak text-sm text-muted"
            >
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              欢迎回来，{userName}
            </motion.div>
            <h2 className="text-3xl md:text-4xl font-bold text-text">
              选择你要进行的工作
            </h2>
            <p className="text-muted max-w-lg mx-auto">
              智能剪辑帮你自动生成视频，分发中心一键发布到各大平台
            </p>
          </motion.div>

          {/* Feature Cards */}
          <motion.div variants={itemVariants} className="grid md:grid-cols-2 gap-6">
            {features.map((feature) => {
              const card = (
                <div className="os-card h-full p-8 hover:bg-surface-2 transition-colors">
                  <div className="w-16 h-16 rounded-os-md bg-primary flex items-center justify-center mb-6 shadow-os-soft group-hover:scale-110 transition-transform duration-300">
                    <feature.icon size={32} className="text-bg" />
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-2xl font-bold text-text">{feature.title}</h3>
                    <p className="text-primary text-sm font-medium">{feature.subtitle}</p>
                    <p className="text-muted text-sm leading-relaxed">{feature.description}</p>
                  </div>
                  <div className="mt-8 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <BarChart3 size={14} />
                      {feature.stats}
                    </div>
                    <motion.div
                      className="flex items-center gap-2 px-5 py-2.5 rounded-os-sm bg-primary text-bg font-medium text-sm shadow-os-soft"
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      {feature.buttonText}
                      <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform" />
                    </motion.div>
                  </div>
                </div>
              );
              return (
                <motion.div
                  key={feature.id}
                  whileHover={{ y: -8, transition: { duration: 0.2 } }}
                  className="group relative"
                >
                  <Link to={feature.link} className="block">
                    {card}
                  </Link>
                </motion.div>
              );
            })}
          </motion.div>

          {/* Quick Tips */}
          <motion.div variants={itemVariants} className="grid sm:grid-cols-3 gap-4">
            {[
              { icon: Video, title: '视频格式', desc: '支持 MP4、MOV、MKV 等常见格式' },
              { icon: Clapperboard, title: '智能成片', desc: 'AI 自动剪辑，平均 3-5 分钟完成' },
              { icon: Send, title: '一键发布', desc: '同时发布到多个平台，省时省力' },
            ].map((tip, idx) => (
              <div
                key={idx}
                className="flex items-start gap-4 p-5 os-card border-none shadow-none bg-surface-2/50 hover:bg-surface-2 transition-colors"
              >
                <div className="w-10 h-10 rounded-os-sm bg-surface flex items-center justify-center flex-shrink-0 border border-border-os-weak">
                  <tip.icon size={20} className="text-primary" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-text mb-1">{tip.title}</h4>
                  <p className="text-xs text-muted">{tip.desc}</p>
                </div>
              </div>
            ))}
          </motion.div>
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 py-6 text-center text-xs text-muted">
        <p>© 2026 AgentOS Enterprise. All rights reserved.</p>
      </footer>
    </div>
  );
};

// ========================================
// AI 剪辑：仅 qiankun 挂载点；顶栏与剪辑 UI 在 AgentOs-OpenStoryline/web 子应用内实现
// ========================================
const OpenStorylineMicroContainer: React.FC = () => (
  <div id="openstoryline-subapp" className="h-[100dvh] w-full bg-black" />
);

// ========================================
// 认证保护组件
// ========================================
const RequireAuth: React.FC<{ children: ReactNode }> = ({ children }) => {
  const token = localStorage.getItem('access_token');
  if (!token) return <Navigate to="/login" replace />;
  return children;
};

// ========================================
// 分发中心（qiankun 子应用挂载点，须与 microFrontendsQiankun.ts 中 container 一致）
// ========================================
const UploaderMicroContainer: React.FC = () => (
  <div id="uploader-subapp" className="min-h-screen w-full bg-bg" />
);

// ========================================
// 主应用路由
// ========================================
const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/login" element={<UserLogin />} />
      <Route
        path="/distribute/*"
        element={
          <RequireAuth>
            <UploaderMicroContainer />
          </RequireAuth>
        }
      />
      <Route path="/" element={<RequireAuth><UserDashboard /></RequireAuth>} />
      <Route path="/clip/*" element={<RequireAuth><OpenStorylineMicroContainer /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default App;
