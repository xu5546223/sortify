# 📘 Sortify Design System v2.0: Neo-Brutalism Green Edition

**風格定義**: Neo-Brutalism (新粗野主義) / High Contrast / Functional
**核心理念**: 結構優先，色彩為輔。粗黑邊框，硬陰影，無模糊。

---

## 1. 色彩系統 (Color Palette)

我們採用 **功能性配色** 策略。色彩不應隨意使用，必須具有明確含義。

### 🎨 品牌與基礎色 (Brand & Base)
| 角色 (Role) | 色名 (Name) | Hex Code | 應用場景 (Usage) |
| :--- | :--- | :--- | :--- |
| **Primary (主色)** | **Bright Fern** | `#29bf12` | Logo, 主要按鈕背景, 頁面標題裝飾, 強調邊框 |
| **Base Black** | **Ink Black** | `#000000` | **所有**邊框, 文字, 硬陰影, 圖標 |
| **Base White** | **Paper White** | `#ffffff` | 卡片背景, 輸入框背景, 次級按鈕背景 |
| **Background** | **Engine Gray** | `#f3f4f6` | 網頁整體底色 (Tailwind `gray-100`) |

### 📍 狀態與交互色 (State & Interaction)
| 角色 (Role) | 色名 (Name) | Hex Code | 應用場景 (Usage) |
| :--- | :--- | :--- | :--- |
| **Active (當前狀態)** | **Tropical Teal** | `#08bdbd` | **當前選中的 Tab**, 側邊欄選中項, Toggle 開關, Checkbox 勾選 |
| **Hover (懸停/高亮)** | **Green Yellow** | `#abff4f` | 滑鼠懸停 (Hover) 效果, 游標光標, 互動反饋閃爍 |
| **Warning (警告)** | **Deep Saffron** | `#ff9914` | 系統提示, 待處理事項, 低級別錯誤 |
| **Critical (錯誤)** | **Lipstick Red** | `#f21b3f` | 刪除按鈕, 錯誤彈窗, 緊急狀態標籤 |

---

## 2. 邊框與陰影 (Borders & Shadows)

這是此風格的靈魂。**拒絕模糊 (NO BLUR)**。

### 📐 邊框規範 (Borders)
*   **顏色**: 統一使用 `#000000` (純黑)。
*   **粗細**:
    *   **Desktop (電腦端)**: `3px` (強調穩重感)
    *   **Mobile (手機端)**: `2px` (保持精細度)
    *   **Divider (分割線)**: `2px`

### 🌑 陰影規範 (Hard Shadows)
使用純色位移，不透明。
*   **Shadow-SM**: `2px 2px 0px 0px #000000` (輸入框, 小標籤)
*   **Shadow-MD**: `4px 4px 0px 0px #000000` (按鈕, 列表項)
*   **Shadow-LG**: `6px 6px 0px 0px #000000` (主卡片, 模態框)
*   **Shadow-XL**: `8px 8px 0px 0px #000000` (桌面端主容器)

### ⭕ 圓角規範 (Border Radius)
*   **Desktop**:
    *   卡片/容器: `0px` (直角) 或 `4px` (微圓角)
    *   按鈕: `0px`
*   **Mobile**:
    *   卡片/容器: `12px` (稍微友好的圓角)
    *   按鈕: `8px`

---

## 3. 排版系統 (Typography)

*   **標題 (Headings)**: `Space Grotesk` 或 `JetBrains Mono`
    *   Weight: 700 (Bold)
    *   Transform: Uppercase (全大寫)
*   **正文 (Body)**: `Inter`
    *   Weight: 500 (Medium) - 為了對抗粗邊框，字體稍微加粗一點閱讀性更好。
    *   Color: `#000000` (主文), `#4b5563` (次要)

---

## 4. 組件設計指南 (Component Specs)

### A. 按鈕 (Buttons)

