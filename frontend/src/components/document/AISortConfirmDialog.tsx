/**
 * AI Sort 確認對話框
 * Neo-Brutalism 風格
 */

import React from 'react';

interface AISortConfirmDialogProps {
  isOpen: boolean;
  pendingCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

const AISortConfirmDialog: React.FC<AISortConfirmDialogProps> = ({
  isOpen,
  pendingCount,
  onConfirm,
  onCancel
}) => {
  if (!isOpen) return null;

  return (
    <>
      {/* 遮罩層 */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-4"
        onClick={onCancel}
      >
        {/* 對話框 */}
        <div 
          className="bg-neo-white border-3 border-neo-black shadow-neo-xl max-w-md w-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 標題欄 */}
          <div className="bg-neo-primary border-b-3 border-neo-black p-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-neo-black border-2 border-neo-white flex items-center justify-center">
                <span className="text-2xl">✨</span>
              </div>
              <div>
                <h2 className="font-display font-bold text-xl uppercase text-neo-black">
                  AI Sort
                </h2>
                <p className="text-xs font-bold text-neo-black opacity-80">
                  Smart Document Classification
                </p>
              </div>
            </div>
          </div>

          {/* 內容 */}
          <div className="p-6">
            <div className="mb-6">
              {pendingCount > 0 ? (
                <p className="text-base font-bold mb-4 text-neo-black">
                  準備對 <span className="bg-neo-hover px-2 py-1 border-2 border-neo-black text-neo-black">{pendingCount}</span> 個待分類文件進行 AI 分類。
                </p>
              ) : (
                <p className="text-base font-bold mb-4 text-neo-black">
                  準備啟動 AI 智能分類功能
                </p>
              )}
              
              <ul className="space-y-2 text-sm text-gray-700">
                <li className="flex items-start gap-2">
                  <span className="text-neo-primary font-bold">●</span>
                  <span>AI 將分析文件內容並自動分類</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-neo-active font-bold">●</span>
                  <span>相似文件會被分組到同一資料夾</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-neo-warn font-bold">●</span>
                  <span>{pendingCount > 0 ? '處理時間取決於文件數量' : '可以重新組織和優化現有文件分類'}</span>
                </li>
              </ul>
            </div>

            {/* 提示訊息 */}
            <div className="bg-gray-100 border-2 border-neo-black p-3 mb-6">
              <div className="flex items-start gap-2">
                <span className="text-lg">💡</span>
                <p className="text-xs font-semibold text-gray-700">
                  {pendingCount > 0 
                    ? '此操作將消耗 AI 配額。分類完成後可隨時調整結果。'
                    : '可以重新分類已有文件，或者添加新文件進行分類。分類完成後可隨時調整結果。'
                  }
                </p>
              </div>
            </div>

            {/* 按鈕組 */}
            <div className="flex gap-3">
              <button
                onClick={onCancel}
                className="flex-1 bg-neo-white text-neo-black border-3 border-neo-black px-4 py-3 font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100"
              >
                取消
              </button>
              <button
                onClick={onConfirm}
                className="flex-1 bg-neo-primary text-neo-black border-3 border-neo-black px-4 py-3 font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:bg-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100"
              >
                開始分類
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default AISortConfirmDialog;
