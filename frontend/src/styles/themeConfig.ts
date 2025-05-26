// Sortify 主題配置文件
export const themeConfig = {
  // 顏色系統
  colors: {
    primary: {
      50: 'var(--color-primary-50)',
      100: 'var(--color-primary-100)',
      200: 'var(--color-primary-200)',
      300: 'var(--color-primary-300)',
      400: 'var(--color-primary-400)',
      500: 'var(--color-primary-500)',
      600: 'var(--color-primary-600)',
      700: 'var(--color-primary-700)',
      800: 'var(--color-primary-800)',
      900: 'var(--color-primary-900)',
    },
    success: {
      50: 'var(--color-success-50)',
      100: 'var(--color-success-100)',
      200: 'var(--color-success-200)',
      300: 'var(--color-success-300)',
      400: 'var(--color-success-400)',
      500: 'var(--color-success-500)',
      600: 'var(--color-success-600)',
      700: 'var(--color-success-700)',
      800: 'var(--color-success-800)',
      900: 'var(--color-success-900)',
    },
    warning: {
      50: 'var(--color-warning-50)',
      100: 'var(--color-warning-100)',
      200: 'var(--color-warning-200)',
      300: 'var(--color-warning-300)',
      400: 'var(--color-warning-400)',
      500: 'var(--color-warning-500)',
      600: 'var(--color-warning-600)',
      700: 'var(--color-warning-700)',
      800: 'var(--color-warning-800)',
      900: 'var(--color-warning-900)',
    },
    error: {
      50: 'var(--color-error-50)',
      100: 'var(--color-error-100)',
      200: 'var(--color-error-200)',
      300: 'var(--color-error-300)',
      400: 'var(--color-error-400)',
      500: 'var(--color-error-500)',
      600: 'var(--color-error-600)',
      700: 'var(--color-error-700)',
      800: 'var(--color-error-800)',
      900: 'var(--color-error-900)',
    },
    surface: {
      50: 'var(--color-surface-50)',
      100: 'var(--color-surface-100)',
      200: 'var(--color-surface-200)',
      300: 'var(--color-surface-300)',
      400: 'var(--color-surface-400)',
      500: 'var(--color-surface-500)',
      600: 'var(--color-surface-600)',
      700: 'var(--color-surface-700)',
      800: 'var(--color-surface-800)',
      900: 'var(--color-surface-900)',
    },
  },

  // 字體系統
  fonts: {
    brand: 'var(--font-brand)',
    heading: 'var(--font-heading)',
    body: 'var(--font-body)',
    mono: 'var(--font-mono)',
  },

  // 間距系統
  spacing: {
    section: 'var(--spacing-section)',
    card: 'var(--spacing-card)',
    component: 'var(--spacing-component)',
  },

  // 圓角系統
  radius: {
    card: 'var(--radius-card)',
    button: 'var(--radius-button)',
    input: 'var(--radius-input)',
    modal: 'var(--radius-modal)',
  },

  // 陰影系統
  shadows: {
    card: 'var(--shadow-card)',
    cardHover: 'var(--shadow-card-hover)',
    modal: 'var(--shadow-modal)',
    button: 'var(--shadow-button)',
  },

  // 動畫緩動
  easing: {
    ui: 'var(--ease-ui)',
    smooth: 'var(--ease-smooth)',
    bounce: 'var(--ease-bounce)',
  },

  // 動畫
  animations: {
    fadeIn: 'var(--animate-fade-in)',
    slideUp: 'var(--animate-slide-up)',
    scaleIn: 'var(--animate-scale-in)',
  },
} as const;

// 主題類型定義
export type ThemeColors = keyof typeof themeConfig.colors;
export type ColorShades = keyof typeof themeConfig.colors.primary;

// 狀態類型
export type StatusType = 'success' | 'warning' | 'error' | 'info';

// 按鈕變體類型
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'success' | 'outline';

// 尺寸類型
export type ComponentSize = 'sm' | 'md' | 'lg';

// 主題輔助函數
export const getColor = (color: ThemeColors, shade: ColorShades = 500) => {
  return themeConfig.colors[color][shade];
};

// 狀態顏色映射
export const statusColorMap: Record<StatusType, ThemeColors> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'primary',
};

// 按鈕樣式配置
export const buttonStyles = {
  base: 'btn-base',
  variants: {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    danger: 'btn-danger',
    success: 'btn-success',
    outline: 'btn-outline',
  },
  sizes: {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  },
} as const;

// 輸入框樣式配置
export const inputStyles = {
  base: 'input-base',
  error: 'input-error',
} as const;

// 狀態標籤樣式配置
export const statusTagStyles = {
  base: 'status-tag',
  variants: {
    success: 'status-success',
    warning: 'status-warning',
    error: 'status-error',
    info: 'status-info',
  },
} as const;

// 表格樣式配置
export const tableStyles = {
  container: 'table-container',
  base: 'table-base',
  header: 'table-header',
  row: 'table-row',
  cell: 'table-cell',
} as const;

// 模態框樣式配置
export const modalStyles = {
  overlay: 'modal-overlay',
  content: 'modal-content',
} as const;

// 訊息提示樣式配置
export const messageStyles = {
  toast: 'message-toast',
  variants: {
    success: 'message-success',
    error: 'message-error',
    info: 'message-info',
  },
} as const;

// 側邊欄樣式配置
export const sidebarStyles = {
  base: 'sidebar',
  link: 'sidebar-link',
} as const;

// 卡片樣式配置
export const cardStyles = {
  base: 'card',
} as const;

// 標題樣式配置
export const titleStyles = {
  page: 'page-title',
  section: 'section-title',
} as const;

// CSS 類名組合輔助函數
export const cn = (...classes: (string | undefined | null | false)[]): string => {
  return classes.filter(Boolean).join(' ');
};

// 主題切換輔助函數
export const toggleTheme = () => {
  const html = document.documentElement;
  const currentTheme = html.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  return newTheme;
};

// 初始化主題
export const initializeTheme = () => {
  const html = document.documentElement;
  const savedTheme = localStorage.getItem('theme');
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  const theme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
  html.setAttribute('data-theme', theme);
  return theme;
};

// 響應式斷點
export const breakpoints = {
  xs: '480px',
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
  '3xl': '1920px',
} as const;

export type Breakpoint = keyof typeof breakpoints; 