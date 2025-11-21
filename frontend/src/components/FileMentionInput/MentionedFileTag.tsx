import React from 'react';
import type { MentionedFileTagProps } from './types';

/**
 * 已提及文件的标签组件
 */
const MentionedFileTag: React.FC<MentionedFileTagProps> = ({ file, onRemove }) => {
  return (
    <div
      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-neo-primary/10 border-2 border-neo-black rounded-md shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-none hover:translate-x-[2px] hover:translate-y-[2px] transition-all group"
      title={file.summary || file.filename}
    >
      {/* 文件图标 */}
      <i className="ph-bold ph-file-text text-neo-primary text-sm" />
      
      {/* 文件名 */}
      <span className="text-xs font-bold text-neo-black truncate max-w-[150px]">
        {file.filename}
      </span>
      
      {/* 文件类型标签 */}
      {file.file_type && (
        <span className="text-[10px] px-1.5 py-0.5 bg-neo-black text-neo-white rounded font-bold uppercase">
          {file.file_type}
        </span>
      )}
      
      {/* 删除按钮 */}
      <button
        onClick={() => onRemove(file.id)}
        className="ml-1 w-4 h-4 flex items-center justify-center bg-red-600 text-white text-xs font-bold rounded hover:bg-red-700 transition-colors"
        aria-label="移除文件"
      >
        ✕
      </button>
    </div>
  );
};

export default MentionedFileTag;
