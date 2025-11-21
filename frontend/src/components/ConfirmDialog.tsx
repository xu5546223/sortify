import React from 'react';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  content: string;
  confirmText?: string;
  cancelText?: string;
  isDanger?: boolean;
  isLoading?: boolean;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  content,
  confirmText = '確認',
  cancelText = '取消',
  isDanger = false,
  isLoading = false,
}) => {
  if (!isOpen) {
    return null;
  }

  const handleConfirm = () => {
    onConfirm();
  };

  return (
    <div
      className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
        className="w-full max-w-md bg-white border-3 border-neo-black shadow-[8px_8px_0px_0px_black]"
      >
        {/* Header */}
        <div className="bg-neo-primary text-neo-white px-6 py-4 border-b-3 border-neo-black flex items-center justify-between">
          <h2 className="font-display font-bold text-lg">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center bg-white text-neo-black border-2 border-neo-black shadow-neo-sm hover:bg-gray-100 transition-colors font-bold text-lg"
            aria-label="關閉"
            disabled={isLoading}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-gray-700 text-base leading-relaxed mb-6">
            {content}
          </p>

          {/* Actions */}
          <div className="flex gap-3 justify-end">
            <button
              onClick={onClose}
              disabled={isLoading}
              className="px-6 py-2 bg-gray-100 text-gray-700 border-2 border-neo-black shadow-neo-sm hover:bg-gray-200 hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {cancelText}
            </button>
            <button
              onClick={handleConfirm}
              disabled={isLoading}
              className={`px-6 py-2 border-2 border-neo-black shadow-neo-sm hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed ${
                isDanger
                  ? 'bg-red-600 text-white hover:bg-red-700'
                  : 'bg-neo-primary text-neo-white hover:bg-neo-primaryDark'
              }`}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  處理中...
                </span>
              ) : (
                confirmText
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
