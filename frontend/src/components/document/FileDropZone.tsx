import React, { useRef, useState, useEffect } from 'react';
import AISortConfirmDialog from './AISortConfirmDialog';
import AISortAnimationModal from './AISortAnimationModal';
import { triggerClustering, getClusteringStatus } from '../../services/clusteringService';
import { ClusteringJobStatus } from '../../types/apiTypes';

interface FileDropZoneProps {
  onFilesSelected: (files: FileList) => void;
  isUploading: boolean;
  pendingCount: number;
  onClusteringComplete?: () => void;
}

const FileDropZone: React.FC<FileDropZoneProps> = ({
  onFilesSelected,
  isUploading,
  pendingCount,
  onClusteringComplete
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [showAnimation, setShowAnimation] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobStatus, setJobStatus] = useState<ClusteringJobStatus | null>(null);

  // 清理輪詢
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      onFilesSelected(files);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onFilesSelected(files);
    }
  };

  // AI Sort 按鈕點擊 - 彈出確認對話框
  const handleAISortClick = () => {
    // 即使沒有文件也可以查看動畫演示
    setShowConfirmDialog(true);
  };

  // 確認分類 - 顯示動畫並開始調用 API
  const handleConfirmSort = async () => {
    setShowConfirmDialog(false);
    setShowAnimation(true);
    setIsProcessing(true);

    try {
      // 調用聚類 API，使用 force_recluster=true 重新分類所有文件
      // 這會先清除舊的聚類數據，然後對所有文件進行重新分類
      const result = await triggerClustering(true);
      setJobStatus(result);
      
      // 開始輪詢狀態
      startPolling();
    } catch (error) {
      console.error('觸發聚類失敗:', error);
      setShowAnimation(false);
      setIsProcessing(false);
    }
  };

  // 輪詢聚類狀態
  const startPolling = () => {
    // 清理舊的輪詢
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = setInterval(async () => {
      try {
        const status = await getClusteringStatus();
        setJobStatus(status);

        // 任務完成或失敗時停止輪詢
        if (status && (status.status === 'completed' || status.status === 'failed')) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          setShowAnimation(false);
          setIsProcessing(false);
          
          if (status.status === 'completed') {
            // 發送聚類完成事件，通知其他組件刷新
            window.dispatchEvent(new CustomEvent('clustering-complete'));
            console.log('📢 聚類完成，已發送刷新事件');
            
            if (onClusteringComplete) {
              onClusteringComplete();
            }
          }
        }
      } catch (error) {
        console.error('獲取聚類狀態失敗:', error);
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        setShowAnimation(false);
        setIsProcessing(false);
      }
    }, 2000); // 每2秒輪詢一次

    // 最多輪詢5分鐘後自動停止
    setTimeout(() => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (isProcessing) {
        setShowAnimation(false);
        setIsProcessing(false);
      }
    }, 300000);
  };

  return (
    <section className="mb-8">
      <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-0 flex flex-col md:flex-row relative">
        {/* 左：Drop Zone */}
        <div
          onClick={handleClick}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className={`flex-1 p-8 border-r-3 border-neo-black border-dashed bg-neo-white hover:bg-green-50 transition-colors cursor-pointer flex flex-col items-center justify-center text-center group ${
            isDragging ? 'bg-green-50 scale-[0.99]' : ''
          }`}
        >
          <div className={`w-14 h-14 bg-neo-primary border-2 border-neo-black rounded-full flex items-center justify-center mb-3 shadow-[4px_4px_0px_black] group-hover:scale-110 transition-transform ${
            isDragging ? 'scale-110' : ''
          }`}>
            <span className="text-2xl font-bold">
              {isUploading ? '⏳' : '➕'}
            </span>
          </div>
          <h3 className="font-display font-bold text-lg uppercase">
            {isUploading ? 'Uploading...' : 'Drag & Drop files here'}
          </h3>
          <p className="text-sm text-gray-500 font-semibold mt-1">
            or click to browse (PDF, JPG, DOCX)
          </p>
        </div>

        {/* 右：AI 分類控制 */}
        <div className="w-full md:w-80 bg-neo-warn border-b-3 md:border-b-0 md:border-t-0 border-neo-black flex flex-col">
          {/* 頂部：待處理統計 */}
          <div className="p-6 flex flex-col justify-center items-center text-center border-b-3 border-neo-black">
            <div className="text-5xl font-display font-black mb-2 text-neo-black">
              {pendingCount}
            </div>
            <div className="text-xs font-bold uppercase tracking-wider text-neo-black">
              Files Pending
            </div>
          </div>

          {/* AI 分類按鈕 */}
          <div className="p-4">
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleAISortClick();
              }}
              className="w-full bg-neo-black text-neo-white border-3 border-neo-black px-4 py-3 text-sm font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 flex items-center gap-2 justify-center"
            >
              <span>✨</span> AI Sort
            </button>
          </div>
        </div>
      </div>

      {/* 隱藏的 file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".txt,.pdf,.jpg,.jpeg,.png,.gif,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* 確認對話框 */}
      <AISortConfirmDialog
        isOpen={showConfirmDialog}
        pendingCount={pendingCount}
        onConfirm={handleConfirmSort}
        onCancel={() => setShowConfirmDialog(false)}
      />

      {/* 分類動畫 - 持續播放直到任務完成 */}
      <AISortAnimationModal
        isOpen={showAnimation}
        onComplete={() => {}} // 不再自動關閉，由任務完成時控制
        duration={5000}
      />
    </section>
  );
};

export default FileDropZone;
