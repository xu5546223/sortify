/**
 * 移動端智能問答頁面
 * 
 * 功能：
 * - 智能問答（支持流式輸出）
 * - 工作流批准（搜索批准、澄清等）
 * - 對話管理
 * - 實時打字機效果
 */

import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Drawer, message as antdMessage } from 'antd';
import MobileHeader from '../components/MobileHeader';
import MobileWorkflowCard from '../components/MobileWorkflowCard';
import { 
  SendOutlined, 
  PlusOutlined,
  DeleteOutlined,
  LoadingOutlined,
  SearchOutlined,
  MessageOutlined,
  ClockCircleOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import { Streamdown } from 'streamdown';
import { streamQA, StreamQARequest, nonStreamQA } from '../../services/streamQAService';
import conversationService from '../../services/conversationService';
import { apiClient } from '../../services/apiClient';
import type { Conversation } from '../../types/conversation';
import type { SuggestedQuestion } from '../../types/suggestedQuestion';
import suggestedQuestionsService from '../../services/suggestedQuestionsService';
import '../../styles/mobile-qa.css';
import '../../styles/mobile-workflow.css';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  workflowState?: any;
  workflowAction?: string; // 用戶的工作流決策（approve_search, skip_search 等）
  progressSteps?: Array<{ 
    stage: string; 
    message: string; 
    timestamp: Date;
    detail?: any; // 詳細信息
    expanded?: boolean; // 是否展開
  }>;
  metadata?: {
    tokens_used?: number;
    source_documents?: string[];
    processing_time?: number;
  };
}

