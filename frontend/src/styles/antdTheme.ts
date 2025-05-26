import { ThemeConfig } from 'antd';

// 通用 token 配置
const commonTokens = {
  // 圓角配置
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 6,
  borderRadiusXS: 4,

  // 字體配置
  fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
  fontSize: 14,
  fontSizeLG: 16,
  fontSizeSM: 12,
  fontSizeXL: 20,

  // 陰影配置
  boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
  boxShadowSecondary: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',

  // 動畫配置
  motionDurationSlow: '0.3s',
  motionDurationMid: '0.2s',
  motionDurationFast: '0.1s',

  // 間距配置
  paddingLG: 24,
  padding: 16,
  paddingSM: 12,
  paddingXS: 8,
  paddingXXS: 4,

  marginLG: 24,
  margin: 16,
  marginSM: 12,
  marginXS: 8,
  marginXXS: 4,
};

// 明亮模式主題配置
export const lightTheme: ThemeConfig = {
  token: {
    ...commonTokens,
    
    // 品牌色系
    colorPrimary: '#4F46E5', // 對應 CSS 變量 --color-primary-600
    colorSuccess: '#059669', // 對應 CSS 變量 --color-success-600
    colorWarning: '#D97706', // 對應 CSS 變量 --color-warning-600
    colorError: '#DC2626',   // 對應 CSS 變量 --color-error-600
    colorInfo: '#4F46E5',    // 使用品牌色作為信息色

    // 背景色系
    colorBgBase: '#FFFFFF',        // 對應 CSS 變量 --color-surface-50 (淺色模式)
    colorBgContainer: '#FFFFFF',   // 容器背景
    colorBgElevated: '#FFFFFF',    // 浮起元素背景
    colorBgLayout: '#F9FAFB',      // 佈局背景，對應 --color-surface-100
    colorBgSpotlight: '#F3F4F6',   // 聚光燈背景，對應 --color-surface-200
    colorBgMask: 'rgba(0, 0, 0, 0.45)', // 遮罩背景

    // 邊框色系
    colorBorder: '#D1D5DB',        // 對應 CSS 變量 --color-surface-300
    colorBorderSecondary: '#E5E7EB', // 次要邊框，對應 --color-surface-200

    // 文字色系
    colorText: '#111827',          // 主要文字，對應 --color-surface-900
    colorTextSecondary: '#6B7280', // 次要文字，對應 --color-surface-500
    colorTextTertiary: '#9CA3AF',  // 三級文字，對應 --color-surface-400
    colorTextQuaternary: '#D1D5DB', // 四級文字，對應 --color-surface-300

    // 填充色系
    colorFill: '#F3F4F6',          // 對應 --color-surface-200
    colorFillSecondary: '#F9FAFB', // 對應 --color-surface-100
    colorFillTertiary: '#FFFFFF',  // 對應 --color-surface-50
    colorFillQuaternary: '#FFFFFF', // 最淺填充色

    // 分割線色
    colorSplit: '#E5E7EB',         // 對應 --color-surface-200
  },
  components: {
    // 佈局組件
    Layout: {
      headerBg: '#FFFFFF',
      siderBg: '#1F2937', // 暗色側邊欄
      triggerBg: '#374151',
    },
    
    // 表格組件
    Table: {
      headerBg: '#F9FAFB',
      rowHoverBg: '#F9FAFB',
      borderColor: '#E5E7EB',
    },
    
    // 卡片組件
    Card: {
      headerBg: 'transparent',
    },
    
    // 模態框組件
    Modal: {
      contentBg: '#FFFFFF',
      headerBg: 'transparent',
    },
    
    // 輸入框組件
    Input: {
      activeBorderColor: '#4F46E5',
      hoverBorderColor: '#6366F1',
    },
    
    // 按鈕組件
    Button: {
      primaryShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    },
  },
};

