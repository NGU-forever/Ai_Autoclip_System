// ========================================
// AgentOS Enterprise - 主题上下文（本地持久化）
// ========================================

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const themeConfigs = {
  light: {
    '--primary': '#7467ef',
    '--primary-light': '#9d94f3',
    '--primary-dark': '#5c52c0',
    '--secondary': '#ff9e43',
    '--background': '#f4f7f9',
    '--surface': '#ffffff',
    '--on-surface': '#333333',
    '--text-primary': '#333333',
    '--text-secondary': '#666666',
    '--text-muted': '#999999',
    '--border-default': '#e0e0e0',
    '--error': '#f44336',
    '--success': '#4caf50',
    '--warning': '#ff9800',
  },
  dark: {
    '--primary': '#7467ef',
    '--primary-light': '#9d94f3',
    '--primary-dark': '#5c52c0',
    '--secondary': '#ff9e43',
    '--background': '#1a2038',
    '--surface': '#222b45',
    '--on-surface': '#ffffff',
    '--text-primary': '#ffffff',
    '--text-secondary': '#b0b3b8',
    '--text-muted': '#65676b',
    '--border-default': '#30363d',
    '--error': '#f44336',
    '--success': '#4caf50',
    '--warning': '#ff9800',
  },
};

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem('agentos-theme');
    return (saved as Theme) || 'light';
  });

  useEffect(() => {
    localStorage.setItem('agentos-theme', theme);
    const config = themeConfigs[theme];
    if (!config) {
      console.warn(`检测到无效主题: ${theme}, 正在回退到亮色模式`);
      setThemeState('light');
      return;
    }
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    Object.entries(config).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
  }, [theme]);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme 必须在 ThemeProvider 内部使用');
  }
  return context;
};
