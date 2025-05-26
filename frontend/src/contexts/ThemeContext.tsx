import React, { createContext, useContext, useEffect, useState } from 'react';
import { initializeTheme, toggleTheme as toggleThemeUtil } from '../styles/themeConfig';

// 主題類型定義
export type Theme = 'light' | 'dark' | 'system';

// 主題上下文接口
interface ThemeContextType {
  theme: Theme;
  actualTheme: 'light' | 'dark'; // 實際應用的主題（解析 system 後）
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

// 創建主題上下文
const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// 主題提供者組件
export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    // 初始化時立即讀取保存的主題
    const savedTheme = localStorage.getItem('theme') as Theme;
    return (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) ? savedTheme : 'system';
  });
  
  const [actualTheme, setActualTheme] = useState<'light' | 'dark'>(() => {
    // 初始化時立即確定實際主題
    const savedTheme = localStorage.getItem('theme') as Theme;
    if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
      return savedTheme;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  // 更新實際主題
  const updateActualTheme = (newTheme: Theme) => {
    if (newTheme === 'system') {
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setActualTheme(systemPrefersDark ? 'dark' : 'light');
    } else {
      setActualTheme(newTheme);
    }
  };

  // 設置主題
  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    updateActualTheme(newTheme);
    
    // 更新 DOM 和 localStorage
    const html = document.documentElement;
    if (newTheme === 'system') {
      localStorage.removeItem('theme');
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      html.setAttribute('data-theme', systemPrefersDark ? 'dark' : 'light');
    } else {
      localStorage.setItem('theme', newTheme);
      html.setAttribute('data-theme', newTheme);
    }
  };

  // 切換主題（在 light 和 dark 之間切換）
  const toggleTheme = () => {
    if (theme === 'system') {
      // 如果當前是系統主題，切換到相反的固定主題
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setTheme(systemPrefersDark ? 'light' : 'dark');
    } else {
      // 在 light 和 dark 之間切換
      setTheme(theme === 'light' ? 'dark' : 'light');
    }
  };

  // 初始化主題 - 立即應用保存的主題設置
  useEffect(() => {
    const html = document.documentElement;
    const savedTheme = localStorage.getItem('theme') as Theme;
    
    if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
      // 立即應用保存的主題
      html.setAttribute('data-theme', savedTheme);
    } else {
      // 應用系統主題
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      html.setAttribute('data-theme', systemPrefersDark ? 'dark' : 'light');
    }

    // 監聽系統主題變化
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemThemeChange = (e: MediaQueryListEvent) => {
      if (theme === 'system') {
        const newTheme = e.matches ? 'dark' : 'light';
        setActualTheme(newTheme);
        document.documentElement.setAttribute('data-theme', newTheme);
      }
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
  }, [theme]);

  const value: ThemeContextType = {
    theme,
    actualTheme,
    setTheme,
    toggleTheme,
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};

// 使用主題的 Hook
export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

// 主題切換按鈕組件
export const ThemeToggle: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { theme, actualTheme, toggleTheme } = useTheme();

  const getThemeIcon = () => {
    switch (actualTheme) {
      case 'light':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        );
      case 'dark':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        );
      default:
        return null;
    }
  };

  return (
    <button
      onClick={toggleTheme}
      className={`btn-base btn-secondary p-2 ${className}`}
      title={`切換到${actualTheme === 'light' ? '暗黑' : '明亮'}模式${theme === 'system' ? ' (當前跟隨系統)' : ''}`}
      aria-label="切換主題"
    >
      {getThemeIcon()}
    </button>
  );
};

// 主題選擇器組件
export const ThemeSelector: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { theme, setTheme } = useTheme();

  const themes: { value: Theme; label: string; icon: React.ReactNode }[] = [
    {
      value: 'light',
      label: '明亮模式',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ),
    },
    {
      value: 'dark',
      label: '暗黑模式',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      ),
    },
    {
      value: 'system',
      label: '跟隨系統',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      ),
    },
  ];

  return (
    <div className={`flex rounded-lg border border-surface-300 p-1 ${className}`}>
      {themes.map((themeOption) => (
        <button
          key={themeOption.value}
          onClick={() => setTheme(themeOption.value)}
          className={`
            flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all
            ${theme === themeOption.value
              ? 'bg-primary-600 text-white shadow-sm'
              : 'text-surface-600 hover:text-surface-900 hover:bg-surface-100'
            }
          `}
          title={themeOption.label}
        >
          {themeOption.icon}
          <span className="hidden sm:inline">{themeOption.label}</span>
        </button>
      ))}
    </div>
  );
}; 