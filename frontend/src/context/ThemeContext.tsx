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
    '--bg': '#ffffff',
    '--text': '#0b0b0c',
    '--muted': 'rgba(11,11,12,0.62)',
    '--surface': 'rgba(255,255,255,0.92)',
    '--surface-2': 'rgba(0,0,0,0.03)',
    '--border': 'rgba(11,11,12,0.14)',
    '--border-weak': 'rgba(11,11,12,0.08)',
    '--shadow-soft': '0 12px 32px rgba(0,0,0,0.06)',
    '--shadow': '0 22px 60px rgba(0,0,0,0.10)',
    '--ring': '0 0 0 3px rgba(116, 103, 239, 0.12)',
    '--error': '#f44336',
    '--success': '#4caf50',
    '--warning': '#ff9800',
  },
  dark: {
    '--primary': '#7467ef',
    '--primary-light': '#9d94f3',
    '--primary-dark': '#5c52c0',
    '--bg': '#0b0b0c',
    '--text': '#f4f4f5',
    '--muted': 'rgba(244,244,245,0.60)',
    '--surface': 'rgba(20,20,22,0.92)',
    '--surface-2': 'rgba(255,255,255,0.07)',
    '--border': 'rgba(244,244,245,0.16)',
    '--border-weak': 'rgba(244,244,245,0.10)',
    '--shadow-soft': '0 14px 36px rgba(0,0,0,0.38)',
    '--shadow': '0 24px 70px rgba(0,0,0,0.58)',
    '--ring': '0 0 0 3px rgba(116, 103, 239, 0.20)',
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
