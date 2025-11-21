/**
 * AI Sort 分類動畫 Modal
 * 基於 sortani.html 的 Neo-Brutalism 風格動畫
 */

import React, { useEffect, useState } from 'react';
import './AISortAnimation.css';

interface AISortAnimationModalProps {
  isOpen: boolean;
  onComplete: () => void;
  duration?: number; // 動畫持續時間（毫秒），預設 5000ms
}

const AISortAnimationModal: React.FC<AISortAnimationModalProps> = ({
  isOpen,
  onComplete,
  duration = 5000
}) => {
  const [showFiles, setShowFiles] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setShowFiles(false);
      return;
    }

    // 延遲 100ms 再顯示文件，確保 DOM 已經渲染
    const showFilesTimer = setTimeout(() => {
      setShowFiles(true);
    }, 100);

    // 不再自動關閉，讓動畫持續播放
    // 由父組件決定何時關閉（當後端任務完成時）

    return () => {
      clearTimeout(showFilesTimer);
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-neo-black bg-opacity-70 z-50 flex items-center justify-center p-4">
      <div className="bg-neo-bg border-3 border-neo-black shadow-neo-xl max-w-4xl w-full">
        {/* 標題欄 */}
        <div className="bg-neo-black text-neo-white border-b-3 border-neo-black p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-neo-primary border-2 border-neo-black flex items-center justify-center animate-pulse">
              <span className="text-lg">✨</span>
            </div>
            <h2 className="font-display font-bold text-lg uppercase">
              AI Processing...
            </h2>
          </div>
        </div>

        {/* 動畫容器 */}
        <div className="p-8">
          <div className="ai-sort-factory-container">
            {/* 狀態文字 */}
            <div className="ai-sort-status-text">AI PROCESSING...</div>

            {/* 傳送帶線條 */}
            <div className="ai-sort-conveyor-track"></div>

            {/* 中央掃描儀 */}
            <div className="ai-sort-scanner-box">
              <div className="ai-sort-scan-beam"></div>
              <div className="ai-sort-scanner-eye">
                <div className="ai-sort-scanner-pupil"></div>
              </div>
            </div>

            {/* 移動的文件 - 使用不同的文件類型圖標 */}
            {showFiles && (
              <>
                {/* 文件 1: 圖片 - 飛往 FINANCE */}
                <div className="ai-sort-file-item ai-sort-file-1">
                  <i className="ph-bold ph-file-image" style={{ fontSize: '28px', color: '#000' }}></i>
                </div>
                
                {/* 文件 2: PDF - 飛往 REVIEW */}
                <div className="ai-sort-file-item ai-sort-file-2">
                  <i className="ph-bold ph-file-pdf" style={{ fontSize: '28px', color: '#000' }}></i>
                </div>
                
                {/* 文件 3: DOC文件 - 飛往 DOCS */}
                <div className="ai-sort-file-item ai-sort-file-3">
                  <i className="ph-bold ph-file-doc" style={{ fontSize: '28px', color: '#000' }}></i>
                </div>
              </>
            )}

            {/* 接收資料夾 */}
            <div className="ai-sort-bucket-container">
              {/* Folder A: Teal */}
              <div className="ai-sort-folder-bucket ai-sort-bucket-teal">
                <i className="ph-fill ph-folder" style={{ fontSize: '50px', color: '#08bdbd' }}></i>
                <div className="ai-sort-folder-label ai-sort-label-teal">FINANCE</div>
              </div>

              {/* Folder B: Green */}
              <div className="ai-sort-folder-bucket ai-sort-bucket-green">
                <i className="ph-fill ph-folder" style={{ fontSize: '50px', color: '#29bf12' }}></i>
                <div className="ai-sort-folder-label ai-sort-label-green">DOCS</div>
              </div>

              {/* Folder C: Orange */}
              <div className="ai-sort-folder-bucket ai-sort-bucket-orange">
                <i className="ph-fill ph-folder" style={{ fontSize: '50px', color: '#ff9914' }}></i>
                <div className="ai-sort-folder-label ai-sort-label-orange">REVIEW</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AISortAnimationModal;