const MobileAIQA: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  // 狀態管理
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  
  // 對話管理
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [showConversationDrawer, setShowConversationDrawer] = useState(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  
  // 工作流狀態
  const [pendingWorkflow, setPendingWorkflow] = useState<any>(null);
  
  // 文檔預覽
  const [documentInfoCache, setDocumentInfoCache] = useState<Record<string, any>>({});
  const [selectedDocument, setSelectedDocument] = useState<any>(null);
  const [showDocumentDrawer, setShowDocumentDrawer] = useState(false);
  const [loadingDocument, setLoadingDocument] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [pdfPreview, setPdfPreview] = useState<string | null>(null);
  
  // 對話級別的來源文檔
  const [conversationDocuments, setConversationDocuments] = useState<string[]>([]);
  const [showSourceDocsPanel, setShowSourceDocsPanel] = useState(false);
  
  // 建議問題
  const [suggestedQuestions, setSuggestedQuestions] = useState<SuggestedQuestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [generatingQuestions, setGeneratingQuestions] = useState(false);
  
  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streamingMessageIdRef = useRef<string | null>(null);
  const shouldAutoScrollRef = useRef<boolean>(true); // 控制是否自動滾動
  const messageContentRefs = useRef<Map<string, HTMLDivElement>>(new Map()); // 存儲每個消息內容的 ref

  // 自動滾動到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    // 只有在需要自動滾動時才滾動
    if (shouldAutoScrollRef.current) {
      scrollToBottom();
    }
    // 滾動後重置為 true（默認行為）
    shouldAutoScrollRef.current = true;
  }, [messages]);

  // 為 AI 回答中的文檔引用添加點擊事件
  useEffect(() => {
    const handlers = new Map<HTMLDivElement, (e: Event) => void>();

    // 為每個 AI 消息添加文檔引用點擊處理
    messages.forEach(msg => {
      if (msg.role === 'assistant' && !msg.isStreaming) {
        const contentElement = messageContentRefs.current.get(msg.id);
        if (!contentElement) return;

        // 查找所有可能的文檔引用（文件名格式）
        const textNodes = contentElement.querySelectorAll('p, li, td, span');

        textNodes.forEach(node => {
          const text = node.textContent || '';
          // 匹配文件名格式：UUID_filename.ext 或類似的模式
          const fileNameRegex = /([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_[^\s,，。]+\.\w+|[a-z0-9_]+_\d+_[a-z0-9]+\.\w+)/gi;
          const matches = text.match(fileNameRegex);
          
          if (matches && !node.querySelector('.doc-reference-link')) {
            matches.forEach(filename => {
              // 從 conversationDocuments 和 documentInfoCache 中查找對應的文檔 ID
              const docId = conversationDocuments.find(id => {
                const docInfo = documentInfoCache[id];
                return docInfo && (
                  docInfo.filename === filename || 
                  docInfo.original_filename === filename ||
                  docInfo.filename.includes(filename) ||
                  filename.includes(docInfo.filename)
                );
              });

              if (docId) {
                // 將文件名包裝為可點擊的元素
                const innerHTML = node.innerHTML;
                const escapedFilename = filename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const newInnerHTML = innerHTML.replace(
                  new RegExp(escapedFilename, 'g'),
                  `<span class="doc-reference-link" data-doc-id="${docId}" style="color: #1890ff; cursor: pointer; text-decoration: underline;">${filename}</span>`
                );
                if (newInnerHTML !== innerHTML) {
                  node.innerHTML = newInnerHTML;
                }
              }
            });
          }
        });

        // 添加點擊事件監聽器
        const handleDocRefClick = (e: Event) => {
          const target = e.target as HTMLElement;
          if (target.classList.contains('doc-reference-link')) {
            const docId = target.getAttribute('data-doc-id');
            if (docId) {
              handleDocumentClick(docId);
            }
          }
        };

        handlers.set(contentElement, handleDocRefClick);
        contentElement.addEventListener('click', handleDocRefClick);
      }
    });

    // 清理函數：移除所有監聽器
    return () => {
      handlers.forEach((handler, element) => {
        element.removeEventListener('click', handler);
      });
    };
  }, [messages, conversationDocuments, documentInfoCache]);

  // 載入對話列表和建議問題
  useEffect(() => {
    loadConversations();
    loadSuggestedQuestions();
  }, []);

  // 檢查是否從文檔詳情頁面返回，並恢復對話狀態
  useEffect(() => {
    const conversationIdFromState = (location.state as any)?.conversationId;
    if (conversationIdFromState && conversationIdFromState !== currentConversationId) {
      console.log('🔄 從文檔詳情頁面返回，恢復對話:', conversationIdFromState);
      switchConversation(conversationIdFromState);
      // 清除導航狀態，避免重複觸發
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state]);

  const loadConversations = async () => {
    try {
      console.log('📡 API 請求: GET /api/v1/conversations');
      const response = await conversationService.listConversations(0, 50);
      console.log('API: 對話列表獲取成功:', { 
        total: response.total, 
        count: response.conversations.length 
      });
      
      // 顯示前幾個對話的基本信息
      response.conversations.slice(0, 6).forEach((conv, idx) => {
        console.log(`  [${idx}] ${conv.id}: {title: '${conv.title}', cached_documents: Array(${conv.cached_documents?.length || 0}), cached_docs_length: ${conv.cached_documents?.length || 0}}`);
      });
      
      setConversations(response.conversations);
    } catch (error) {
      console.error('❌ 載入對話列表失敗:', error);
      antdMessage.error('載入對話列表失敗');
    }
  };

  // 載入建議問題
  const loadSuggestedQuestions = async () => {
    try {
      setLoadingSuggestions(true);
      console.log('📡 載入建議問題...');
      
      const response = await suggestedQuestionsService.getSuggestedQuestions(4);
      
      console.log(`✅ 成功載入 ${response.questions.length} 個建議問題`);
      setSuggestedQuestions(response.questions);
      
      if (response.questions.length === 0) {
        console.log('💡 提示：尚無建議問題，請先生成問題');
      }
    } catch (error) {
      console.error('❌ 載入建議問題失敗:', error);
      // 失敗時使用空數組，不顯示錯誤提示（非關鍵功能）
      setSuggestedQuestions([]);
    } finally {
      setLoadingSuggestions(false);
    }
  };

  // 生成建議問題
  const handleGenerateQuestions = async () => {
    try {
      setGeneratingQuestions(true);
      antdMessage.loading({ content: '正在生成智能問題...', key: 'generating', duration: 0 });
      
      console.log('🔄 開始生成建議問題...');
      
      const response = await suggestedQuestionsService.generateSuggestedQuestions({
        force_regenerate: false,
        questions_per_category: 5,
        include_cross_category: true
      });
      
      antdMessage.destroy('generating');
      
      if (response.success) {
        antdMessage.success(`成功生成 ${response.total_questions} 個智能問題！`);
        console.log(`✅ 生成成功: ${response.total_questions} 個問題`);
        
        // 重新載入問題
        await loadSuggestedQuestions();
      } else {
        antdMessage.warning(response.message || '問題生成失敗');
        console.warn('⚠️ 生成失敗:', response.message);
      }
    } catch (error: any) {
      antdMessage.destroy('generating');
      
      const errorMsg = error?.response?.data?.detail || '生成建議問題失敗';
      antdMessage.error(errorMsg);
      console.error('❌ 生成建議問題失敗:', error);
      
      // 如果錯誤提示包含"沒有聚類信息"或"文檔數量不足"
      if (errorMsg.includes('聚類') || errorMsg.includes('文檔')) {
        antdMessage.info({
          content: '請先上傳文檔並執行智能分類，才能生成智能問題',
          duration: 5
        });
      }
    } finally {
      setGeneratingQuestions(false);
    }
  };

  // 發送消息
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    // 創建流式接收的消息
    const assistantMessageId = `assistant-${Date.now()}`;
    streamingMessageIdRef.current = assistantMessageId;
    
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    };

    setMessages(prev => [...prev, assistantMessage]);
    setIsStreaming(true);

    // 如果沒有當前對話，先創建
    let conversationId = currentConversationId;
    if (!conversationId) {
      try {
        console.log('API: 創建新對話...', { firstQuestion: userMessage.content });
        console.log('📡 API 請求: POST /api/v1/conversations');
        const newConversation = await conversationService.createConversation(userMessage.content);
        conversationId = newConversation.id;
        setCurrentConversationId(conversationId);
        setConversations(prev => [newConversation, ...prev]);
        console.log('API: 對話創建成功:', { id: conversationId });
      } catch (error) {
        console.error('❌ 創建對話失敗:', error);
      }
    }

    const request: StreamQARequest = {
      question: userMessage.content,
      conversation_id: conversationId || undefined,
    };

    try {
      // 使用流式 API
      await streamQA(request, {
        onChunk: (text: string) => {
          // AI 現在直接輸出 Markdown，Streamdown 會自動處理
          // 直接使用原始 text，無需額外處理
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content + text }
              : msg
          ));
        },
        onComplete: (fullText: string) => {
          // 流式完成
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false }
              : msg
          ));
          setIsStreaming(false);
          setIsLoading(false);
          streamingMessageIdRef.current = null;
        },
        onApprovalNeeded: (workflowState: any) => {
          // 需要用戶批准
          console.log('🔔 收到批准請求:', workflowState);
          console.log('📝 當前 assistantMessageId:', assistantMessageId);
          
          setPendingWorkflow({
            messageId: assistantMessageId,
            state: workflowState,
            originalQuestion: userMessage.content
          });
          setIsStreaming(false);
          setIsLoading(false);
          
          // 更新消息以顯示批准請求（保留 progressSteps）
          setMessages(prev => {
            const updated = prev.map(msg => 
              msg.id === assistantMessageId
                ? { ...msg, workflowState, isStreaming: false }
                : msg
            );
            console.log('✅ 更新後的消息列表:', updated);
            return updated;
          });
        },
        onProgress: (stage: string, message: string, detail?: any) => {
          // 累積進度步驟
          console.log('📊 收到進度更新:', stage, message, detail);
          setMessages(prev => prev.map(msg => {
            if (msg.id === assistantMessageId) {
              const currentSteps = msg.progressSteps || [];
              return {
                ...msg,
                progressSteps: [...currentSteps, { 
                  stage, 
                  message, 
                  timestamp: new Date(),
                  detail,
                  expanded: false // 默認不展開
                }]
              };
            }
            return msg;
          }));
        },
        onMetadata: (metadata) => {
          // 接收元數據
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, metadata }
              : msg
          ));
          
          // 更新對話級別的來源文檔
          if (metadata?.source_documents && Array.isArray(metadata.source_documents)) {
            setConversationDocuments(prev => {
              // 合併新的文檔 ID，去重
              const newDocs = metadata.source_documents!.filter((docId: string) => !prev.includes(docId));
              if (newDocs.length > 0) {
                console.log('📄 新增來源文檔:', newDocs);
                // 載入新文檔的信息
                loadDocumentInfo(newDocs);
                return [...prev, ...newDocs];
              }
              return prev;
            });
          }
        },
        onError: (error: string) => {
          console.error('流式問答失敗:', error);
          antdMessage.error(`問答失敗: ${error}`);
          
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, content: `抱歉，發生錯誤: ${error}`, isStreaming: false }
              : msg
          ));
          
          setIsStreaming(false);
          setIsLoading(false);
        }
      });
    } catch (error) {
      console.error('問答失敗:', error);
      antdMessage.error('問答失敗，請重試');
      
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMessageId
          ? { ...msg, content: '抱歉，處理您的問題時發生錯誤。', isStreaming: false }
          : msg
      ));
      
      setIsStreaming(false);
      setIsLoading(false);
    }
  };

  // 處理快速選擇填入主輸入框
  const handleFillMainInput = (text: string) => {
    setInputValue(text);
    // 自動聚焦到輸入框
    textareaRef.current?.focus();
  };

  // 處理展開/折疊進度步驟詳情
  const toggleProgressDetail = (messageId: string, stepIndex: number) => {
    // 展開/折疊時不自動滾動到底部
    shouldAutoScrollRef.current = false;
    
    setMessages(prev => prev.map(msg => {
      if (msg.id === messageId && msg.progressSteps) {
        const updatedSteps = [...msg.progressSteps];
        updatedSteps[stepIndex] = {
          ...updatedSteps[stepIndex],
          expanded: !updatedSteps[stepIndex].expanded
        };
        return { ...msg, progressSteps: updatedSteps };
      }
      return msg;
    }));
  };

  // 加載文檔信息（用於顯示文件名和預覽）
  const loadDocumentInfo = async (documentIds: string[]) => {
    try {
      const newDocInfo: Record<string, any> = {};
      
      for (const docId of documentIds) {
        // 檢查緩存
        if (documentInfoCache[docId]) {
          continue;
        }
        
        try {
          const response = await apiClient.get(`/documents/${docId}`);
          newDocInfo[docId] = response.data;
        } catch (error) {
          console.error(`獲取文檔 ${docId} 信息失敗:`, error);
          newDocInfo[docId] = { 
            id: docId,
            filename: '未知文檔',
            status: 'unknown'
          };
        }
      }
      
      if (Object.keys(newDocInfo).length > 0) {
        setDocumentInfoCache(prev => ({ ...prev, ...newDocInfo }));
      }
    } catch (error) {
      console.error('加載文檔信息失敗:', error);
    }
  };

  // 處理文檔點擊 - 打開預覽抽屜
  const handleDocumentClick = async (documentId: string) => {
    setLoadingDocument(true);
    setShowDocumentDrawer(true);
    setImagePreview(null);
    setPdfPreview(null);
    
    try {
      // 從緩存或重新加載
      let docData = documentInfoCache[documentId];
      
      if (!docData || !docData.analysis) {
        const response = await apiClient.get(`/documents/${documentId}`);
        docData = response.data;
        setDocumentInfoCache(prev => ({ ...prev, [documentId]: docData }));
      }
      
      setSelectedDocument(docData);
      
      // 如果是圖片，加載預覽
      if (isImageFile(docData.file_type)) {
        try {
          const imageResponse = await apiClient.get(`/documents/${documentId}/file`, {
            responseType: 'blob'
          });
          const blobUrl = URL.createObjectURL(imageResponse.data);
          setImagePreview(blobUrl);
          console.log('✅ 圖片預覽加載成功');
        } catch (err) {
          console.error('❌ 加載圖片預覽失敗:', err);
        }
      }
      
      // 如果是 PDF，加載預覽（第一頁）
      if (isPdfFile(docData.file_type)) {
        try {
          const pdfResponse = await apiClient.get(`/documents/${documentId}/file`, {
            responseType: 'blob'
          });
          const blobUrl = URL.createObjectURL(pdfResponse.data);
          setPdfPreview(blobUrl);
          console.log('✅ PDF 預覽加載成功');
        } catch (err) {
          console.error('❌ 加載 PDF 預覽失敗:', err);
        }
      }
    } catch (error) {
      console.error('加載文檔詳情失敗:', error);
      antdMessage.error('無法加載文檔詳情');
      setShowDocumentDrawer(false);
    } finally {
      setLoadingDocument(false);
    }
  };

  // 判斷是否為圖片文件
  const isImageFile = (fileType: string | null | undefined): boolean => {
    if (!fileType) return false;
    return fileType.startsWith('image/');
  };

  // 判斷是否為 PDF 文件
  const isPdfFile = (fileType: string | null | undefined): boolean => {
    if (!fileType) return false;
    return fileType === 'application/pdf';
  };

  // 關閉文檔預覽
  const closeDocumentDrawer = () => {
    setShowDocumentDrawer(false);
    setSelectedDocument(null);
    
    // 清理 blob URLs
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
      setImagePreview(null);
    }
    if (pdfPreview) {
      URL.revokeObjectURL(pdfPreview);
      setPdfPreview(null);
    }
  };

  // 打開完整文檔詳情
  const openFullDocumentDetail = () => {
    if (selectedDocument) {
      // 傳遞當前對話 ID 作為狀態，以便返回時能恢復對話
      navigate(`/mobile/documents/${selectedDocument.id}`, {
        state: { 
          fromConversation: currentConversationId,
          returnPath: '/mobile/qa'
        }
      });
    }
  };

  // 處理澄清問題提交（從主輸入框提交）
  const handleClarificationSubmit = async () => {
    if (!pendingWorkflow || !inputValue.trim()) return;

    const clarificationText = inputValue.trim();
    
    // 添加用戶的澄清回答
    const clarificationMessage: Message = {
      id: `user-clarification-${Date.now()}`,
      role: 'user',
      content: clarificationText,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, clarificationMessage]);
    setInputValue('');
    
    // 清除工作流狀態
    setPendingWorkflow(null);
    setIsLoading(true);
    
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    };

    setMessages(prev => [...prev, assistantMessage]);
    setIsStreaming(true);

    const request: StreamQARequest = {
      question: pendingWorkflow.originalQuestion,
      conversation_id: currentConversationId || undefined,
      workflow_action: 'provide_clarification',
      clarification_text: clarificationText
    };

    try {
      await streamQA(request, {
        onChunk: (text: string) => {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content + text }
              : msg
          ));
        },
        onComplete: (fullText: string) => {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false }
              : msg
          ));
          setIsStreaming(false);
          setIsLoading(false);
        },
        onApprovalNeeded: (workflowState: any) => {
          // 可能在提交澄清後還需要其他批准（如搜索批准）
          console.log('🔔 [澄清後] 收到批准請求:', workflowState);
          console.log('📝 [澄清後] 當前 assistantMessageId:', assistantMessageId);
          
          setPendingWorkflow({
            messageId: assistantMessageId,
            state: workflowState,
            originalQuestion: pendingWorkflow.originalQuestion
          });
          setIsStreaming(false);
          setIsLoading(false);
          
          // 更新消息以顯示批准請求（保留 progressSteps）
          setMessages(prev => {
            const updated = prev.map(msg => 
              msg.id === assistantMessageId
                ? { ...msg, workflowState, isStreaming: false }
                : msg
            );
            console.log('✅ [澄清後] 更新後的消息列表:', updated);
            return updated;
          });
        },
        onProgress: (stage: string, message: string, detail?: any) => {
          console.log('📊 [澄清後] 收到進度更新:', stage, message, detail);
          setMessages(prev => prev.map(msg => {
            if (msg.id === assistantMessageId) {
              const currentSteps = msg.progressSteps || [];
              return {
                ...msg,
                progressSteps: [...currentSteps, { 
                  stage, 
                  message, 
                  timestamp: new Date(),
                  detail,
                  expanded: false
                }]
              };
            }
            return msg;
          }));
        },
        onMetadata: (metadata) => {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, metadata }
              : msg
          ));
          
          // 更新對話級別的來源文檔
          if (metadata?.source_documents && Array.isArray(metadata.source_documents)) {
            setConversationDocuments(prev => {
              // 合併新的文檔 ID，去重
              const newDocs = metadata.source_documents!.filter((docId: string) => !prev.includes(docId));
              if (newDocs.length > 0) {
                console.log('📄 [澄清後] 新增來源文檔:', newDocs);
                // 載入新文檔的信息
                loadDocumentInfo(newDocs);
                return [...prev, ...newDocs];
              }
              return prev;
            });
          }
        },
        onError: (error: string) => {
          console.error('提交澄清失敗:', error);
          antdMessage.error(`提交失敗: ${error}`);
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, content: `抱歉，發生錯誤: ${error}`, isStreaming: false }
              : msg
          ));
          setIsStreaming(false);
          setIsLoading(false);
        }
      });
    } catch (error) {
      console.error('提交澄清失敗:', error);
      antdMessage.error('提交失敗，請重試');
      setIsStreaming(false);
      setIsLoading(false);
    }
  };

  // 處理工作流批准
  const handleApprove = async (action: 'approve_search' | 'skip_search' | 'approve_detail_query' | 'skip_detail_query') => {
    if (!pendingWorkflow) return;

    // 記錄用戶的決策到當前消息
    setMessages(prev => prev.map(msg => 
      msg.id === pendingWorkflow.messageId
        ? { ...msg, workflowAction: action }
        : msg
    ));

    // 清除工作流狀態
    setPendingWorkflow(null);
    setIsLoading(true);
    const assistantMessageId = `assistant-${Date.now()}`;
    
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    };

    setMessages(prev => [...prev, assistantMessage]);
    setIsStreaming(true);

    const request: StreamQARequest = {
      question: pendingWorkflow.originalQuestion,
      conversation_id: currentConversationId || undefined,
      workflow_action: action
    };

    try {
      await streamQA(request, {
        onChunk: (text: string) => {
          // AI 直接輸出 Markdown，無需處理
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content + text }
              : msg
          ));
        },
        onComplete: () => {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false }
              : msg
          ));
          setIsStreaming(false);
          setIsLoading(false);
          setPendingWorkflow(null);
        },
        onApprovalNeeded: (workflowState: any) => {
          // 可能在批准後還需要其他批准（如批准搜索後又需要詳細查詢批准）
          console.log('🔔 [批准後] 收到新的批准請求:', workflowState);
          console.log('📝 [批准後] 當前 assistantMessageId:', assistantMessageId);
          
          setPendingWorkflow({
            messageId: assistantMessageId,
            state: workflowState,
            originalQuestion: pendingWorkflow.originalQuestion
          });
          setIsStreaming(false);
          setIsLoading(false);
          
          // 更新消息以顯示批准請求（保留 progressSteps）
          setMessages(prev => {
            const updated = prev.map(msg => 
              msg.id === assistantMessageId
                ? { ...msg, workflowState, isStreaming: false }
                : msg
            );
            console.log('✅ [批准後] 更新後的消息列表:', updated);
            return updated;
          });
        },
        onProgress: (stage: string, message: string, detail?: any) => {
          console.log('📊 [批准後] 收到進度更新:', stage, message, detail);
          setMessages(prev => prev.map(msg => {
            if (msg.id === assistantMessageId) {
              const currentSteps = msg.progressSteps || [];
              return {
                ...msg,
                progressSteps: [...currentSteps, { 
                  stage, 
                  message, 
                  timestamp: new Date(),
                  detail,
                  expanded: false
                }]
              };
            }
            return msg;
          }));
        },
        onMetadata: (metadata) => {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId
              ? { ...msg, metadata }
              : msg
          ));
          
          // 更新對話級別的來源文檔
          if (metadata?.source_documents && Array.isArray(metadata.source_documents)) {
            setConversationDocuments(prev => {
              // 合併新的文檔 ID，去重
              const newDocs = metadata.source_documents!.filter((docId: string) => !prev.includes(docId));
              if (newDocs.length > 0) {
                console.log('📄 [批准後] 新增來源文檔:', newDocs);
                // 載入新文檔的信息
                loadDocumentInfo(newDocs);
                return [...prev, ...newDocs];
              }
              return prev;
            });
          }
        },
        onError: (error: string) => {
          antdMessage.error(`處理失敗: ${error}`);
          setIsStreaming(false);
          setIsLoading(false);
          setPendingWorkflow(null);
        }
      });
    } catch (error) {
      console.error('處理批准失敗:', error);
      setIsStreaming(false);
      setIsLoading(false);
    }
  };

  // 新建對話
  const startNewConversation = () => {
    setCurrentConversationId(null);
    setMessages([]);
    setPendingWorkflow(null);
    setConversationDocuments([]);
    setShowSourceDocsPanel(false);
    setShowConversationDrawer(false);
    antdMessage.success('開始新對話');
  };

  // 切換對話
  const switchConversation = async (conversationId: string) => {
    try {
      setCurrentConversationId(conversationId);
      setMessages([]);
      setPendingWorkflow(null);
      
      const conversationDetail = await conversationService.getConversation(conversationId);
      
      console.log('📥 載入對話詳情:', {
        id: conversationDetail.id,
        title: conversationDetail.title,
        messageCount: conversationDetail.messages.length,
        cachedDocuments: conversationDetail.cached_documents?.length || 0
      });
      
      // 設置對話的來源文檔列表
      const cachedDocs = conversationDetail.cached_documents || [];
      setConversationDocuments(cachedDocs);
      
      // 批量加載文檔信息（避免重複請求）
      if (cachedDocs.length > 0) {
        loadDocumentInfo(cachedDocs);
      }
      
      const loadedMessages: Message[] = [];
      
      // 確保消息是成對的（用戶問題 + AI 回答）
      for (let i = 0; i < conversationDetail.messages.length; i += 2) {
        const userMsg = conversationDetail.messages[i];
        const assistantMsg = conversationDetail.messages[i + 1];
        
        // 只有當用戶消息和助手消息都存在時才添加
        if (userMsg && assistantMsg && userMsg.role === 'user' && assistantMsg.role === 'assistant') {
          // AI 現在直接輸出 Markdown，內容已是正確格式，無需處理
          loadedMessages.push({
            id: `user-${i}`,
            role: 'user',
            content: userMsg.content,
            timestamp: new Date(userMsg.timestamp)
          });
          
          loadedMessages.push({
            id: `assistant-${i}`,
            role: 'assistant',
            content: assistantMsg.content,
            timestamp: new Date(assistantMsg.timestamp),
            metadata: {
              tokens_used: assistantMsg.tokens_used || 0
            }
          });
        }
      }
      
      setMessages(loadedMessages);
      setShowConversationDrawer(false);
      
      console.log('✅ 成功載入', loadedMessages.length, '條消息');
      antdMessage.success(`已載入對話 (${loadedMessages.length / 2} 個問答)`);
    } catch (error) {
      console.error('❌ 切換對話失敗:', error);
      antdMessage.error('切換對話失敗');
    }
  };

  // 刪除對話
  const deleteConversation = async (conversationId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    
    try {
      await conversationService.deleteConversation(conversationId);
      await loadConversations();
      
      if (conversationId === currentConversationId) {
        setCurrentConversationId(null);
        setMessages([]);
      }
      
      antdMessage.success('對話已刪除');
    } catch (error) {
      console.error('刪除對話失敗:', error);
      antdMessage.error('刪除對話失敗');
    }
  };

  // 處理建議問題點擊
  const handleQuestionClick = async (question: SuggestedQuestion) => {
    // 設置輸入框內容
    setInputValue(question.question);
    
    // 標記問題已使用（異步，不阻塞用戶操作）
    suggestedQuestionsService.markQuestionUsed(question.id).catch(err => {
      console.warn('標記問題使用失敗（非關鍵錯誤）:', err);
    });
  };

  // 過濾對話列表
  const filteredConversations = conversations.filter(conv => 
    conv.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // 按時間分組對話
  const groupedConversations = () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(today);
    lastWeek.setDate(lastWeek.getDate() - 7);

    const groups: { label: string; conversations: Conversation[] }[] = [
      { label: '今天', conversations: [] },
      { label: '昨天', conversations: [] },
      { label: '最近 7 天', conversations: [] },
      { label: '更早', conversations: [] },
    ];

    filteredConversations.forEach(conv => {
      const convDate = new Date(conv.updated_at);
      
      if (convDate.toDateString() === today.toDateString()) {
        groups[0].conversations.push(conv);
      } else if (convDate.toDateString() === yesterday.toDateString()) {
        groups[1].conversations.push(conv);
      } else if (convDate > lastWeek) {
        groups[2].conversations.push(conv);
      } else {
        groups[3].conversations.push(conv);
      }
    });

    return groups.filter(group => group.conversations.length > 0);
  };

  // 處理從問題銀行傳來的預填問題
  useEffect(() => {
    const state = location.state as { prefilledQuestion?: string; fromQuestionBank?: boolean };
    if (state?.prefilledQuestion && state?.fromQuestionBank) {
      // 設置輸入框的值為預填問題
      setInputValue(state.prefilledQuestion);
      
      // 清除 location state 以避免重複填充
      window.history.replaceState({}, document.title);
      
      // 如果當前沒有正在進行的對話，自動聚焦到輸入框
      if (textareaRef.current && messages.length === 0) {
        setTimeout(() => {
          textareaRef.current?.focus();
        }, 300);
      }
    }
  }, [location.state]);

  // 從文檔詳情頁返回時恢復對話
  useEffect(() => {
    const state = location.state as { conversationId?: string };
    if (state?.conversationId && state.conversationId !== currentConversationId) {
      console.log('🔄 從文檔詳情返回，恢復對話:', state.conversationId);
      switchConversation(state.conversationId);
      
      // 清除 state
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  // 初始化：載入對話列表和建議問題
  useEffect(() => {
    loadConversations();
    loadSuggestedQuestions();
  }, []);

  // 自動滾動到底部
  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      scrollToBottom();
    }
  }, [messages]);

  // 為 AI 回答中的文檔引用添加點擊事件
  useEffect(() => {
    messages.forEach((msg) => {
      if (msg.role === 'assistant' && msg.metadata?.source_documents) {
        const contentElement = messageContentRefs.current.get(msg.id);
        if (contentElement) {
          // 查找所有的文檔文件名
          const sourceDocIds = msg.metadata.source_documents;
          
          // 獲取所有文檔信息
          sourceDocIds.forEach(docId => {
            const docInfo = documentInfoCache[docId];
            if (docInfo && docInfo.filename) {
              // 查找內容中的文件名
              const filename = docInfo.filename;
              const filenamePattern = new RegExp(filename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
              
              // 找到所有匹配的文字節點
              const walker = document.createTreeWalker(
                contentElement,
                NodeFilter.SHOW_TEXT,
                null
              );
              
              const textNodes: Text[] = [];
              let node;
              while ((node = walker.nextNode())) {
                if (node.textContent && filenamePattern.test(node.textContent)) {
                  textNodes.push(node as Text);
                }
              }
              
              // 為每個匹配的文字節點添加點擊處理
              textNodes.forEach((textNode) => {
                const parent = textNode.parentNode as HTMLElement;
                if (parent && !parent.classList.contains('doc-reference-link')) {
                  const span = document.createElement('span');
                  span.className = 'doc-reference-link';
                  span.textContent = filename;
                  span.onclick = () => handleDocumentClick(docId);
                  
                  textNode.replaceWith(span);
                }
              });
            }
          });
        }
      }
    });
  }, [messages, documentInfoCache]);

  return (
    <>
      <MobileHeader 
        title="智能問答" 
        showMenu={true}
        onMenuClick={() => setShowConversationDrawer(true)}
      />
      
      <div className="mobile-qa-container">
        {/* 消息列表 */}
        <div className="mobile-qa-messages">
          {messages.length === 0 ? (
            <div className="mobile-empty" style={{ marginTop: '48px' }}>
              <div className="mobile-empty-icon">💬</div>
              <div className="mobile-empty-text">開始對話</div>
              <div className="mobile-empty-subtext">向 AI 提問關於您文件的問題</div>
              
              <div style={{ marginTop: '24px', width: '100%' }}>
                <p style={{ fontSize: '14px', color: '#666', marginBottom: '12px', textAlign: 'center' }}>
                  {loadingSuggestions ? '載入中...' : '💡 智能建議問題：'}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {suggestedQuestions.length > 0 ? (
                    suggestedQuestions.map((question) => (
                      <button
                        key={question.id}
                        onClick={() => handleQuestionClick(question)}
                        className="mobile-quick-question-btn"
                        disabled={loadingSuggestions}
                      >
                        {question.category && !question.is_cross_category && (
                          <span style={{
                            fontSize: '11px',
                            color: '#1890ff',
                            marginRight: '6px',
                            background: '#e6f7ff',
                            padding: '2px 6px',
                            borderRadius: '4px'
                          }}>
                            {question.category}
                          </span>
                        )}
                        {question.question}
                      </button>
                    ))
                  ) : (
                    <div style={{
                      textAlign: 'center',
                      padding: '16px',
                      color: '#8c8c8c',
                      fontSize: '13px'
                    }}>
                      {!loadingSuggestions && (
                        <>
                          尚無智能問題<br/>
                          <span style={{ fontSize: '12px' }}>
                            請先上傳文檔並執行智能分類
                          </span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <React.Fragment key={msg.id}>
                  {/* 用戶消息 - 獨立容器 */}
                  {msg.role === 'user' && (
                    <div className="mobile-qa-message-wrapper mobile-qa-user-wrapper">
                      <div className="mobile-qa-message user">
                        <div className="mobile-qa-bubble user-bubble">
                          {msg.content}
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* AI 消息 - 獨立容器 */}
                  {msg.role === 'assistant' && (
                    <div className="mobile-qa-message-wrapper mobile-qa-assistant-wrapper">
                      <div className="mobile-qa-message assistant">
                        <div className="assistant-content">
                          {/* AI 圖標 */}
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: '8px', 
                            marginBottom: '8px',
                            color: '#8c8c8c',
                            fontSize: '13px'
                          }}>
                            <span style={{ 
                              fontSize: '18px',
                              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                              WebkitBackgroundClip: 'text',
                              WebkitTextFillColor: 'transparent'
                            }}>🤖</span>
                            <span>AI 助手</span>
                          </div>
                          
                          {/* AI 回答內容 - 使用 Streamdown 渲染 Markdown */}
                          <div style={{ paddingLeft: '26px' }}>
                            {/* 進度時間線 */}
                            {msg.progressSteps && msg.progressSteps.length > 0 && (
                              <div style={{ marginTop: '12px', marginBottom: '12px' }}>
                                {msg.progressSteps.map((step, idx) => (
                                  <div key={idx} style={{ 
                                    marginBottom: '8px',
                                    animation: 'fade-in 0.3s ease-out'
                                  }}>
                                    <div 
                                      style={{
                                        display: 'flex', 
                                        alignItems: 'flex-start',
                                        fontSize: '13px',
                                        color: '#595959',
                                        cursor: step.detail ? 'pointer' : 'default'
                                      }}
                                      onClick={() => {
                                        if (step.detail) {
                                          toggleProgressDetail(msg.id, idx);
                                        }
                                      }}
                                    >
                                      <span style={{ marginRight: '6px', fontSize: '16px', flexShrink: 0 }}>
                                        {idx === (msg.progressSteps?.length ?? 0) - 1 && msg.isStreaming ? '⏳' : '✓'}
                                      </span>
                                      <span style={{ flex: 1 }}>{step.message}</span>
                                      {step.detail && (
                                        <span style={{ marginLeft: '4px', fontSize: '12px', color: '#1890ff' }}>
                                          {step.expanded ? '▼' : '▶'}
                                        </span>
                                      )}
                                    </div>
                                    
                                    {/* 詳細信息展開區域 */}
                                    {step.detail && step.expanded && (
                                      <div style={{
                                        marginTop: '8px',
                                        marginLeft: '22px',
                                        padding: '12px',
                                        background: '#f5f5f5',
                                        borderRadius: '6px',
                                        borderLeft: '3px solid #1890ff',
                                        fontSize: '12px',
                                        color: '#262626',
                                        lineHeight: '1.6'
                                      }}>
                                        {/* 推理內容 */}
                                        {typeof step.detail === 'string' && (
                                          <div style={{ whiteSpace: 'pre-wrap' }}>{step.detail}</div>
                                        )}
                                        
                                        {/* 查詢重寫 */}
                                        {step.detail.queries && (
                                          <div>
                                            <div style={{ fontWeight: 600, marginBottom: '8px', color: '#1890ff' }}>
                                              生成了 {step.detail.count} 個優化查詢：
                                            </div>
                                            {step.detail.queries.map((q: string, qIdx: number) => (
                                              <div key={qIdx} style={{ 
                                                marginBottom: '6px',
                                                paddingLeft: '12px',
                                                borderLeft: '2px solid #d9d9d9'
                                              }}>
                                                {qIdx + 1}. {q}
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                            
                            {msg.isStreaming && <span className="typing-cursor">▊</span>}
                            {msg.content ? (
                              <div ref={(el) => {
                                if (el) {
                                  messageContentRefs.current.set(msg.id, el);
                                } else {
                                  messageContentRefs.current.delete(msg.id);
                                }
                              }}>
                                <Streamdown 
                                  isAnimating={msg.isStreaming}
                                  parseIncompleteMarkdown={msg.isStreaming}
                                >
                                  {msg.content}
                                </Streamdown>
                              </div>
                            ) : (
                              msg.isStreaming && (!msg.progressSteps || msg.progressSteps.length === 0) ? '正在思考...' : ''
                            )}
                            
                            {/* 工作流批准UI */}
                            {msg.workflowState && (() => {
                              // 如果是當前 pending 的工作流，顯示交互式卡片
                              if (pendingWorkflow && pendingWorkflow.messageId === msg.id) {
                                console.log('🎨 渲染工作流卡片:', { 
                                  messageId: msg.id, 
                                  current_step: msg.workflowState.current_step,
                                  workflowState: msg.workflowState 
                                });
                                return (
                                  <>
                                  {msg.workflowState.current_step === 'need_clarification' && (
                                    <MobileWorkflowCard
                                      type="clarification"
                                      clarificationQuestion={msg.workflowState.clarification_question}
                                      suggestedResponses={msg.workflowState.suggested_responses}
                                      onFillMainInput={handleFillMainInput}
                                    />
                                  )}
                                    {msg.workflowState.current_step === 'awaiting_search_approval' && (
                                      <MobileWorkflowCard
                                        type="search_approval"
                                        searchPreview={msg.workflowState.search_preview}
                                        onApproveSearch={() => handleApprove('approve_search')}
                                        onSkipSearch={() => handleApprove('skip_search')}
                                        isLoading={isLoading}
                                      />
                                    )}
                                    {msg.workflowState.current_step === 'awaiting_detail_query_approval' && (
                                      <MobileWorkflowCard
                                        type="detail_query_approval"
                                        documentNames={msg.workflowState.document_names}
                                        queryType={msg.workflowState.query_type}
                                        onApproveDetailQuery={() => handleApprove('approve_detail_query')}
                                        onSkipDetailQuery={() => handleApprove('skip_detail_query')}
                                        isLoading={isLoading}
                                      />
                                    )}
                                  </>
                                );
                              }
                              
                              // 如果已處理，顯示決策記錄
                              if (msg.workflowAction) {
                                const actionLabels = {
                                  'approve_search': '✅ 已批准文檔搜索',
                                  'skip_search': '⏭️ 已跳過文檔搜索',
                                  'approve_detail_query': '✅ 已批准詳細查詢',
                                  'skip_detail_query': '⏭️ 已跳過詳細查詢'
                                };
                                return (
                                  <div style={{
                                    marginTop: '12px',
                                    padding: '10px 14px',
                                    background: '#f0f7ff',
                                    border: '1px solid #d9e8ff',
                                    borderRadius: '8px',
                                    fontSize: '13px',
                                    color: '#0066cc',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px'
                                  }}>
                                    {actionLabels[msg.workflowAction as keyof typeof actionLabels] || msg.workflowAction}
                                  </div>
                                );
                              }
                              
                              return null;
                            })()}
                            
                            {/* 元數據 */}
                            {msg.metadata && (
                              <div className="message-metadata" style={{ marginTop: '12px' }}>
                                {msg.metadata.tokens_used && (
                                  <span className="metadata-item">🔢 {msg.metadata.tokens_used} tokens</span>
                                )}
                                {msg.metadata.processing_time && (
                                  <span className="metadata-item">⏱️ {msg.metadata.processing_time.toFixed(2)}s</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </React.Fragment>
              ))}
              {isLoading && !isStreaming && (
                <div className="mobile-qa-message-wrapper mobile-qa-assistant-wrapper">
                  <div className="mobile-qa-message assistant">
                    <div className="assistant-content">
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          color: '#8c8c8c',
                          fontSize: '13px'
                        }}
                      >
                        <span
                          style={{
                            fontSize: '18px',
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent'
                          }}
                        >
                          🤖
                        </span>
                        <span>AI 助手</span>
                      </div>
                      <div style={{ paddingLeft: '26px', marginTop: '8px', color: '#8c8c8c' }}>
                        <LoadingOutlined /> 正在連接...
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* 來源文檔折疊面板 - 在輸入框上方 */}
        {conversationDocuments.length > 0 && (
          <div style={{
            borderTop: '1px solid #e8e8e8',
            background: '#fff',
            padding: '0'
          }}>
            {/* 折疊按鈕 */}
            <div 
              onClick={() => setShowSourceDocsPanel(!showSourceDocsPanel)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 16px',
                cursor: 'pointer',
                background: showSourceDocsPanel ? '#f5f5f5' : '#fff',
                transition: 'all 0.2s'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileTextOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
                <span style={{ fontSize: '14px', fontWeight: 500, color: '#262626' }}>
                  來源文檔 ({conversationDocuments.length})
                </span>
              </div>
              <span style={{ fontSize: '12px', color: '#8c8c8c' }}>
                {showSourceDocsPanel ? '▼' : '▲'}
              </span>
            </div>
            
            {/* 展開的文檔列表 */}
            {showSourceDocsPanel && (
              <div style={{
                maxHeight: '200px',
                overflowY: 'auto',
                padding: '8px 16px 12px',
                background: '#fafafa'
              }}>
                {conversationDocuments.map((docId, idx) => {
                  const docInfo = documentInfoCache[docId];
                  
                  return (
                    <div
                      key={docId}
                      onClick={() => handleDocumentClick(docId)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '10px 12px',
                        marginBottom: idx < conversationDocuments.length - 1 ? '6px' : '0',
                        background: '#fff',
                        border: '1px solid #e0e0e0',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        fontSize: '13px'
                      }}
                      onTouchStart={(e) => {
                        e.currentTarget.style.background = '#e6f7ff';
                        e.currentTarget.style.borderColor = '#1890ff';
                      }}
                      onTouchEnd={(e) => {
                        e.currentTarget.style.background = '#fff';
                        e.currentTarget.style.borderColor = '#e0e0e0';
                      }}
                    >
                      <FileTextOutlined style={{ fontSize: '18px', color: '#1890ff', flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ 
                          color: '#262626', 
                          overflow: 'hidden', 
                          textOverflow: 'ellipsis', 
                          whiteSpace: 'nowrap',
                          marginBottom: '2px'
                        }}>
                          {docInfo ? docInfo.filename : `加載中...`}
                        </div>
                        {docInfo?.file_type && (
                          <div style={{ fontSize: '11px', color: '#8c8c8c' }}>
                            {docInfo.file_type}
                          </div>
                        )}
                      </div>
                      <span style={{ fontSize: '18px', color: '#8c8c8c', flexShrink: 0 }}>›</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* 輸入框 */}
        <div className="mobile-qa-input-wrapper">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                // 判斷當前是否在等待澄清回答
                if (pendingWorkflow?.state?.current_step === 'need_clarification') {
                  handleClarificationSubmit();
                } else {
                  handleSend();
                }
              }
            }}
            placeholder={
              pendingWorkflow?.state?.current_step === 'need_clarification' 
                ? "輸入您的回答..."
                : "輸入您的問題..."
            }
            className="mobile-qa-input"
            disabled={isLoading}
            rows={1}
          />
          <button
            onClick={() => {
              // 判斷當前是否在等待澄清回答
              if (pendingWorkflow?.state?.current_step === 'need_clarification') {
                handleClarificationSubmit();
              } else {
                handleSend();
              }
            }}
            disabled={!inputValue.trim() || isLoading}
            className="mobile-qa-send-btn"
          >
            <SendOutlined />
          </button>
        </div>
      </div>

      {/* 對話列表抽屜 */}
      <Drawer
        title="對話歷史"
        placement="left"
        onClose={() => {
          setShowConversationDrawer(false);
          setSearchQuery('');
        }}
        open={showConversationDrawer}
        width="85%"
        className="mobile-conversation-drawer"
      >
        {/* 頂部操作區 */}
        <div className="drawer-header-actions">
          <button 
            className="drawer-new-btn"
            onClick={startNewConversation}
          >
            <PlusOutlined /> 新對話
          </button>
        </div>

        {/* 搜索框 */}
        <div className="drawer-search">
          <div style={{ position: 'relative' }}>
            <SearchOutlined 
              style={{ 
                position: 'absolute', 
                left: '12px', 
                top: '50%', 
                transform: 'translateY(-50%)',
                color: '#8c8c8c',
                fontSize: '14px'
              }} 
            />
            <input
              type="text"
              placeholder="搜索對話..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="drawer-search-input"
              style={{ paddingLeft: '36px' }}
            />
          </div>
        </div>

        {/* 對話列表 */}
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <div className="mobile-empty">
              <div className="mobile-empty-icon">📝</div>
              <div className="mobile-empty-text">暫無對話</div>
              <div className="mobile-empty-subtext">開始您的第一個對話</div>
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="mobile-empty">
              <div className="mobile-empty-icon">🔍</div>
              <div className="mobile-empty-text">找不到對話</div>
              <div className="mobile-empty-subtext">試試其他關鍵字</div>
            </div>
          ) : (
            groupedConversations().map((group, groupIndex) => (
              <div key={groupIndex}>
                <div className="conversation-category">{group.label}</div>
                {group.conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''}`}
                    onClick={() => switchConversation(conv.id)}
                  >
                    <div className="conversation-title">{conv.title}</div>
                    <div className="conversation-meta">
                      <div className="conversation-meta-item">
                        <MessageOutlined style={{ fontSize: '11px' }} />
                        <span className="conversation-meta-badge">{conv.message_count} 條</span>
                      </div>
                      {conv.cached_documents && conv.cached_documents.length > 0 && (
                        <div className="conversation-meta-item">
                          <span className="conversation-meta-badge">
                            📄 {conv.cached_documents.length} 文件
                          </span>
                        </div>
                      )}
                      <div className="conversation-meta-item">
                        <ClockCircleOutlined style={{ fontSize: '11px' }} />
                        <span>{new Date(conv.updated_at).toLocaleDateString('zh-TW', { 
                          month: 'numeric', 
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}</span>
                      </div>
                    </div>
                    <button
                      className="conversation-delete-btn"
                      onClick={(e) => deleteConversation(conv.id, e)}
                    >
                      <DeleteOutlined />
                    </button>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </Drawer>

      {/* 文檔預覽 Drawer */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FileTextOutlined style={{ color: '#1890ff' }} />
            <span>文檔預覽</span>
          </div>
        }
        placement="bottom"
        onClose={closeDocumentDrawer}
        open={showDocumentDrawer}
        height="85vh"
        styles={{ body: { padding: '16px' } }}
      >
        {loadingDocument ? (
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            height: '200px' 
          }}>
            <LoadingOutlined style={{ fontSize: '32px', color: '#1890ff' }} />
          </div>
        ) : selectedDocument ? (
          <div style={{ paddingBottom: '80px' }}>
            {/* 文檔基本信息 */}
            <div style={{ 
              padding: '16px', 
              background: '#f5f5f5', 
              borderRadius: '8px',
              marginBottom: '16px'
            }}>
              <h3 style={{ 
                margin: '0 0 12px 0', 
                fontSize: '16px',
                color: '#262626',
                wordBreak: 'break-word'
              }}>
                {selectedDocument.filename}
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px', color: '#595959' }}>
                {selectedDocument.file_type && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontWeight: 500 }}>類型:</span>
                    <span>{selectedDocument.file_type}</span>
                  </div>
                )}
                
                {selectedDocument.size && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontWeight: 500 }}>大小:</span>
                    <span>{(selectedDocument.size / 1024).toFixed(2)} KB</span>
                  </div>
                )}
                
                {selectedDocument.created_at && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontWeight: 500 }}>上傳時間:</span>
                    <span>{new Date(selectedDocument.created_at).toLocaleString('zh-TW')}</span>
                  </div>
                )}
              </div>
            </div>

            {/* 圖片預覽 */}
            {imagePreview && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ 
                  fontSize: '14px', 
                  color: '#262626', 
                  marginBottom: '8px',
                  fontWeight: 600
                }}>
                  🖼️ 圖片預覽
                </h4>
                <div style={{ 
                  width: '100%',
                  maxHeight: '300px',
                  overflow: 'hidden',
                  borderRadius: '8px',
                  border: '1px solid #e8e8e8',
                  background: '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  <img 
                    src={imagePreview} 
                    alt={selectedDocument.filename}
                    style={{
                      maxWidth: '100%',
                      maxHeight: '300px',
                      objectFit: 'contain'
                    }}
                  />
                </div>
              </div>
            )}

            {/* PDF 預覽 */}
            {pdfPreview && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ 
                  fontSize: '14px', 
                  color: '#262626', 
                  marginBottom: '8px',
                  fontWeight: 600
                }}>
                  📄 PDF 預覽
                </h4>
                <div style={{ 
                  width: '100%',
                  height: '400px',
                  borderRadius: '8px',
                  border: '1px solid #e8e8e8',
                  overflow: 'hidden'
                }}>
                  <iframe
                    src={pdfPreview}
                    style={{
                      width: '100%',
                      height: '100%',
                      border: 'none'
                    }}
                    title="PDF 預覽"
                  />
                </div>
                <div style={{
                  marginTop: '8px',
                  padding: '8px 12px',
                  background: '#f0f7ff',
                  borderRadius: '6px',
                  fontSize: '12px',
                  color: '#0066cc',
                  textAlign: 'center'
                }}>
                  💡 提示：點擊下方「查看完整詳情」查看完整 PDF
                </div>
              </div>
            )}

            {/* AI 分析摘要 */}
            {selectedDocument.analysis?.ai_analysis_output?.key_information?.content_summary && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ 
                  fontSize: '14px', 
                  color: '#262626', 
                  marginBottom: '8px',
                  fontWeight: 600
                }}>
                  📝 文檔摘要
                </h4>
                <div style={{ 
                  padding: '12px', 
                  background: '#fff', 
                  border: '1px solid #e8e8e8',
                  borderRadius: '6px',
                  fontSize: '13px',
                  color: '#595959',
                  lineHeight: '1.6',
                  whiteSpace: 'pre-wrap'
                }}>
                  {selectedDocument.analysis.ai_analysis_output.key_information.content_summary}
                </div>
              </div>
            )}

            {/* 關鍵信息 */}
            {selectedDocument.analysis?.ai_analysis_output?.key_information && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ 
                  fontSize: '14px', 
                  color: '#262626', 
                  marginBottom: '8px',
                  fontWeight: 600
                }}>
                  🔑 關鍵信息
                </h4>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {/* 主題 */}
                  {selectedDocument.analysis.ai_analysis_output.key_information.main_topics?.length > 0 && (
                    <div>
                      <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>主題</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {selectedDocument.analysis.ai_analysis_output.key_information.main_topics.map((topic: string, idx: number) => (
                          <span 
                            key={idx}
                            style={{
                              padding: '4px 10px',
                              background: '#e6f7ff',
                              color: '#0066cc',
                              borderRadius: '12px',
                              fontSize: '12px'
                            }}
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 關鍵概念 */}
                  {selectedDocument.analysis.ai_analysis_output.key_information.key_concepts?.length > 0 && (
                    <div>
                      <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>關鍵概念</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {selectedDocument.analysis.ai_analysis_output.key_information.key_concepts.map((concept: string, idx: number) => (
                          <span 
                            key={idx}
                            style={{
                              padding: '4px 10px',
                              background: '#f0f5ff',
                              color: '#1890ff',
                              borderRadius: '12px',
                              fontSize: '12px'
                            }}
                          >
                            {concept}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 日期 */}
                  {selectedDocument.analysis.ai_analysis_output.key_information.dates_mentioned?.length > 0 && (
                    <div>
                      <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>提及日期</div>
                      <div style={{ fontSize: '13px', color: '#595959' }}>
                        {selectedDocument.analysis.ai_analysis_output.key_information.dates_mentioned.join(', ')}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 標籤 */}
            {selectedDocument.tags && selectedDocument.tags.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ 
                  fontSize: '14px', 
                  color: '#262626', 
                  marginBottom: '8px',
                  fontWeight: 600
                }}>
                  🏷️ 標籤
                </h4>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {selectedDocument.tags.map((tag: string, idx: number) => (
                    <span 
                      key={idx}
                      style={{
                        padding: '4px 12px',
                        background: '#fafafa',
                        border: '1px solid #d9d9d9',
                        color: '#595959',
                        borderRadius: '4px',
                        fontSize: '12px'
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 操作按鈕 - 固定在底部 */}
            <div style={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              padding: '16px',
              background: '#fff',
              borderTop: '1px solid #e8e8e8',
              zIndex: 1000
            }}>
              <button
                onClick={openFullDocumentDetail}
                style={{
                  width: '100%',
                  padding: '12px',
                  background: '#1890ff',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '15px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}
              >
                <FileTextOutlined />
                查看完整詳情
              </button>
            </div>
          </div>
        ) : (
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            height: '200px',
            color: '#8c8c8c'
          }}>
            無法加載文檔信息
          </div>
        )}
      </Drawer>
    </>
  );
};

export default MobileAIQA;

