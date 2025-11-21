import React from 'react';
import { useFileMention } from './useFileMention';
import FilePicker from './FilePicker';
import MentionedFileTag from './MentionedFileTag';
import type { FileMentionInputProps } from './types';

/**
 * 支持 @ 文件提及的智能输入框组件
 * 
 * 使用示例:
 * ```tsx
 * const [question, setQuestion] = useState('');
 * const [mentionedFiles, setMentionedFiles] = useState<MentionedFile[]>([]);
 * 
 * <FileMentionInput
 *   value={question}
 *   onChange={setQuestion}
 *   mentionedFiles={mentionedFiles}
 *   onMentionedFilesChange={setMentionedFiles}
 *   placeholder="Ask AI anything... (Type @ to tag files)"
 * />
 * ```
 */
const FileMentionInput: React.FC<FileMentionInputProps> = ({
  value,
  onChange,
  mentionedFiles,
  onMentionedFilesChange,
  placeholder = '輸入內容...',
  disabled = false,
  minHeight = '100px',
  className = '',
  enableSemanticSearch = true,
  showHint = true,
  onFileSelected,  // ✅ 新增回調
}) => {
  const {
    showFilePicker,
    filePickerPosition,
    availableFiles,
    isLoadingFiles,
    selectedIndex,
    textareaRef,
    handleInputChange,
    selectFile,
    removeFile,
    handleKeyDown,
    closeFilePicker,
  } = useFileMention(enableSemanticSearch);
  
  // ✅ 封裝選擇文件的邏輯
  const handleFileSelect = (file: any) => {
    // 如果提供了 onFileSelected，立即觸發並清除 @
    if (onFileSelected) {
      onFileSelected(file);
      // 清除輸入框中的 @ 文本
      const atIndex = value.lastIndexOf('@');
      if (atIndex !== -1) {
        const newValue = value.substring(0, atIndex) + value.substring(value.length);
        onChange(newValue.trim());
      }
      closeFilePicker();
    } else {
      // 原有邏輯：添加到 mentionedFiles
      selectFile(file, value, mentionedFiles, onChange, onMentionedFilesChange);
    }
  };

  return (
    <div className="relative w-full">
      {/* 输入框 */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => handleInputChange(e, onChange)}
        onKeyDown={(e) => handleKeyDown(e, value, mentionedFiles, onChange, onMentionedFilesChange)}
        placeholder={placeholder}
        disabled={disabled}
        className={`
          w-full px-4 py-3 
          bg-white 
          border-2 border-neo-black 
          rounded-lg 
          font-sans text-base text-neo-black font-bold
          placeholder:text-gray-400 placeholder:font-normal
          focus:outline-none focus:ring-2 focus:ring-neo-primary focus:border-neo-primary
          disabled:bg-gray-100 disabled:cursor-not-allowed
          resize-none
          ${className}
        `}
        style={{ minHeight }}
      />

      {/* 文档选择器 */}
      <FilePicker
        isOpen={showFilePicker}
        onClose={closeFilePicker}
        onSelect={handleFileSelect}
        position={filePickerPosition}
        searchQuery={(value.match(/@([^\s\n]*)$/)?.[1] || '')}
        files={availableFiles}
        isLoading={isLoadingFiles}
        selectedIndex={selectedIndex}
      />

      {/* 已提及文件标签 - 只在未使用 onFileSelected 時顯示 */}
      {!onFileSelected && mentionedFiles.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2 items-center">
          <div className="text-xs text-gray-500 font-bold flex items-center gap-1">
            <i className="ph-bold ph-paperclip text-neo-primary" />
            <span>已附加文件:</span>
          </div>
          {mentionedFiles.map((file) => (
            <MentionedFileTag
              key={file.id}
              file={file}
              onRemove={(fileId) => removeFile(fileId, value, mentionedFiles, onChange, onMentionedFilesChange)}
            />
          ))}
        </div>
      )}

      {/* 提示信息 */}
      {showHint && mentionedFiles.length === 0 && !showFilePicker && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-gray-500">
          <i className="ph-bold ph-lightning text-neo-primary" />
          <span>輸入 <kbd className="px-1.5 py-0.5 bg-neo-primary/10 border border-neo-primary/30 rounded font-mono text-[10px] font-bold text-neo-primary">@</kbd> 立即搜索文件（{enableSemanticSearch ? '文件名 + 語義搜索' : '僅文件名搜索'}）</span>
        </div>
      )}
      
      {/* 搜索状态提示 */}
      {showFilePicker && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-neo-primary animate-pulse">
          <i className="ph-bold ph-at" />
          <span>正在搜索文件...</span>
        </div>
      )}
    </div>
  );
};

export default FileMentionInput;
