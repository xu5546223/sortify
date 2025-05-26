import React, { useState } from 'react';
import { 
  Button, 
  Input, 
  StatusTag, 
  Card, 
  ThemeToggle, 
  ThemeSelector, 
  useTheme,
  titleStyles
} from '../components/ui';

export const ThemeShowcasePage: React.FC = () => {
  const { theme, actualTheme } = useTheme();
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLoadingDemo = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 2000);
  };

  return (
    <div className="min-h-screen bg-surface-50 p-6">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* 頁面標題 */}
        <div className="flex items-center justify-between">
          <h1 className={titleStyles.page}>
            Sortify 主題系統展示
          </h1>
          <div className="flex items-center gap-4">
            <ThemeSelector />
            <ThemeToggle />
          </div>
        </div>

        {/* 當前主題信息 */}
        <Card>
          <h2 className={titleStyles.section}>當前主題信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="text-sm font-medium text-surface-600">用戶選擇</p>
              <p className="text-lg font-semibold text-surface-900">{theme}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-surface-600">實際應用</p>
              <p className="text-lg font-semibold text-surface-900">{actualTheme}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-surface-600">系統偏好</p>
              <p className="text-lg font-semibold text-surface-900">
                {window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'}
              </p>
            </div>
          </div>
        </Card>

        {/* 按鈕組件展示 */}
        <Card>
          <h2 className={titleStyles.section}>按鈕組件</h2>
          <div className="space-y-6">
            {/* 按鈕變體 */}
            <div>
              <h3 className="text-lg font-medium text-surface-800 mb-3">按鈕變體</h3>
              <div className="flex flex-wrap gap-3">
                <Button variant="primary">主要按鈕</Button>
                <Button variant="secondary">次要按鈕</Button>
                <Button variant="success">成功按鈕</Button>
                <Button variant="danger">危險按鈕</Button>
              </div>
            </div>

            {/* 按鈕尺寸 */}
            <div>
              <h3 className="text-lg font-medium text-surface-800 mb-3">按鈕尺寸</h3>
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="primary" size="sm">小按鈕</Button>
                <Button variant="primary" size="md">中按鈕</Button>
                <Button variant="primary" size="lg">大按鈕</Button>
              </div>
            </div>

            {/* 按鈕狀態 */}
            <div>
              <h3 className="text-lg font-medium text-surface-800 mb-3">按鈕狀態</h3>
              <div className="flex flex-wrap gap-3">
                <Button 
                  variant="primary" 
                  loading={loading}
                  onClick={handleLoadingDemo}
                >
                  {loading ? '載入中...' : '點擊載入'}
                </Button>
                <Button variant="secondary" disabled>禁用按鈕</Button>
                <Button 
                  variant="success" 
                  icon={
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  }
                >
                  帶圖標
                </Button>
                <Button variant="primary" fullWidth>
                  全寬按鈕
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* 輸入框組件展示 */}
        <Card>
          <h2 className={titleStyles.section}>輸入框組件</h2>
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Input
                label="基礎輸入框"
                placeholder="請輸入內容..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
              
              <Input
                label="帶圖標的輸入框"
                placeholder="搜索..."
                leftIcon={
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                }
              />
              
              <Input
                label="錯誤狀態"
                placeholder="無效輸入"
                error="此欄位為必填項目"
              />
              
              <Input
                label="帶提示的輸入框"
                placeholder="用戶名"
                hint="用戶名必須是唯一的"
              />
            </div>
          </div>
        </Card>

        {/* 狀態標籤展示 */}
        <Card>
          <h2 className={titleStyles.section}>狀態標籤</h2>
          <div className="flex flex-wrap gap-3">
            <StatusTag status="success">成功</StatusTag>
            <StatusTag status="warning">警告</StatusTag>
            <StatusTag status="error">錯誤</StatusTag>
            <StatusTag status="info">信息</StatusTag>
            <StatusTag 
              status="success"
              icon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              }
            >
              已完成
            </StatusTag>
          </div>
        </Card>

        {/* 卡片展示 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card padding="sm">
            <h3 className="font-semibold text-surface-900 mb-2">小間距卡片</h3>
            <p className="text-surface-600">這是一個使用小間距的卡片。</p>
          </Card>
          
          <Card padding="md">
            <h3 className="font-semibold text-surface-900 mb-2">中間距卡片</h3>
            <p className="text-surface-600">這是一個使用中間距的卡片。</p>
          </Card>
          
          <Card padding="lg">
            <h3 className="font-semibold text-surface-900 mb-2">大間距卡片</h3>
            <p className="text-surface-600">這是一個使用大間距的卡片。</p>
          </Card>
        </div>

        {/* 顏色系統展示 */}
        <Card>
          <h2 className={titleStyles.section}>顏色系統</h2>
          <div className="space-y-6">
            {/* 主品牌色 */}
            <div>
              <h3 className="text-lg font-medium text-surface-800 mb-3">主品牌色</h3>
              <div className="grid grid-cols-5 md:grid-cols-10 gap-2">
                {[50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((shade) => (
                  <div key={shade} className="text-center">
                    <div 
                      className={`h-12 rounded-md bg-primary-${shade} border border-surface-200`}
                      style={{ backgroundColor: `var(--color-primary-${shade})` }}
                    />
                    <span className="text-xs text-surface-600 mt-1 block">{shade}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 成功色 */}
            <div>
              <h3 className="text-lg font-medium text-surface-800 mb-3">成功色</h3>
              <div className="grid grid-cols-5 md:grid-cols-10 gap-2">
                {[50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((shade) => (
                  <div key={shade} className="text-center">
                    <div 
                      className={`h-12 rounded-md border border-surface-200`}
                      style={{ backgroundColor: `var(--color-success-${shade})` }}
                    />
                    <span className="text-xs text-surface-600 mt-1 block">{shade}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* 表格樣式展示 */}
        <Card padding="none">
          <div className="table-container">
            <table className="table-base">
              <thead className="table-header">
                <tr>
                  <th>文件名</th>
                  <th>狀態</th>
                  <th>上傳時間</th>
                  <th>大小</th>
                </tr>
              </thead>
              <tbody>
                <tr className="table-row">
                  <td className="table-cell">示例文件.pdf</td>
                  <td className="table-cell">
                    <StatusTag status="success">已完成</StatusTag>
                  </td>
                  <td className="table-cell">2024-01-20 14:30</td>
                  <td className="table-cell">2.5 MB</td>
                </tr>
                <tr className="table-row">
                  <td className="table-cell">報告.docx</td>
                  <td className="table-cell">
                    <StatusTag status="warning">處理中</StatusTag>
                  </td>
                  <td className="table-cell">2024-01-20 15:45</td>
                  <td className="table-cell">1.8 MB</td>
                </tr>
                <tr className="table-row">
                  <td className="table-cell">數據.xlsx</td>
                  <td className="table-cell">
                    <StatusTag status="error">失敗</StatusTag>
                  </td>
                  <td className="table-cell">2024-01-20 16:20</td>
                  <td className="table-cell">3.2 MB</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}; 