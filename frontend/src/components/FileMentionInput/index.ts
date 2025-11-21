/**
 * FileMentionInput - 支持 @ 文件提及的智能输入框
 * 
 * 导出主要组件和类型定义
 */

export { default as FileMentionInput } from './FileMentionInput';
export { default as MentionedFileTag } from './MentionedFileTag';
export { default as FilePicker } from './FilePicker';
export { useFileMention } from './useFileMention';

export type {
  MentionedFile,
  FileMentionInputProps,
  FilePickerProps,
  MentionedFileTagProps,
} from './types';
