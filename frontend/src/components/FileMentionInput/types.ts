/**
 * @ 文件提及功能的类型定义
 */

export interface MentionedFile {
  id: string;
  filename: string;
  summary?: string;
  key_concepts?: string[];
  file_type?: string;
}

export interface FileMentionInputProps {
  value: string;
  onChange: (value: string) => void;
  mentionedFiles: MentionedFile[];
  onMentionedFilesChange: (files: MentionedFile[]) => void;
  placeholder?: string;
  disabled?: boolean;
  minHeight?: string;
  className?: string;
  enableSemanticSearch?: boolean;  // 新增：是否启用向量搜索
  showHint?: boolean;  // 新增：是否顯示輸入提示（默認 true）
  onFileSelected?: (file: MentionedFile) => void;  // 新增：選擇文件時的回調，用於立即添加到文件池
}

export interface FilePickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (file: MentionedFile) => void;
  position: { x: number; y: number };
  searchQuery: string;
}

export interface MentionedFileTagProps {
  file: MentionedFile;
  onRemove: (fileId: string) => void;
}
