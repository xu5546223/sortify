# Sortify 主題系統

統一的前端樣式管理系統，基於 Tailwind CSS 和現代 CSS 特性構建。

## 核心特色

- 🎨 統一設計語言
- 🌙 暗黑模式支持  
- 🧩 可重用組件
- 📱 響應式設計
- ♿ 無障礙支持

## 快速開始

### 1. 添加主題提供者
```tsx
import { ThemeProvider } from './contexts/ThemeContext';

function App() {
  return (
    <ThemeProvider>
      <YourApp />
    </ThemeProvider>
  );
}
```

### 2. 使用組件
```tsx
import { Button, Input, Card } from './components/ui';

function MyPage() {
  return (
    <Card>
      <Input label="用戶名" />
      <Button variant="primary">提交</Button>
    </Card>
  );
}
```

## 主要組件

- **Button**: 統一按鈕組件
- **Input**: 輸入框組件
- **StatusTag**: 狀態標籤
- **Card**: 卡片容器
- **ThemeToggle**: 主題切換按鈕

## 設計系統

### 顏色
- Primary (主品牌色)
- Success (成功狀態)
- Warning (警告狀態)
- Error (錯誤狀態)
- Surface (中性色)

### 主題模式
- Light (明亮模式)
- Dark (暗黑模式)  
- System (跟隨系統)

詳細文檔請參考組件示例頁面。 