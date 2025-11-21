import { useState, useCallback, useEffect, useRef } from 'react';
import { getDocuments, getDocumentsByIds } from '../../services/documentService';
import { performSemanticSearch } from '../../services/vectorDBService';
import type { MentionedFile } from './types';

export const useFileMention = (enableSemanticSearch: boolean = true) => {
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [filePickerPosition, setFilePickerPosition] = useState({ x: 0, y: 0 });
  const [fileSearchQuery, setFileSearchQuery] = useState('');
  const [availableFiles, setAvailableFiles] = useState<MentionedFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 🔥 混合搜索：文件名 + 语义搜索
  const loadFiles = useCallback(async (query: string) => {
    setIsLoadingFiles(true);
    try {
      let allDocs: any[] = [];
      
      if (query) {
        // 🔥 根据开关决定是否启用语义搜索
        if (enableSemanticSearch) {
          // 混合搜索：文件名 + 语义搜索
          console.log('🔍 启用混合搜索（文件名 + 语义向量）');
          const [filenameResults, semanticResults] = await Promise.allSettled([
            getDocuments(query, 'all', undefined, 'created_at', 'desc', 0, 20),
            performSemanticSearch(query, 10, 0.4)  // threshold: 0.4 (严格), topK: 10
          ]);
          
          // 合并文件名搜索结果
          if (filenameResults.status === 'fulfilled') {
            allDocs = [...filenameResults.value.documents];
          }
          
          // 🔥 合并语义搜索结果 - 获取完整的文档信息
          if (semanticResults.status === 'fulfilled') {
            const semanticDocs = semanticResults.value;
            const existingIds = new Set(allDocs.map((d: any) => d.id));
            
            // 🎯 收集需要获取完整信息的文档 ID
            const documentIdsToFetch = semanticDocs
              .filter(result => !existingIds.has(result.document_id))
              .map(result => result.document_id);
            
            if (documentIdsToFetch.length > 0) {
              console.log(`📥 批量获取 ${documentIdsToFetch.length} 个文档的完整信息...`);
              
              // 🔥 批量获取完整的文档信息（包含 enriched_data）
              const fullDocs = await getDocumentsByIds(documentIdsToFetch);
              
              console.log(`✅ 成功获取 ${fullDocs.length} 个完整文档`);
              
              // 添加完整文档信息
              for (const doc of fullDocs) {
                if (doc && !existingIds.has(doc.id)) {
                  allDocs.push({
                    ...doc,
                    _searchScore: semanticDocs.find(r => r.document_id === doc.id)?.similarity_score
                  });
                  existingIds.add(doc.id);
                }
              }
            }
          }
        } else {
          // 仅文件名搜索
          console.log('🔍 仅使用文件名搜索（向量搜索已禁用）');
          const response = await getDocuments(query, 'all', undefined, 'created_at', 'desc', 0, 20);
          allDocs = response.documents;
        }
      } else {
        // 无搜索关键词：显示最近文档
        const response = await getDocuments('', 'all', undefined, 'created_at', 'desc', 0, 50);
        allDocs = response.documents;
      }
      
      // 只显示已向量化的文档
      const vectorizedDocs = allDocs.filter((doc: any) => 
        doc.vector_status === 'vectorized'
      );
      
      // 排序：优先显示高相关性结果
      if (query.trim()) {
        vectorizedDocs.sort((a: any, b: any) => {
          const scoreA = a._searchScore || 0;
          const scoreB = b._searchScore || 0;
          return scoreB - scoreA;
        });
      }
      
      const files: MentionedFile[] = vectorizedDocs.map((doc: any) => ({
        id: doc.id,
        filename: doc.filename,
        summary: doc.enriched_data?.summary || doc.analysis?.ai_analysis_output?.key_information?.content_summary,
        key_concepts: (doc.enriched_data as any)?.key_concepts || doc.analysis?.ai_analysis_output?.key_information?.key_concepts || [],
        file_type: doc.file_type,
      }));
      
      setAvailableFiles(files.slice(0, 20)); // 最多显示 20 个
      setSelectedIndex(0);
    } catch (error) {
      console.error('加载文档列表失败:', error);
      setAvailableFiles([]);
    } finally {
      setIsLoadingFiles(false);
    }
  }, [enableSemanticSearch]);

  // 🔥 实时搜索（减少防抖时间以提高响应速度）
  useEffect(() => {
    if (showFilePicker) {
      const timer = setTimeout(() => {
        loadFiles(fileSearchQuery);
      }, 150); // 从 300ms 减少到 150ms，更快响应
      return () => clearTimeout(timer);
    }
  }, [fileSearchQuery, showFilePicker, loadFiles]);

  // 🔥 检测 @ 输入并实时搜索（保持开启状态）
  const handleInputChange = useCallback((
    e: React.ChangeEvent<HTMLTextAreaElement>,
    onChange: (value: string) => void
  ) => {
    const value = e.target.value;
    const cursorPos = e.target.selectionStart || 0;
    
    onChange(value);
    
    // 检查是否输入了 @
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');
    
    if (lastAtIndex !== -1) {
      const textAfterAt = textBeforeCursor.substring(lastAtIndex + 1);
      
      // 🔥 只要有 @，就保持弹窗开启（除非后面有空格或换行）
      if (!textAfterAt.includes(' ') && !textAfterAt.includes('\n')) {
        console.log('🔥 检测到 @ 输入！textAfterAt:', `"${textAfterAt}"`);
        setFileSearchQuery(textAfterAt);
        
        // 🔥 只在首次打开或关闭状态时计算位置
        if (!showFilePicker) {
          setShowFilePicker(true);
          
          // 🔥 基於輸入框的實際位置
          if (textareaRef.current) {
            const rect = textareaRef.current.getBoundingClientRect();
            const atPosition = {
              x: rect.left, // 輸入框左邊的位置
              y: rect.top   // 輸入框頂部的位置
            };
            
            console.log('📍 輸入框位置:', atPosition);
            setFilePickerPosition(atPosition);
          }
        }
      } else {
        // 只有在输入空格或换行后才关闭
        console.log('🚫 @ 后有空格或换行，关闭弹窗');
        setShowFilePicker(false);
        setFileSearchQuery('');
      }
    } else {
      // 没有 @ 时关闭
      if (showFilePicker) {
        console.log('🚫 没有 @，关闭弹窗');
        setShowFilePicker(false);
        setFileSearchQuery('');
      }
    }
  }, [showFilePicker]);

  // 选中文件
  const selectFile = useCallback((
    file: MentionedFile,
    currentValue: string,
    mentionedFiles: MentionedFile[],
    onValueChange: (value: string) => void,
    onMentionedFilesChange: (files: MentionedFile[]) => void
  ) => {
    // 检查是否已经添加
    if (mentionedFiles.some(f => f.id === file.id)) {
      return;
    }

    // 替换 @ 为文件名标记
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPos = textarea.selectionStart || 0;
    const textBeforeCursor = currentValue.substring(0, cursorPos);
    const textAfterCursor = currentValue.substring(cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex !== -1) {
      const newValue = 
        textBeforeCursor.substring(0, lastAtIndex) + 
        `@${file.filename} ` + 
        textAfterCursor;
      
      onValueChange(newValue);
      onMentionedFilesChange([...mentionedFiles, file]);
      
      setShowFilePicker(false);
      setFileSearchQuery('');
      
      // 重新聚焦并设置光标位置
      setTimeout(() => {
        textarea.focus();
        const newCursorPos = lastAtIndex + file.filename.length + 2;
        textarea.setSelectionRange(newCursorPos, newCursorPos);
      }, 0);
    }
  }, []);

  // 移除文件
  const removeFile = useCallback((
    fileId: string,
    currentValue: string,
    mentionedFiles: MentionedFile[],
    onValueChange: (value: string) => void,
    onMentionedFilesChange: (files: MentionedFile[]) => void
  ) => {
    const file = mentionedFiles.find(f => f.id === fileId);
    if (!file) return;

    // 从输入框中移除文件名标记
    const pattern = new RegExp(`@${file.filename}\\s?`, 'g');
    const newValue = currentValue.replace(pattern, '');
    
    onValueChange(newValue);
    onMentionedFilesChange(mentionedFiles.filter(f => f.id !== fileId));
  }, []);

  // 键盘导航
  const handleKeyDown = useCallback((
    e: React.KeyboardEvent<HTMLTextAreaElement>,
    currentValue: string,
    mentionedFiles: MentionedFile[],
    onValueChange: (value: string) => void,
    onMentionedFilesChange: (files: MentionedFile[]) => void
  ) => {
    if (!showFilePicker || availableFiles.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < availableFiles.length - 1 ? prev + 1 : prev
        );
        break;
      
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : 0);
        break;
      
      case 'Enter':
        if (showFilePicker) {
          e.preventDefault();
          const selectedFile = availableFiles[selectedIndex];
          if (selectedFile) {
            selectFile(
              selectedFile,
              currentValue,
              mentionedFiles,
              onValueChange,
              onMentionedFilesChange
            );
          }
        }
        break;
      
      case 'Escape':
        e.preventDefault();
        setShowFilePicker(false);
        setFileSearchQuery('');
        break;
    }
  }, [showFilePicker, availableFiles, selectedIndex, selectFile]);

  return {
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
    closeFilePicker: () => setShowFilePicker(false),
  };
};