// 暗黑模式主題配置
export const darkTheme: ThemeConfig = {
  token: {
    ...commonTokens,
    
    // 品牌色系 (暗色模式下稍微調亮)
    colorPrimary: '#6366F1', // 對應 CSS 變量 --color-primary-500 (暗色模式)
    colorSuccess: '#10B981', // 對應 CSS 變量 --color-success-500 (暗色模式)
    colorWarning: '#F59E0B', // 對應 CSS 變量 --color-warning-500 (暗色模式)
    colorError: '#EF4444',   // 對應 CSS 變量 --color-error-500 (暗色模式)
    colorInfo: '#6366F1',    // 使用品牌色作為信息色

    // 背景色系 (對應暗色模式的 CSS 變量)
    colorBgBase: '#141619',        // 對應 CSS 變量 --color-surface-50 (暗色模式)
    colorBgContainer: '#1C1E22',   // 容器背景，對應 --color-surface-100 (暗色模式)
    colorBgElevated: '#252830',    // 浮起元素背景，對應 --color-surface-200 (暗色模式)
    colorBgLayout: '#0F1114',      // 佈局背景，比 base 更暗
    colorBgSpotlight: '#2D3138',   // 聚光燈背景，對應 --color-surface-300 (暗色模式)
    colorBgMask: 'rgba(0, 0, 0, 0.65)', // 遮罩背景

    // 邊框色系
    colorBorder: '#2D3138',        // 對應 CSS 變量 --color-surface-300 (暗色模式)
    colorBorderSecondary: '#252830', // 次要邊框，對應 --color-surface-200 (暗色模式)

    // 文字色系 (對應暗色模式的 CSS 變量)
    colorText: '#F3F4F6',          // 主要文字，對應 --color-surface-900 (暗色模式)
    colorTextSecondary: '#8C939F', // 次要文字，對應 --color-surface-600 (暗色模式)
    colorTextTertiary: '#6B7280',  // 三級文字，對應 --color-surface-500 (暗色模式)
    colorTextQuaternary: '#4B5563', // 四級文字，對應 --color-surface-400 (暗色模式)

    // 填充色系
    colorFill: '#252830',          // 對應 --color-surface-200 (暗色模式)
    colorFillSecondary: '#1C1E22', // 對應 --color-surface-100 (暗色模式)
    colorFillTertiary: '#141619',  // 對應 --color-surface-50 (暗色模式)
    colorFillQuaternary: '#0F1114', // 最深填充色

    // 分割線色
    colorSplit: '#252830',         // 對應 --color-surface-200 (暗色模式)
  },
  components: {
    // 佈局組件
    Layout: {
      headerBg: '#1C1E22',
      siderBg: '#0B0D0F', // 更暗的側邊欄
      triggerBg: '#252830',
    },
    
    // 表格組件
    Table: {
      headerBg: '#1C1E22',
      rowHoverBg: '#1C1E22',
      borderColor: '#252830',
    },
    
    // 卡片組件
    Card: {
      headerBg: 'transparent',
    },
    
    // 模態框組件
    Modal: {
      contentBg: '#1C1E22',
      headerBg: 'transparent',
    },
    
    // 輸入框組件
    Input: {
      activeBorderColor: '#6366F1',
      hoverBorderColor: '#8B5CF6',
    },
    
    // 按鈕組件
    Button: {
      primaryShadow: '0 1px 2px 0 rgb(0 0 0 / 0.25)',
    },
    
    // Alert 組件 - 深色模式下的顏色優化
    Alert: {
      // Warning Alert 在深色模式下的配置
      colorWarningBg: '#F59E0B', // 使用較亮的警告背景色
      colorWarningBorder: '#F59E0B',
      colorWarningText: '#1C1E22', // 使用深色文字確保對比度

      // Info Alert 在深色模式下的配置
      colorInfoBg: '#6366F1', // 使用品牌色作為信息背景
      colorInfoBorder: '#6366F1',
      colorInfoText: '#FFFFFF', // 白色文字

      // Error Alert 在深色模式下的配置
      colorErrorBg: '#EF4444', // 使用較亮的錯誤背景色
      colorErrorBorder: '#EF4444',
      colorErrorText: '#FFFFFF', // 白色文字

      // Success Alert 在深色模式下的配置
      colorSuccessBg: '#10B981', // 使用較亮的成功背景色
      colorSuccessBorder: '#10B981',
      colorSuccessText: '#FFFFFF', // 白色文字
    },
    
    // Typography 組件 - 確保文字在深色模式下清晰可見
    Typography: {
      titleMarginTop: '1.2em',
      titleMarginBottom: '0.5em',
    },
    
    // Tag 組件 - 深色模式下的顏色優化
    Tag: {
      defaultBg: '#252830',
      defaultColor: '#F3F4F6',
    },
  },
};

// 根據主題模式獲取對應的配置
export const getAntdTheme = (isDark: boolean): ThemeConfig => {
  return isDark ? darkTheme : lightTheme;
}; 