#### 1. Primary Button (主要操作)
*   **背景**: `Bright Fern (#29bf12)`
*   **文字**: `#000000`, Bold, Uppercase
*   **邊框**: `2px solid #000000`
*   **陰影**: `4px 4px 0px 0px #000000`
*   **交互**:
    *   Hover: 背景變 `Green Yellow (#abff4f)`, 陰影變 `6px 6px`
    *   Active: 陰影歸零 (`0px 0px`), `transform: translate(4px, 4px)`

#### 2. Navigation Item (導航項 - Sidebar)
*   **Default (默認)**:
    *   背景: Transparent
    *   文字: `#000000`
    *   圖標: `#000000`
*   **Active (當前選中)**:
    *   背景: `Tropical Teal (#08bdbd)`
    *   文字: `#ffffff` (白色) 或 `#000000` (黑色) - *推薦白色以獲得最強對比*
    *   邊框: `2px solid #000000`
    *   陰影: `3px 3px 0px 0px #000000`

### B. 狀態標籤 (Status Tags)
*   結構: `border: 2px solid black`, `font-size: 12px`, `font-weight: bold`, `padding: 2px 8px`
*   **完成**: 背景 `#29bf12` (Fern) + 黑字
*   **進行中**: 背景 `#08bdbd` (Teal) + 白字
*   **警告**: 背景 `#ff9914` (Saffron) + 黑字
*   **錯誤**: 背景 `#f21b3f` (Red) + 白字

### C. 輸入框 (Inputs)
*   背景: `#ffffff`
*   邊框: `2px solid #000000`
*   陰影: `2px 2px 0px 0px rgba(0,0,0,0.2)`
*   **Focus 狀態**:
    *   背景: `#ffffff`
    *   邊框: `2px solid #000000`
    *   陰影: `4px 4px 0px 0px #29bf12` (聚焦時陰影變**主綠色**)

---

## 5. 實作 CSS 變數 (Tailwind Config Ready)

將此代碼塊複製到你的 CSS 根目錄或 Tailwind 配置中。

```css
:root {
    /* --- Palette --- */
    --color-primary: #29bf12;  /* Bright Fern */
    --color-active: #08bdbd;   /* Tropical Teal */
    --color-hover: #abff4f;    /* Green Yellow */
    --color-error: #f21b3f;    /* Lipstick Red */
    --color-warn: #ff9914;     /* Deep Saffron */
    
    --color-black: #000000;
    --color-white: #ffffff;
    --color-bg: #f3f4f6;

    /* --- Borders --- */
    --border-width-pc: 3px;
    --border-width-m: 2px;
    --border-main: var(--border-width-pc) solid var(--color-black);

    /* --- Shadows (X Y Blur Spread Color) --- */
    --shadow-sm: 2px 2px 0px 0px var(--color-black);
    --shadow-md: 4px 4px 0px 0px var(--color-black);
    --shadow-lg: 6px 6px 0px 0px var(--color-black);
    
    /* --- Transitions --- */
    --trans-bounce: all 0.15s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* Utility Classes Examples */

.neo-box {
    background-color: var(--color-white);
    border: var(--border-main);
    box-shadow: var(--shadow-lg);
}

.neo-btn-primary {
    background-color: var(--color-primary);
    color: var(--color-black);
    border: var(--border-main);
    box-shadow: var(--shadow-md);
    font-weight: 700;
    text-transform: uppercase;
    transition: var(--trans-bounce);
}

.neo-btn-primary:hover {
    background-color: var(--color-hover); /* Hover to Yellow-Green */
    transform: translate(-2px, -2px);
    box-shadow: 6px 6px 0px 0px var(--color-black);
}

.neo-btn-primary:active {
    transform: translate(2px, 2px);
    box-shadow: 0px 0px 0px 0px var(--color-black);
}

/* Active Navigation State */
.nav-item.active {
    background-color: var(--color-active); /* Teal */
    color: white;
    border: 2px solid var(--color-black);
    box-shadow: var(--shadow-sm);
}