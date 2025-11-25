/**
 * AIQAPage - Neo-Brutalism Edition
 * 
 * 完整的 Agentic Chat Interface，參考 Cursor/Windsurf
 * 
 * 核心功能：
 * - ✅ 流式狀態機（顯示具體處理步驟）
 * - ✅ 推理鏈展示（ReasoningChainDisplay）
 * - ✅ 可折疊技術細節
 * - ✅ Human-in-the-loop 批准卡片
 * - ✅ 引用與文檔預覽聯動
 * - ✅ Streamdown 渲染
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Button,
  Input,
  Spin,
  Empty,
  Drawer,
  Typography,
  Modal,
} from 'antd';
import {
  RobotOutlined,
  SendOutlined,
  PlusOutlined,
  UserOutlined,
  QuestionCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';

// Components
import StreamedAnswer from '../components/chat/StreamedAnswer';
import ReasoningChainDisplay, { ReasoningStep } from '../components/ReasoningChainDisplay';
import { DocumentDetailsModal } from '../components';
import { FileMentionInput, type MentionedFile } from '../components/FileMentionInput';
import { FileSearchModal } from '../components/FileSearchModal';

// Services
import { streamQA } from '../services/streamQAService';
import { getVectorDatabaseStats } from '../services/vectorDBService';
import { getDocumentById } from '../services/documentService';
import conversationService from '../services/conversationService';

// Types
import type { VectorDatabaseStats, Document } from '../types/apiTypes';

const { TextArea } = Input;
const { Text } = Typography;

interface AIQAPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface QASession {
  id: string;
  question: string;
  answer: string;
  timestamp: Date;
  reasoningSteps?: ReasoningStep[];
  isStreaming?: boolean;
  sourceDocuments?: string[];
  tokensUsed?: number;
  processingTime?: number;
  documentPoolSnapshot?: any[]; // 保存生成時的文檔池快照，用於正確解析引用
}

const AIQAPageNeo: React.FC<AIQAPageProps> = ({ showPCMessage }) => {
  // ========== State Management ==========
  const [isLoading, setIsLoading] = useState(true);
  const [question, setQuestion] = useState(''); // 新增: 文件提及狀態
  const [mentionedFiles, setMentionedFiles] = useState<MentionedFile[]>([]);
  const [enableSemanticSearch, setEnableSemanticSearch] = useState(true); // 向量搜索开关
  const [isAsking, setIsAsking] = useState(false);
  const [qaHistory, setQAHistory] = useState<QASession[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  
  // Conversation History
  const [conversations, setConversations] = useState<any[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [showHistorySidebar, setShowHistorySidebar] = useState(true);
  
  // Grouped conversations by date
  const [groupedConversations, setGroupedConversations] = useState<{
    pinned: any[];
    today: any[];
    yesterday: any[];
    last7Days: any[];
    older: any[];
  }>({
    pinned: [],
    today: [],
    yesterday: [],
    last7Days: [],
    older: []
  });
  
  // Document Pool
  const [documentPool, setDocumentPool] = useState<any[]>([]);
  const [showDocumentPool, setShowDocumentPool] = useState(false);
  const [selectedDocForDetail, setSelectedDocForDetail] = useState<Document | null>(null);
  const [isLoadingDocDetail, setIsLoadingDocDetail] = useState(false);
  
  // ⭐ 監控 documentPool 狀態變化（僅用於調試）
  useEffect(() => {
    console.log('🔄 [documentPool 狀態更新]:', {
      count: documentPool.length,
      filenames: documentPool.map(d => d.filename)
    });
    // 注意：不再自動修正快照，因為現在使用 current_round_documents
    // 每個會話的快照只包含該輪次 AI 看到的文檔
  }, [documentPool]);
  
  // Removed AI Settings

  // Workflow State (for clarification, approvals)
  const [pendingWorkflow, setPendingWorkflow] = useState<any>(null);

  // Streaming State
  const [currentStreamingSession, setCurrentStreamingSession] = useState<{
    question: string;
    answer: string;
    reasoningSteps: ReasoningStep[];
    isStreaming: boolean;
    startTime: number;
    workflowState?: any;
    currentRoundDocuments?: any[]; // ⭐ 當前輪次的文檔快照（用於引用解析）
  } | null>(null);

  // Document Preview
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);
  const [previewDrawerOpen, setPreviewDrawerOpen] = useState(false);
  
  // File Search Modal
  const [showFileSearchModal, setShowFileSearchModal] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ========== Lifecycle ==========
  useEffect(() => {
    loadConversations();
    setIsLoading(false);
  }, []);
  
  // 快捷键支持 (Ctrl+K 打开文件搜索)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+K 或 Cmd+K
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setShowFileSearchModal(true);
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    // Auto scroll to bottom when new messages arrive
    if (currentStreamingSession || qaHistory.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentStreamingSession, qaHistory]);

  // Debug: Log workflow state changes
  useEffect(() => {
    if (currentStreamingSession?.workflowState) {
      console.log('🎬 工作流狀態更新:', {
        currentStep: currentStreamingSession.workflowState.current_step,
        pendingApproval: currentStreamingSession.workflowState.pending_approval,
        isStreaming: currentStreamingSession.isStreaming
      });
    }
  }, [currentStreamingSession?.workflowState]);

  // ========== Load Conversations ==========
  // 按日期分組對話
  const groupConversationsByDate = useCallback((convs: any[]) => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart);
    yesterdayStart.setDate(yesterdayStart.getDate() - 1);
    const last7DaysStart = new Date(todayStart);
    last7DaysStart.setDate(last7DaysStart.getDate() - 7);
    
    const grouped = {
      pinned: [] as any[],
      today: [] as any[],
      yesterday: [] as any[],
      last7Days: [] as any[],
      older: [] as any[]
    };
    
    convs.forEach((conv) => {
      // Pinned conversations go to pinned group
      if (conv.is_pinned) {
        grouped.pinned.push(conv);
        return;
      }
      
      const updatedAt = new Date(conv.updated_at);
      
      if (updatedAt >= todayStart) {
        grouped.today.push(conv);
      } else if (updatedAt >= yesterdayStart) {
        grouped.yesterday.push(conv);
      } else if (updatedAt >= last7DaysStart) {
        grouped.last7Days.push(conv);
      } else {
        grouped.older.push(conv);
      }
    });
    
    return grouped;
  }, []);
  
  const loadConversations = useCallback(async () => {
    try {
      setLoadingConversations(true);
      const response = await conversationService.listConversations();
      const convs = response.conversations || [];
      setConversations(convs);
      
      // 按日期分組
      const grouped = groupConversationsByDate(convs);
      setGroupedConversations(grouped);
      
      console.log('📊 對話分組:', {
        total: convs.length,
        pinned: grouped.pinned.length,
        today: grouped.today.length,
        yesterday: grouped.yesterday.length,
        last7Days: grouped.last7Days.length,
        older: grouped.older.length
      });
    } catch (error) {
      console.error('載入對話失敗:', error);
    } finally {
      setLoadingConversations(false);
    }
  }, [groupConversationsByDate]);

  // ========== Conversation Management ==========
  const switchConversation = async (conversationId: string) => {
    try {
      console.log('🔄 切換對話:', conversationId);
      setCurrentConversationId(conversationId);
      setQAHistory([]);
      setPendingWorkflow(null);
      setCurrentStreamingSession(null);
      setDocumentPool([]);  // 先清空，載入後更新
      
      // 獲取對話詳情
      const conversationDetail = await conversationService.getConversation(conversationId);
      
      console.log('📥 載入對話詳情:', {
        id: conversationDetail.id,
        title: conversationDetail.title,
        messageCount: conversationDetail.messages.length,
        cachedDocuments: conversationDetail.cached_documents?.length || 0,
        hasCachedDocumentData: !!conversationDetail.cached_document_data,
        cachedDocumentDataType: typeof conversationDetail.cached_document_data,
        cachedDocumentDataKeys: conversationDetail.cached_document_data ? Object.keys(conversationDetail.cached_document_data).length : 0
      });
      
      // 解析文檔池
      // ⭐ 重要：按相關性排序，與後端 _build_classification_context 保持一致
      // 這樣 citation:1 才能正確對應到相關性最高的文檔
      const docPool: any[] = [];
      if (conversationDetail.cached_document_data && typeof conversationDetail.cached_document_data === 'object') {
        console.log('📦 cached_document_data 內容:', conversationDetail.cached_document_data);
        for (const [docId, docInfo] of Object.entries(conversationDetail.cached_document_data)) {
          docPool.push({
            document_id: docId,
            ...docInfo as any
          });
        }
        // ⭐ 按相關性排序，與後端保持一致
        // 後端 _build_classification_context 也是按 relevance_score 降序排列
        docPool.sort((a: any, b: any) => (b.relevance_score || 0) - (a.relevance_score || 0));
      } else {
        console.warn('⚠️ cached_document_data 不存在或格式錯誤，需要後端自動修復');
      }
      setDocumentPool(docPool);
      console.log('📚 文檔池（按相關性排序）:', docPool.map(d => `${d.filename}(${d.relevance_score?.toFixed(2)})`));
      
      const loadedSessions: QASession[] = [];
      
      // 將消息轉換為 QA 會話（成對處理：用戶問題 + AI 回答）
      for (let i = 0; i < conversationDetail.messages.length; i += 2) {
        const userMsg = conversationDetail.messages[i];
        const assistantMsg = conversationDetail.messages[i + 1];
        
        // 確保用戶消息和助手消息都存在
        if (userMsg && assistantMsg && userMsg.role === 'user' && assistantMsg.role === 'assistant') {
          // ⭐ 關鍵修復：為歷史對話設置 documentPoolSnapshot
          // 由於我們無法知道每輪對話時的確切文檔池狀態，
          // 使用當前文檔池作為快照（按相關性排序後）
          // 這樣歷史對話中的引用點擊才能正確工作
          loadedSessions.push({
            id: `qa-${i}`,
            question: userMsg.content,
            answer: assistantMsg.content,
            timestamp: new Date(userMsg.timestamp),
            sourceDocuments: [],
            tokensUsed: assistantMsg.tokens_used || 0,
            processingTime: 0,
            reasoningSteps: [],
            isStreaming: false,
            documentPoolSnapshot: [...docPool]  // ⭐ 使用排序後的文檔池作為快照
          });
        }
      }
      
      console.log(`✅ 載入了 ${loadedSessions.length} 個 QA 會話`);
      setQAHistory(loadedSessions);
      showPCMessage(`已載入 ${conversationDetail.title}`, 'success');
    } catch (error) {
      console.error('切換對話失敗:', error);
      showPCMessage('載入對話失敗', 'error');
    }
  };

  const deleteConversation = async (conversationId: string) => {
    try {
      await conversationService.deleteConversation(conversationId);
      const updatedConvs = conversations.filter(c => c.id !== conversationId);
      setConversations(updatedConvs);
      
      // 重新分組
      const grouped = groupConversationsByDate(updatedConvs);
      setGroupedConversations(grouped);
      
      if (currentConversationId === conversationId) {
        // 清空當前對話的所有狀態
        setCurrentConversationId(null);
        setCurrentSessionId(null);
        setQAHistory([]);
        setDocumentPool([]); // 清空文檔池
        setCurrentStreamingSession(null); // 清空流式會話
        setPendingWorkflow(null); // 清空待處理工作流
      }
      showPCMessage('已刪除對話', 'success');
    } catch (error) {
      console.error('刪除對話失敗:', error);
      showPCMessage('刪除對話失敗', 'error');
    }
  };

  // ========== Pin/Unpin Conversation ==========
  const togglePinConversation = async (conversationId: string, currentlyPinned: boolean) => {
    try {
      if (currentlyPinned) {
        await conversationService.unpinConversation(conversationId);
      } else {
        await conversationService.pinConversation(conversationId);
      }
      
      // 更新對話列表
      const updatedConvs = conversations.map(c => 
        c.id === conversationId ? { ...c, is_pinned: !currentlyPinned } : c
      );
      setConversations(updatedConvs);
      
      // 重新分組
      const grouped = groupConversationsByDate(updatedConvs);
      setGroupedConversations(grouped);
      
      showPCMessage(currentlyPinned ? '已取消置頂' : '已置頂對話', 'success');
    } catch (error) {
      console.error('Pin/Unpin 對話失敗:', error);
      showPCMessage('操作失敗', 'error');
    }
  };

  // ========== Document Pool Smart Merge ==========
  const mergeDocumentPool = useCallback((meta: any) => {
    console.log('🔍 [mergeDocumentPool] 收到 metadata:', {
      has_meta: !!meta,
      has_document_pool: !!meta?.document_pool,
      document_pool_type: typeof meta?.document_pool,
      document_pool_keys: meta?.document_pool ? Object.keys(meta.document_pool).length : 0,
      raw_meta: meta
    });
    
    if (!meta?.document_pool) {
      console.warn('⚠️ [mergeDocumentPool] document_pool 不存在，跳過合併');
      return;
    }
    
    // ⭐ 關鍵修復：保持後端返回的順序（後端已按 source_documents 順序排列）
    // Object.entries 會保持 JS 對象的插入順序
    const backendDocs = Object.entries(meta.document_pool).map(([docId, docInfo]: [string, any]) => ({
      document_id: docId,
      filename: docInfo.filename,
      summary: docInfo.summary,
      key_concepts: docInfo.key_concepts || [],
      relevance_score: docInfo.relevance_score,
      access_count: docInfo.access_count
    }));
    
    console.log('📊 [mergeDocumentPool] 後端文檔數:', backendDocs.length, backendDocs.map(d => d.filename));
    
    // ⭐ 直接使用後端返回的順序，不做任何合併或重排
    // 這樣可以確保引用編號與文檔一一對應
    setDocumentPool(() => {
      console.log('✅ [mergeDocumentPool] 直接使用後端順序:', { 
        backend_count: backendDocs.length,
        filenames: backendDocs.map(d => d.filename)
      });
      
      return backendDocs;
    });
  }, []);

  // ========== Citation Click ==========
  const handleCitationClick = async (docId: number, sessionDocumentPool?: any[]) => {
    try {
      console.log('🔍 [handleCitationClick] 點擊引用:', {
        docId,
        hasSessionPool: !!sessionDocumentPool,
        sessionPoolSize: sessionDocumentPool?.length,
        currentPoolSize: documentPool.length,
        currentPoolFilenames: documentPool.map(d => d.filename)
      });
      
      // ⭐ 智能選擇文檔池：優先使用 session pool，但如果引用超出範圍，回退到全局 pool
      let targetPool = sessionDocumentPool || documentPool;
      const docIndex = docId - 1; // 轉換為 0-based index
      
      // 如果 session pool 存在但引用超出範圍，嘗試使用全局 pool（可能是快照不完整）
      if (sessionDocumentPool && (docIndex < 0 || docIndex >= sessionDocumentPool.length)) {
        console.warn(`⚠️ 引用編號 ${docId} 超出 session pool 範圍 (${sessionDocumentPool.length}), 嘗試使用全局文檔池 (${documentPool.length})`);
        
        // 如果全局 pool 能覆蓋這個引用，就使用全局 pool
        if (docIndex >= 0 && docIndex < documentPool.length) {
          console.log('✅ 使用全局文檔池作為 fallback');
          targetPool = documentPool;
        } else {
          console.error(`❌ 引用編號 ${docId} 在全局文檔池中也不存在`);
          showPCMessage(`引用編號 ${docId} 超出文檔池範圍`, 'error');
          return;
        }
      }
      
      console.log('🎯 [handleCitationClick] 使用的文檔池:', {
        poolSize: targetPool.length,
        filenames: targetPool.map(d => d.filename)
      });

      if (docIndex < 0 || docIndex >= targetPool.length) {
        console.warn(`⚠️ 引用編號 ${docId} 超出文檔池範圍 (池大小: ${targetPool.length})`);
        showPCMessage(`引用編號 ${docId} 超出文檔池範圍`, 'error');
        return;
      }
      
      const poolDoc = targetPool[docIndex];
      const actualDocId = poolDoc.document_id;
      
      console.log(`📄 從文檔池載入文檔: ${poolDoc.filename} (ID: ${actualDocId})`);
      showPCMessage(`正在載入 ${poolDoc.filename}...`, 'info');
      
      // 獲取完整文檔資料
      const doc = await getDocumentById(actualDocId);
      setPreviewDoc(doc);
      setPreviewDrawerOpen(true);
      
      console.log('✅ 文檔預覽已打開');
    } catch (error) {
      console.error('❌ 載入文檔失敗:', error);
      showPCMessage('載入文檔失敗', 'error');
    }
  };

  // ========== New Conversation ==========
  const startNewConversation = async () => {
    try {
      const newConv = await conversationService.createConversation('新對話');
      setConversations(prev => [newConv, ...prev]);
      setCurrentConversationId(newConv.id);
      setCurrentSessionId(null);
      setQAHistory([]);
      setQuestion('');
      setMentionedFiles([]);  // 清空 @ 文件
      setDocumentPool([]);  // 清空文檔池
      showPCMessage('已開始新對話', 'success');
    } catch (error) {
      console.error('創建對話失敗:', error);
      showPCMessage('創建對話失敗', 'error');
    }
  };

  // ========== Shared Progress Handler ==========
  const handleProgressEvent = (
    stage: string,
    message: string,
    detail: any,
    tempReasoningSteps: ReasoningStep[]
  ) => {
    // 處理後端 progress events
    if (stage === 'reasoning' && detail) {
      tempReasoningSteps.push({
        type: 'thought',
        stage: 'reasoning',
        message: '💭 AI 推理',
        detail,
        status: 'done',
        timestamp: Date.now()
      });
    } else if (stage === 'classifying') {
      tempReasoningSteps.push({
        type: 'thought',
        stage: 'classifying',
        message: '🎯 AI 正在分析問題意圖...',
        detail: detail || {},
        status: 'active',
        timestamp: Date.now()
      });
    } else if (stage === 'classified') {
      // 標記分類步驟為完成
      if (tempReasoningSteps.length > 0 && tempReasoningSteps[tempReasoningSteps.length - 1].stage === 'classifying') {
        tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
        tempReasoningSteps[tempReasoningSteps.length - 1].message = message || '✅ 問題分類完成';
        tempReasoningSteps[tempReasoningSteps.length - 1].detail = detail || {};
      }
    } else if (stage === 'reasoning') {
      // AI 推理內容
      tempReasoningSteps.push({
        type: 'thought',
        stage: 'reasoning',
        message: message || '💭 AI 推理',
        detail: detail || {},
        status: 'done',
        timestamp: Date.now()
      });
    } else if (stage === 'query_rewriting') {
      // 檢查是否已經有 query_rewriting 步驟
      const existingIndex = tempReasoningSteps.findIndex(s => s.stage === 'query_rewriting');
      if (existingIndex !== -1) {
        // 更新現有步驟的詳細信息
        tempReasoningSteps[existingIndex].message = message || tempReasoningSteps[existingIndex].message;
        tempReasoningSteps[existingIndex].detail = detail || tempReasoningSteps[existingIndex].detail;
        tempReasoningSteps[existingIndex].status = detail ? 'done' : 'active';
      } else {
        // 標記前一步為完成
        if (tempReasoningSteps.length > 0 && tempReasoningSteps[tempReasoningSteps.length - 1].status === 'active') {
          tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
        }
        // 創建新步驟
        tempReasoningSteps.push({
          type: 'action',
          stage: 'query_rewriting',
          message: message || '🔄 正在優化查詢語句...',
          detail: detail || {},
          status: detail ? 'done' : 'active',
          timestamp: Date.now()
        });
      }
    } else if (stage === 'mongodb_query') {
      // 標記前一步為完成
      if (tempReasoningSteps.length > 0 && tempReasoningSteps[tempReasoningSteps.length - 1].status === 'active') {
        tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
      }
      tempReasoningSteps.push({
        type: 'action',
        stage: 'mongodb_query',
        message: message || '🔍 執行 MongoDB 詳細查詢',
        detail: detail || {},
        status: 'active',
        timestamp: Date.now()
      });
    } else if (stage === 'vector_search') {
      // 檢查是否已經有 vector_search 步驟
      const existingIndex = tempReasoningSteps.findIndex(s => s.stage === 'vector_search');
      if (existingIndex !== -1) {
        // 更新現有步驟（特別是添加文檔列表）
        tempReasoningSteps[existingIndex].message = message || tempReasoningSteps[existingIndex].message;
        tempReasoningSteps[existingIndex].detail = detail || tempReasoningSteps[existingIndex].detail;
        tempReasoningSteps[existingIndex].status = 'done';
      } else {
        // 標記前一步為完成
        if (tempReasoningSteps.length > 0 && tempReasoningSteps[tempReasoningSteps.length - 1].status === 'active') {
          tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
        }
        // 創建新步驟
        tempReasoningSteps.push({
          type: 'observation',
          stage: 'vector_search',
          message: message || '🔎 調用工具: vector_search',
          detail: detail || {},
          status: detail ? 'done' : 'active',
          timestamp: Date.now()
        });
      }
    } else if (stage === 'ai_generating') {
      // 標記前一步為完成
      if (tempReasoningSteps.length > 0 && tempReasoningSteps[tempReasoningSteps.length - 1].status === 'active') {
        tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
      }
      tempReasoningSteps.push({
        type: 'generating',
        stage: 'ai_generating',
        message: '🤖 AI 正在生成答案...',
        detail: detail || {},
        status: 'active',
        timestamp: Date.now()
      });
    }
  };

  // ========== Document Pool Actions ==========
  const handleViewDocumentDetail = async (docId: string) => {
    try {
      setIsLoadingDocDetail(true);
      const doc = await getDocumentById(docId);
      setSelectedDocForDetail(doc);
    } catch (error) {
      console.error('❌ 載入文檔詳情失敗:', error);
      showPCMessage('載入文檔詳情失敗', 'error');
    } finally {
      setIsLoadingDocDetail(false);
    }
  };

  const handleRemoveFromDocumentPool = async (docId: string) => {
    try {
      // ✅ 如果有對話 ID，同步到後端
      if (currentConversationId) {
        await conversationService.removeCachedDocument(currentConversationId, docId);
      }
      
      // ✅ 總是更新本地文檔池狀態（即使沒有對話 ID）
      setDocumentPool(prev => prev.filter(doc => doc.document_id !== docId));
      
      showPCMessage('已從文檔池移除', 'success');
    } catch (error) {
      console.error('❌ 移除文檔失敗:', error);
      showPCMessage('移除文檔失敗', 'error');
    }
  };

  // ========== Handle Approval ==========
  const handleApprove = async (action: 'approve_search' | 'skip_search' | 'approve_detail_query' | 'skip_detail_query') => {
    if (!pendingWorkflow) return;

    const originalQuestion = pendingWorkflow.originalQuestion;
    
    console.log('📤 批准操作:', action, '查詢:', originalQuestion);
    
    // 清除工作流狀態
    setPendingWorkflow(null);
    setIsAsking(true);

    // 更新流式會話，添加批准決策到 reasoning steps
    const actionLabels = {
      'approve_search': '✅ 已批准文檔搜索',
      'skip_search': '⏭️ 已跳過文檔搜索',
      'approve_detail_query': '✅ 已批准詳細查詢',
      'skip_detail_query': '⏭️ 已跳過詳細查詢'
    };

    // 保留當前 session 的內容
    const existingAnswer = currentStreamingSession?.answer || '';
    const existingSteps = currentStreamingSession?.reasoningSteps || [];
    
    const approvalStep: ReasoningStep = {
      type: 'action',
      stage: 'approval',
      message: actionLabels[action] || action,
      detail: null,
      status: 'done',
      timestamp: Date.now()
    };

    setCurrentStreamingSession(prev => {
      if (!prev) return null;

      return {
        ...prev,
        question: originalQuestion,  // 使用原始問題（已被後端組合）
        reasoningSteps: [...prev.reasoningSteps, approvalStep],
        workflowState: undefined,
        isStreaming: true
      };
    });

    let fullAnswer = existingAnswer; // 保留現有答案
    const tempReasoningSteps: ReasoningStep[] = [...existingSteps, approvalStep];
    let metadata: any = {};

    await streamQA(
      {
        question: originalQuestion,  // 使用原始問題（後端已組合好）
        conversation_id: currentConversationId || undefined,
        session_id: currentSessionId || undefined,
        workflow_action: action,
        context_limit: 10,
        use_semantic_search: true,
        use_structured_filter: true
      },
      {
        onProgress: (stage, message, detail) => {
          console.log('📊 Progress (批准):', stage, message, detail);
          handleProgressEvent(stage, message, detail, tempReasoningSteps);
          
          // 如果是查詢重寫結果，更新 pendingWorkflow 的查詢重寫結果
          if (stage === 'query_rewriting' && detail && detail.queries) {
            setPendingWorkflow((prev: any) => prev ? {
              ...prev,
              state: {
                ...prev.state,
                query_rewrite_result: {
                  rewritten_queries: detail.queries,
                  count: detail.count
                }
              }
            } : null);
          }
          
          setCurrentStreamingSession(prev => prev ? {
            ...prev,
            reasoningSteps: [...tempReasoningSteps]
          } : null);
        },
        onChunk: (text) => {
          fullAnswer += text;
          setCurrentStreamingSession(prev => prev ? {
            ...prev,
            answer: fullAnswer
          } : null);
        },
        onMetadata: (meta) => {
          metadata = meta;
          // ⭐ 使用智能合併邏輯
          mergeDocumentPool(meta);
          
          // ⭐⭐ 保存當前輪次的文檔到 streaming session（用於引用解析）
          if (meta.current_round_documents && meta.current_round_documents.length > 0) {
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              currentRoundDocuments: meta.current_round_documents
            } : null);
          }
        },
        onComplete: (completeAnswer, completeData?: any) => {
          console.log('✅ 批准後答案完成', completeData);
          const processingTime = (Date.now() - (currentStreamingSession?.startTime || Date.now())) / 1000;

          // 檢查是否需要澄清
          if (completeData?.workflow_state?.current_step === 'need_clarification') {
            console.log('📝 批准後需要澄清');
            
            // 添加澄清請求步驟到 reasoning chain
            const clarificationStep: ReasoningStep = {
              type: 'approval',
              stage: 'need_clarification',
              message: '❓ 需要澄清問題',
              detail: completeData.workflow_state,
              status: 'active',
              timestamp: Date.now()
            };
            
            tempReasoningSteps.push(clarificationStep);
            
            setPendingWorkflow({
              originalQuestion,
              state: completeData.workflow_state
            });
            
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              answer: fullAnswer || completeAnswer,
              reasoningSteps: [...tempReasoningSteps],
              workflowState: completeData.workflow_state,
              isStreaming: false
            } : null);
            
            setIsAsking(false);
            return;
          }

          // 檢查是否還需要進一步批准
          if (completeData?.workflow_state?.current_step === 'awaiting_search_approval' ||
              completeData?.workflow_state?.current_step === 'awaiting_detail_query_approval') {
            console.log('📋 批准後仍需進一步批准');
            
            const mergedState = {
              ...completeData.workflow_state,
              query_rewrite_result: completeData.query_rewrite_result,
              classification: completeData.classification,
              next_action: completeData.next_action,
              pending_approval: completeData.pending_approval
            };
            
            setPendingWorkflow({
              originalQuestion,
              state: mergedState
            });
            
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              answer: fullAnswer || completeAnswer,
              workflowState: mergedState,
              isStreaming: false
            } : null);
            
            setIsAsking(false);
            return;
          }

          // ⭐⭐ 使用當前輪次的文檔快照
          const currentRoundDocs = metadata.current_round_documents || [];
          
          const newSession: QASession = {
            id: `qa-${Date.now()}`,
            question: originalQuestion,
            answer: fullAnswer || completeAnswer,
            timestamp: new Date(),
            sourceDocuments: metadata.source_documents || [],
            tokensUsed: metadata.tokens_used || 0,
            processingTime,
            reasoningSteps: tempReasoningSteps,
            isStreaming: false,
            documentPoolSnapshot: currentRoundDocs.length > 0 ? currentRoundDocs : [...documentPool]
          };

          // 新會話添加到末尾（渲染時顯示在下面）
          setQAHistory(prev => [...prev, newSession]);
          setCurrentStreamingSession(null);
          setIsAsking(false);
        },
        onApprovalNeeded: (approvalData) => {
          console.log('⚠️ 批准後仍需批准:', approvalData);
          
          // 合併 workflow_state 和額外數據
          const mergedState = {
            ...approvalData.workflow_state,
            query_rewrite_result: approvalData.query_rewrite_result,
            classification: approvalData.classification,
            next_action: approvalData.next_action,
            pending_approval: approvalData.pending_approval
          };
          
          // 添加批准/澄清請求到 reasoning chain
          const approvalStep: ReasoningStep = {
            type: 'approval',
            stage: mergedState.current_step || 'approval',
            message: mergedState.current_step === 'awaiting_search_approval' 
              ? '🔐 需要權限批准：文檔搜索'
              : mergedState.current_step === 'awaiting_detail_query_approval'
              ? '🔐 需要權限批准：詳細查詢'
              : mergedState.current_step === 'need_clarification'
              ? '❓ 需要澄清問題'
              : '🔐 需要權限批准',
            detail: mergedState,
            status: 'active',
            timestamp: Date.now()
          };
          
          tempReasoningSteps.push(approvalStep);
          
          // 可能還需要其他批准（如搜索後需要詳細查詢）
          setPendingWorkflow({
            originalQuestion,
            state: mergedState
          });
          setCurrentStreamingSession(prev => prev ? {
            ...prev,
            reasoningSteps: [...tempReasoningSteps],
            workflowState: mergedState,
            isStreaming: false
          } : null);
          setIsAsking(false);
        },
        onError: (error) => {
          console.error('❌ 批准後處理失敗:', error);
          showPCMessage(`處理失敗: ${error}`, 'error');
          setCurrentStreamingSession(null);
          setIsAsking(false);
        }
      }
    );
  };

  // ========== Handle Clarification Submit ==========
  const handleClarificationSubmit = async () => {
    if (!pendingWorkflow || !question.trim()) return;

    const clarificationText = question.trim();
    const originalQuestion = pendingWorkflow.originalQuestion;
    
    console.log('📤 提交澄清回答:', clarificationText);
    
    // 清空輸入框
    setQuestion('');
    setMentionedFiles([]);  // 清空 @ 文件
    
    // 清除工作流狀態
    setPendingWorkflow(null);
    setIsAsking(true);

    // 保留當前 session，添加澄清回答標記
    const existingSteps = currentStreamingSession?.reasoningSteps || [];
    const existingAnswer = currentStreamingSession?.answer || '';
    
    // 添加澄清回答的標記到 reasoning steps
    const clarificationStep: ReasoningStep = {
      type: 'action',
      stage: 'clarification_response',
      message: `💬 用戶回答：${clarificationText}`,
      detail: null,
      status: 'done',
      timestamp: Date.now()
    };
    
    // 繼續在當前 session 中，不創建新的
    setCurrentStreamingSession(prev => prev ? {
      ...prev,
      reasoningSteps: [...prev.reasoningSteps, clarificationStep],
      workflowState: undefined, // 清除 workflow state
      isStreaming: true
    } : {
      question: originalQuestion, // 保持原始問題
      answer: existingAnswer,
      reasoningSteps: [clarificationStep],
      isStreaming: true,
      startTime: Date.now()
    });

    let fullAnswer = existingAnswer; // 從現有答案繼續
    const tempReasoningSteps: ReasoningStep[] = [...existingSteps, clarificationStep];
    let metadata: any = {};

    await streamQA(
      {
        question: originalQuestion,
        conversation_id: currentConversationId || undefined,
        session_id: currentSessionId || undefined,
        workflow_action: 'provide_clarification',
        clarification_text: clarificationText,
        context_limit: 10,
        use_semantic_search: true,
        use_structured_filter: true
      },
      {
        onProgress: (stage, message, detail) => {
          console.log('📊 Progress (澄清後):', stage, message, detail);
          handleProgressEvent(stage, message, detail, tempReasoningSteps);
          
          // 如果是查詢重寫結果，更新 pendingWorkflow 的查詢重寫結果
          if (stage === 'query_rewriting' && detail && detail.queries) {
            setPendingWorkflow((prev: any) => prev ? {
              ...prev,
              state: {
                ...prev.state,
                query_rewrite_result: {
                  rewritten_queries: detail.queries,
                  count: detail.count
                }
              }
            } : null);
          }
          
          setCurrentStreamingSession(prev => prev ? {
            ...prev,
            reasoningSteps: [...tempReasoningSteps]
          } : null);
        },
        onChunk: (text) => {
          fullAnswer += text;
          setCurrentStreamingSession(prev => prev ? {
            ...prev,
            answer: fullAnswer
          } : null);
        },
        onMetadata: (meta) => {
          metadata = meta;
          // ⭐ 使用智能合併邏輯
          mergeDocumentPool(meta);
          
          // ⭐⭐ 保存當前輪次的文檔到 streaming session（用於引用解析）
          if (meta.current_round_documents && meta.current_round_documents.length > 0) {
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              currentRoundDocuments: meta.current_round_documents
            } : null);
          }
        },
        onComplete: (completeAnswer, completeData?: any) => {
          console.log('✅ 澄清後答案完成', completeData);
          const processingTime = (Date.now() - (currentStreamingSession?.startTime || Date.now())) / 1000;

          // 檢查澄清後是否還需要進一步澄清
          if (completeData?.workflow_state?.current_step === 'need_clarification') {
            console.log('📝 澄清後仍需澄清');
            
            // 添加澄清請求步驟到 reasoning chain
            const clarificationStep: ReasoningStep = {
              type: 'approval',
              stage: 'need_clarification',
              message: '❓ 需要澄清問題',
              detail: completeData.workflow_state,
              status: 'active',
              timestamp: Date.now()
            };
            
            tempReasoningSteps.push(clarificationStep);
            
            // 不保存到歷史，繼續在當前 session 中顯示
            setPendingWorkflow({
              originalQuestion,
              state: completeData.workflow_state
            });
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              answer: fullAnswer || completeAnswer,
              reasoningSteps: [...tempReasoningSteps],
              workflowState: completeData.workflow_state,
              isStreaming: false
            } : null);
            setIsAsking(false);
            return;
          }

          // 檢查是否需要批准
          if (completeData?.workflow_state?.current_step === 'awaiting_search_approval' ||
              completeData?.workflow_state?.current_step === 'awaiting_detail_query_approval') {
            console.log('📋 澄清後需要批准');
            
            const mergedState = {
              ...completeData.workflow_state,
              query_rewrite_result: completeData.query_rewrite_result,
              classification: completeData.classification,
              next_action: completeData.next_action,
              pending_approval: completeData.pending_approval
            };
            
            setPendingWorkflow({
              originalQuestion,
              state: mergedState
            });
            
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              answer: fullAnswer || completeAnswer,
              workflowState: mergedState,
              isStreaming: false
            } : null);
            
            setIsAsking(false);
            return;
          }

          // ⭐⭐ 使用當前輪次的文檔快照
          const currentRoundDocs = metadata.current_round_documents || [];

          // 最終完成 - 保存整個對話到歷史
          const newSession: QASession = {
            id: `qa-${Date.now()}`,
            question: originalQuestion, // 使用原始問題
            answer: fullAnswer || completeAnswer,
            timestamp: new Date(),
            sourceDocuments: metadata.source_documents || [],
            tokensUsed: metadata.tokens_used || 0,
            processingTime,
            reasoningSteps: tempReasoningSteps,
            isStreaming: false,
            documentPoolSnapshot: currentRoundDocs.length > 0 ? currentRoundDocs : [...documentPool]
          };

          // 新會話添加到末尾（渲染時顯示在下面）
          setQAHistory(prev => [...prev, newSession]);
          setCurrentStreamingSession(null);
          setIsAsking(false);
        },
        onApprovalNeeded: (approvalData) => {
          console.log('⚠️ 澄清後仍需批准:', approvalData);
          
          // 合併 workflow_state 和額外數據
          const mergedState = {
            ...approvalData.workflow_state,
            query_rewrite_result: approvalData.query_rewrite_result,
            classification: approvalData.classification,
            next_action: approvalData.next_action,
            pending_approval: approvalData.pending_approval
          };
          
          console.log('📋 合併後的狀態:', mergedState);
          console.log('📋 當前步驟:', mergedState.current_step);
          
          // 添加批准/澄清請求到 reasoning chain
          const approvalStep: ReasoningStep = {
            type: 'approval',
            stage: mergedState.current_step || 'approval',
            message: mergedState.current_step === 'awaiting_search_approval' 
              ? '🔐 需要權限批准：文檔搜索'
              : mergedState.current_step === 'awaiting_detail_query_approval'
              ? '🔐 需要權限批准：詳細查詢'
              : mergedState.current_step === 'need_clarification'
              ? '❓ 需要澄清問題'
              : '🔐 需要權限批准',
            detail: mergedState,
            status: 'active',
            timestamp: Date.now()
          };
          
          tempReasoningSteps.push(approvalStep);
          
          // 可能還需要其他批准
          // ⭐ 重要：使用後端返回的組合後問題（如 "收據 → 早餐"）
          // 後端在處理澄清時已經組合了問題，並通過 search_preview.original_question 返回
          const combinedQuestion = mergedState.search_preview?.original_question || originalQuestion;
          console.log('🔍 [澄清後批准] 組合後的問題:', combinedQuestion, '(原始:', originalQuestion, ')');
          
          setPendingWorkflow({
            originalQuestion: combinedQuestion,  // 使用組合後的問題
            state: mergedState
          });
          setCurrentStreamingSession(prev => {
            console.log('📋 更新 currentStreamingSession，添加 workflowState');
            return prev ? {
              ...prev,
              reasoningSteps: [...tempReasoningSteps],
              workflowState: mergedState,
              isStreaming: false
            } : null;
          });
          setIsAsking(false);
        },
        onError: (error) => {
          console.error('❌ 澄清後處理失敗:', error);
          showPCMessage(`處理失敗: ${error}`, 'error');
          setCurrentStreamingSession(null);
          setIsAsking(false);
        }
      }
    );
  };

  // ========== Streaming Q&A ==========
  const handleAskQuestionStream = async (customQuestion?: string) => {
    const questionToAsk = customQuestion || question.trim();
    
    if (!questionToAsk.trim()) {
      showPCMessage('請輸入問題', 'error');
      return;
    }

    try {
      setIsAsking(true);
      setQuestion(''); // Clear input
      
      // ✅ 從文檔池中提取文檔 ID 作為上下文
      // 注意：文件已經在 @ 選擇時添加到 documentPool 了
      const mentionedDocIds = documentPool.map(d => d.document_id);
      console.log('📚 文檔池狀態:', { 
        documentPool, 
        mentionedDocIds,
        count: mentionedDocIds.length 
      });

      // Create conversation if needed
      let conversationId = currentConversationId;
      if (!conversationId) {
        try {
          const newConversation = await conversationService.createConversation(questionToAsk);
          conversationId = newConversation.id;
          setCurrentConversationId(conversationId);
        } catch (error) {
          console.error('創建對話失敗:', error);
        }
      }

      // Initialize streaming session
      setCurrentStreamingSession({
        question: questionToAsk,
        answer: '',
        reasoningSteps: [],
        isStreaming: true,
        startTime: Date.now()
      });

      let fullAnswer = '';
      const tempReasoningSteps: ReasoningStep[] = [];
      let metadata: any = {};

      await streamQA(
        {
          question: questionToAsk,
          conversation_id: conversationId || undefined,
          session_id: currentSessionId || undefined,
          document_ids: mentionedDocIds.length > 0 ? mentionedDocIds : undefined,
          context_limit: 10,
          use_semantic_search: true,
          use_structured_filter: true
        },
        {
          // Handle reasoning/progress steps
          onProgress: (stage, message, detail) => {
            console.log('📊 Progress:', stage, message, detail);
            handleProgressEvent(stage, message, detail, tempReasoningSteps);
            
            // 如果是查詢重寫結果，更新 pendingWorkflow 的查詢重寫結果
            if (stage === 'query_rewriting' && detail && detail.queries) {
              setPendingWorkflow((prev: any) => prev ? {
                ...prev,
                state: {
                  ...prev.state,
                  query_rewrite_result: {
                    rewritten_queries: detail.queries,
                    count: detail.count
                  }
                }
              } : null);
            }
            
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              reasoningSteps: [...tempReasoningSteps]
            } : null);
          },

          // Handle answer chunks
          onChunk: (text) => {
            fullAnswer += text;
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              answer: fullAnswer
            } : null);
          },

          // Handle metadata
          onMetadata: (meta) => {
            metadata = meta;
            console.log('📋 Metadata:', meta);
            // ⭐ 使用智能合併邏輯
            mergeDocumentPool(meta);
            
            // ⭐⭐ 保存當前輪次的文檔到 streaming session（用於引用解析）
            if (meta.current_round_documents && meta.current_round_documents.length > 0) {
              console.log('📸 [onMetadata] 保存當前輪次文檔:', meta.current_round_documents.map((d: any) => d.filename));
              setCurrentStreamingSession(prev => prev ? {
                ...prev,
                currentRoundDocuments: meta.current_round_documents
              } : null);
            }
          },

          // Handle completion
          onComplete: (completeAnswer, completeData?: any) => {
            console.log('✅ Stream complete', completeData);

            if (tempReasoningSteps.length > 0) {
              tempReasoningSteps[tempReasoningSteps.length - 1].status = 'done';
              tempReasoningSteps[tempReasoningSteps.length - 1].message = '✅ 答案生成完成';
            }

            const processingTime = (Date.now() - (currentStreamingSession?.startTime || Date.now())) / 1000;

            // 檢查是否包含 workflow_state（澄清問題）
            if (completeData?.workflow_state?.current_step === 'need_clarification') {
              console.log('📝 收到澄清問題:', completeData.workflow_state);
              
              // 添加澄清請求步驟到 reasoning chain
              const clarificationStep: ReasoningStep = {
                type: 'approval',
                stage: 'need_clarification',
                message: '❓ 需要澄清問題',
                detail: completeData.workflow_state,
                status: 'active',
                timestamp: Date.now()
              };
              
              tempReasoningSteps.push(clarificationStep);
              
              // 設置工作流狀態
              setPendingWorkflow({
                originalQuestion: questionToAsk,
                state: completeData.workflow_state
              });
              
              // 更新流式會話包含 workflowState 和 reasoning steps
              setCurrentStreamingSession(prev => prev ? {
                ...prev,
                answer: fullAnswer || completeAnswer,
                reasoningSteps: [...tempReasoningSteps],
                workflowState: completeData.workflow_state,
                isStreaming: false
              } : null);
              
              setIsAsking(false);
              showPCMessage('請提供更多資訊以繼續', 'info');
              return;
            }

            // ⭐ 正常完成（無需批准的情況，如高置信度自動批准）
            // 創建 QASession 並保存到歷史記錄
            if (fullAnswer || completeAnswer) {
              // ⭐⭐ 關鍵修復：使用 current_round_documents 作為快照
              // 這只包含當前輪次 AI 看到的文檔（按順序），而不是累積的全部文檔池
              // 這樣 citation:1 就會正確指向當前輪次的第一個文檔
              const currentRoundDocs = metadata.current_round_documents || [];
              
              console.log('📸 [documentPoolSnapshot] 使用當前輪次文檔:', {
                current_round_count: currentRoundDocs.length,
                current_round_filenames: currentRoundDocs.map((d: any) => d.filename),
                full_pool_count: documentPool.length
              });
              
              const newSession: QASession = {
                id: `qa-${Date.now()}`,
                question: questionToAsk,
                answer: fullAnswer || completeAnswer,
                timestamp: new Date(),
                sourceDocuments: metadata.source_documents || [],
                tokensUsed: metadata.tokens_used || 0,
                processingTime,
                reasoningSteps: tempReasoningSteps,
                isStreaming: false,
                // ⭐⭐ 使用當前輪次的文檔快照，而不是累積的文檔池
                documentPoolSnapshot: currentRoundDocs.length > 0 ? currentRoundDocs : [...documentPool]
              };

              // 新會話添加到末尾
              setQAHistory(prev => [...prev, newSession]);
              setCurrentStreamingSession(null);
            }

            setIsAsking(false);
          },

          // Handle approval needed
          onApprovalNeeded: (approvalData) => {
            console.log('⚠️ Approval needed:', approvalData);
            
            // 合併 workflow_state 和額外數據
            const mergedState = {
              ...approvalData.workflow_state,
              query_rewrite_result: approvalData.query_rewrite_result,
              classification: approvalData.classification,
              next_action: approvalData.next_action,
              pending_approval: approvalData.pending_approval
            };
            
            // 添加批准/澄清請求到 reasoning chain
            const approvalStep: ReasoningStep = {
              type: 'approval',
              stage: mergedState.current_step || 'approval',
              message: mergedState.current_step === 'awaiting_search_approval' 
                ? '🔐 需要權限批准：文檔搜索'
                : mergedState.current_step === 'awaiting_detail_query_approval'
                ? '🔐 需要權限批准：詳細查詢'
                : mergedState.current_step === 'need_clarification'
                ? '❓ 需要澄清問題'
                : '🔐 需要權限批准',
              detail: mergedState,
              status: 'active',
              timestamp: Date.now()
            };
            
            tempReasoningSteps.push(approvalStep);
            
            // 設置工作流狀態  
            // ⭐ 優先使用後端返回的問題（可能已經組合了澄清答案）
            const actualQuestion = 
              mergedState.search_preview?.original_question ||  // 後端組合後的問題（如 "收據 → 早餐"）
              currentStreamingSession?.question ||              // 當前會話問題
              questionToAsk;                                     // 原始問題
            
            console.log('🔍 [主流程批准] 使用問題:', actualQuestion);
            
            setPendingWorkflow({
              originalQuestion: actualQuestion,
              state: mergedState
            });
            
            // 更新當前流式會話的 workflowState 和 reasoning steps
            setCurrentStreamingSession(prev => prev ? {
              ...prev,
              reasoningSteps: [...tempReasoningSteps],
              workflowState: mergedState,
              isStreaming: false
            } : null);
            
            setIsAsking(false);
            
            // 根據不同類型顯示提示
            if (mergedState.current_step === 'need_clarification') {
              showPCMessage('請提供更多資訊以繼續', 'info');
            } else if (mergedState.current_step === 'awaiting_search_approval') {
              showPCMessage('需要批准文檔搜索', 'info');
            } else if (mergedState.current_step === 'awaiting_detail_query_approval') {
              showPCMessage('需要批准詳細查詢', 'info');
            } else {
              showPCMessage('需要批准操作', 'info');
            }
          },

          // Handle errors
          onError: (error) => {
            console.error('❌ Stream error:', error);
            showPCMessage(`問答失敗: ${error}`, 'error');
            setCurrentStreamingSession(null);
            setIsAsking(false);
          }
        }
      );

    } catch (error) {
      console.error('流式問答失敗:', error);
      showPCMessage('問答失敗', 'error');
      setCurrentStreamingSession(null);
      setIsAsking(false);
    }
  };

  // ========== Loading State ==========
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" tip="載入 AI 問答系統..." />
      </div>
    );
  }

  // ========== Main Render ==========
  return (
    <>
    <div className="h-screen flex bg-neo-bg">
      {/* ✅ Left Sidebar - Conversation History (Neo-Brutalism) */}
      {showHistorySidebar && (
        <aside className="w-72 bg-white border-r-2 border-neo-black flex flex-col shadow-[6px_6px_0px_0px_rgba(0,0,0,0.1)]">
          {/* Sidebar Header */}
          <div className="p-4 border-b-2 border-neo-black space-y-3 bg-white z-10">
            {/* NEW CHAT Button - Neo Style */}
            <button
              onClick={startNewConversation}
              disabled={loadingConversations}
              className="w-full py-3 flex items-center justify-center gap-2 bg-neo-black text-neo-primary border-2 border-neo-black font-bold uppercase tracking-wide rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,0.2)] hover:translate-x-[-1px] hover:translate-y-[-1px] hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,0.2)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-[1px_1px_0px_0px_rgba(0,0,0,0.2)] transition-all"
            >
              <i className="ph-bold ph-plus text-lg"></i> New Chat
            </button>
            
            {/* Search Box */}
            <div className="relative group">
              <i className="ph-bold ph-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-black"></i>
              <input
                type="text"
                placeholder="Search history..."
                className="w-full bg-gray-50 border-2 border-gray-200 rounded-lg py-2 pl-9 pr-3 text-sm font-medium outline-none focus:border-black transition-colors"
              />
            </div>
          </div>

          {/* Conversation List - Scrollable */}
          <div className="flex-1 overflow-y-auto p-3 space-y-6" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
            <style>{`.flex-1::-webkit-scrollbar { display: none; }`}</style>
            
            {loadingConversations ? (
              <div className="flex items-center justify-center py-8">
                <Spin size="small" />
              </div>
            ) : conversations.length > 0 ? (
              <>
                {/* Pinned Section */}
                {groupedConversations.pinned.length > 0 && (
                  <div className="space-y-1 mb-4">
                    <div className="flex items-center gap-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-2">
                      <span>Pinned ({groupedConversations.pinned.length})</span>
                      <i className="ph-fill ph-push-pin text-xs"></i>
                    </div>
                    {groupedConversations.pinned.map((conv) => (
                      <div
                        key={conv.id}
                        onClick={() => switchConversation(conv.id)}
                        className={`relative group flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-all ${
                          currentConversationId === conv.id
                            ? 'bg-neo-active text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_#000000] font-bold'
                            : 'border-2 border-transparent hover:bg-gray-100'
                        }`}
                      >
                        <i className={`ph-fill ph-push-pin text-lg flex-shrink-0 ${
                          currentConversationId === conv.id ? 'text-white' : 'text-neo-primary'
                        }`}></i>
                        <div className="flex-1 min-w-0 pr-20">
                          <div className={`truncate text-sm ${currentConversationId === conv.id ? 'font-bold' : 'font-medium'}`}>
                            {conv.title}
                          </div>
                          <div className={`text-[10px] truncate ${
                            currentConversationId === conv.id ? 'text-white text-opacity-80' : 'text-gray-400 group-hover:text-gray-600'
                          }`}>
                            {new Date(conv.updated_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                        {/* Hover Actions */}
                        <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 ${
                          currentConversationId === conv.id ? 'bg-neo-active' : 'bg-gray-100'
                        } pl-2 z-10`}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinConversation(conv.id, conv.is_pinned || false);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Unpin"
                          >
                            <i className="ph-bold ph-push-pin-slash text-sm"></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              console.log('Edit conversation:', conv.id);
                              showPCMessage('Edit 功能開發中', 'info');
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Edit"
                          >
                            <i className="ph-bold ph-pencil-simple text-sm"></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 hover:text-red-500 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Delete"
                          >
                            <i className="ph-bold ph-trash text-sm"></i>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* TODAY Section */}
                {groupedConversations.today.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-2">Today ({groupedConversations.today.length})</div>
                    {groupedConversations.today.map((conv) => (
                    <div
                      key={conv.id}
                      onClick={() => switchConversation(conv.id)}
                      className={`relative group flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-all ${
                        currentConversationId === conv.id
                          ? 'bg-neo-active text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_#000000] font-bold'
                          : 'border-2 border-transparent hover:bg-gray-100'
                      }`}
                    >
                      <i className={`ph-bold ph-chat-text text-lg flex-shrink-0 ${
                        currentConversationId === conv.id ? 'text-white' : 'text-gray-400 group-hover:text-black'
                      }`}></i>
                      <div className="flex-1 min-w-0 pr-20">
                        <div className={`truncate text-sm ${currentConversationId === conv.id ? 'font-bold' : 'font-medium'}`}>
                          {conv.title}
                        </div>
                        <div className={`text-[10px] truncate ${
                          currentConversationId === conv.id ? 'text-white text-opacity-80' : 'text-gray-400 group-hover:text-gray-600'
                        }`}>
                          {new Date(conv.updated_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                      {/* Hover Actions */}
                      <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 ${
                        currentConversationId === conv.id ? 'bg-neo-active' : 'bg-gray-100'
                      } pl-2 z-10`}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            togglePinConversation(conv.id, conv.is_pinned || false);
                          }}
                          className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                            currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                          }`}
                          title={conv.is_pinned ? 'Unpin' : 'Pin'}
                        >
                          <i className={`ph-bold ${conv.is_pinned ? 'ph-push-pin-slash' : 'ph-push-pin'} text-sm`}></i>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            console.log('Edit conversation:', conv.id);
                            showPCMessage('Edit 功能開發中', 'info');
                          }}
                          className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                            currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                          }`}
                          title="Edit"
                        >
                          <i className="ph-bold ph-pencil-simple text-sm"></i>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteConversation(conv.id);
                          }}
                          className={`p-1 rounded hover:bg-black hover:bg-opacity-10 hover:text-red-500 ${
                            currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                          }`}
                          title="Delete"
                        >
                          <i className="ph-bold ph-trash text-sm"></i>
                        </button>
                      </div>
                    </div>
                    ))}
                  </div>
                )}

                {/* YESTERDAY Section */}
                {groupedConversations.yesterday.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-2">Yesterday ({groupedConversations.yesterday.length})</div>
                    {groupedConversations.yesterday.map((conv) => (
                      <div
                        key={conv.id}
                        onClick={() => switchConversation(conv.id)}
                        className={`relative group flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-all ${
                          currentConversationId === conv.id
                            ? 'bg-neo-active text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_#000000] font-bold'
                            : 'border-2 border-transparent hover:bg-gray-100'
                        }`}
                      >
                        <i className={`ph-bold ph-chat-text text-lg flex-shrink-0 ${
                          currentConversationId === conv.id ? 'text-white' : 'text-gray-400 group-hover:text-black'
                        }`}></i>
                        <div className="flex-1 min-w-0 pr-20">
                          <div className={`truncate text-sm ${currentConversationId === conv.id ? 'font-bold' : 'font-medium'}`}>
                            {conv.title}
                          </div>
                          <div className={`text-[10px] truncate ${
                            currentConversationId === conv.id ? 'text-white text-opacity-80' : 'text-gray-400 group-hover:text-gray-600'
                          }`}>
                            {conv.message_count} messages
                          </div>
                        </div>
                        {/* Hover Actions */}
                        <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 ${
                          currentConversationId === conv.id ? 'bg-neo-active' : 'bg-gray-100'
                        } pl-2 z-10`}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinConversation(conv.id, conv.is_pinned || false);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title={conv.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            <i className={`ph-bold ${conv.is_pinned ? 'ph-push-pin-slash' : 'ph-push-pin'} text-sm`}></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              console.log('Edit conversation:', conv.id);
                              showPCMessage('Edit 功能開發中', 'info');
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Edit"
                          >
                            <i className="ph-bold ph-pencil-simple text-sm"></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 hover:text-red-500 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Delete"
                          >
                            <i className="ph-bold ph-trash text-sm"></i>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* PREVIOUS 7 DAYS Section */}
                {groupedConversations.last7Days.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-2">Previous 7 Days ({groupedConversations.last7Days.length})</div>
                    {groupedConversations.last7Days.map((conv) => (
                      <div
                        key={conv.id}
                        onClick={() => switchConversation(conv.id)}
                        className={`relative group flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-all ${
                          currentConversationId === conv.id
                            ? 'bg-neo-active text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_#000000] font-bold'
                            : 'border-2 border-transparent hover:bg-gray-100'
                        }`}
                      >
                        <i className={`ph-bold ph-chat-text text-lg flex-shrink-0 ${
                          currentConversationId === conv.id ? 'text-white' : 'text-gray-400 group-hover:text-black'
                        }`}></i>
                        <div className="flex-1 min-w-0 pr-20">
                          <div className={`truncate text-sm ${currentConversationId === conv.id ? 'font-bold' : 'font-medium'}`}>
                            {conv.title}
                          </div>
                          <div className={`text-[10px] truncate ${
                            currentConversationId === conv.id ? 'text-white text-opacity-80' : 'text-gray-400 group-hover:text-gray-600'
                          }`}>
                            {new Date(conv.updated_at).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' })}
                          </div>
                        </div>
                        {/* Hover Actions */}
                        <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 ${
                          currentConversationId === conv.id ? 'bg-neo-active' : 'bg-gray-100'
                        } pl-2 z-10`}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinConversation(conv.id, conv.is_pinned || false);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title={conv.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            <i className={`ph-bold ${conv.is_pinned ? 'ph-push-pin-slash' : 'ph-push-pin'} text-sm`}></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              console.log('Edit conversation:', conv.id);
                              showPCMessage('Edit 功能開發中', 'info');
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Edit"
                          >
                            <i className="ph-bold ph-pencil-simple text-sm"></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 hover:text-red-500 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Delete"
                          >
                            <i className="ph-bold ph-trash text-sm"></i>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* OLDER Section */}
                {groupedConversations.older.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-2">Older ({groupedConversations.older.length})</div>
                    {groupedConversations.older.map((conv) => (
                      <div
                        key={conv.id}
                        onClick={() => switchConversation(conv.id)}
                        className={`relative group flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-all ${
                          currentConversationId === conv.id
                            ? 'bg-neo-active text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_#000000] font-bold'
                            : 'border-2 border-transparent hover:bg-gray-100'
                        }`}
                      >
                        <i className={`ph-bold ph-chat-text text-lg flex-shrink-0 ${
                          currentConversationId === conv.id ? 'text-white' : 'text-gray-400 group-hover:text-black'
                        }`}></i>
                        <div className="flex-1 min-w-0 pr-20">
                          <div className={`truncate text-sm ${currentConversationId === conv.id ? 'font-bold' : 'font-medium'}`}>
                            {conv.title}
                          </div>
                          <div className={`text-[10px] truncate ${
                            currentConversationId === conv.id ? 'text-white text-opacity-80' : 'text-gray-400 group-hover:text-gray-600'
                          }`}>
                            {new Date(conv.updated_at).toLocaleDateString('zh-TW')}
                          </div>
                        </div>
                        {/* Hover Actions */}
                        <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1 ${
                          currentConversationId === conv.id ? 'bg-neo-active' : 'bg-gray-100'
                        } pl-2 z-10`}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinConversation(conv.id, conv.is_pinned || false);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title={conv.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            <i className={`ph-bold ${conv.is_pinned ? 'ph-push-pin-slash' : 'ph-push-pin'} text-sm`}></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              console.log('Edit conversation:', conv.id);
                              showPCMessage('Edit 功能開發中', 'info');
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Edit"
                          >
                            <i className="ph-bold ph-pencil-simple text-sm"></i>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                            className={`p-1 rounded hover:bg-black hover:bg-opacity-10 hover:text-red-500 ${
                              currentConversationId === conv.id ? 'text-white' : 'text-gray-600'
                            }`}
                            title="Delete"
                          >
                            <i className="ph-bold ph-trash text-sm"></i>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暫無對話記錄"
                className="mt-8"
              />
            )}
          </div>

          {/* User Settings Footer - Removed */}
        </aside>
      )}

      {/* ✅ Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-neo-white border-b-3 border-neo-black px-6 py-4 flex items-center justify-between shadow-neo-sm">
          <div className="flex items-center gap-3">
            <Button
              type="text"
              icon={<i className={`ph ${showHistorySidebar ? 'ph-sidebar-simple' : 'ph-sidebar'}`}></i>}
              onClick={() => setShowHistorySidebar(!showHistorySidebar)}
              className="border-2 border-neo-black"
            />
            <div className="w-10 h-10 bg-neo-primary border-2 border-neo-black rounded-lg flex items-center justify-center font-display font-bold text-lg shadow-neo-sm">
              S
            </div>
            <div>
              <h1 className="font-display font-bold text-lg uppercase tracking-tight">AI WORKSPACE</h1>
              <p className="text-xs text-gray-600 font-mono">Sortify Intelligence System</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Settings removed */}
          </div>
        </header>

        {/* ✅ Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* 歷史對話記錄 - 始終顯示 */}
          {qaHistory.length > 0 && (
            <div className="space-y-6">
              {qaHistory.map((session) => (
                <div key={session.id} className="space-y-6">
                  {/* User Question */}
                  <div className="flex justify-end">
                    <div className="max-w-[70%] bg-neo-black text-white px-5 py-3 rounded-2xl rounded-br-none shadow-neo-md">
                      <div className="flex items-start gap-3">
                        <Text className="text-white font-medium flex-1">{session.question}</Text>
                        <UserOutlined className="text-white mt-1" />
                      </div>
                    </div>
                  </div>

                  {/* AI Response */}
                  <div className="flex justify-start gap-4">
                    <div className="w-10 h-10 bg-neo-primary border-2 border-neo-black rounded-lg flex-shrink-0 flex items-center justify-center font-display font-bold shadow-neo-sm">
                      AI
                    </div>
                    <div className="flex-1 min-w-0">
                      {/* Reasoning Chain */}
                      {session.reasoningSteps && session.reasoningSteps.length > 0 && (
                        <ReasoningChainDisplay
                          steps={session.reasoningSteps}
                          isStreaming={false}
                          onCitationClick={(docId) => handleCitationClick(docId, session.documentPoolSnapshot)}
                        />
                      )}

                      {/* Answer */}
                      <StreamedAnswer
                        content={session.answer}
                        isStreaming={false}
                        onCitationClick={(docId) => handleCitationClick(docId, session.documentPoolSnapshot)}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 當前流式會話 - 在歷史記錄之後顯示 */}
          {currentStreamingSession && (
            <div className="space-y-6">
              {/* User Question */}
              <div className="flex justify-end">
                <div className="max-w-[70%] bg-neo-black text-white px-5 py-3 rounded-2xl rounded-br-none shadow-neo-md">
                  <div className="flex items-start gap-3">
                    <Text className="text-white font-medium flex-1">{currentStreamingSession.question}</Text>
                    <UserOutlined className="text-white mt-1" />
                  </div>
                </div>
              </div>

              {/* AI Response */}
              <div className="flex justify-start gap-4">
                <div className="w-10 h-10 bg-neo-primary border-2 border-neo-black rounded-lg flex-shrink-0 flex items-center justify-center font-display font-bold shadow-neo-sm">
                  AI
                </div>
                <div className="flex-1 min-w-0">
                  {/* Reasoning Chain */}
                  {currentStreamingSession.reasoningSteps.length > 0 && (
                    <ReasoningChainDisplay
                      steps={currentStreamingSession.reasoningSteps}
                      isStreaming={currentStreamingSession.isStreaming && !currentStreamingSession.answer}
                      processingTime={(Date.now() - currentStreamingSession.startTime) / 1000}
                      onApprove={handleApprove}
                      isApproving={isAsking}
                      onClarificationResponse={(response) => setQuestion(response)}
                      // ⭐⭐ 使用當前輪次的文檔快照（如果有），否則使用全局文檔池
                      onCitationClick={(docId) => handleCitationClick(docId, currentStreamingSession.currentRoundDocuments || documentPool)}
                    />
                  )}

                  {/* Streamed Answer - 澄清請求時不顯示原始answer，因為已有澄清卡片 */}
                  {currentStreamingSession.answer && 
                   !currentStreamingSession.reasoningSteps.some(
                     step => step.type === 'approval' && 
                             step.status === 'active' && 
                             step.detail?.current_step === 'need_clarification'
                   ) && (
                    <StreamedAnswer
                      content={currentStreamingSession.answer}
                      isStreaming={currentStreamingSession.isStreaming}
                      // ⭐⭐ 使用當前輪次的文檔快照（如果有），否則使用全局文檔池
                      onCitationClick={(docId) => handleCitationClick(docId, currentStreamingSession.currentRoundDocuments || documentPool)}
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Empty State - 只在沒有歷史記錄且沒有當前會話時顯示 */}
          {qaHistory.length === 0 && !currentStreamingSession && (
            <div className="text-center mt-20">
              <RobotOutlined className="text-6xl text-neo-primary mb-4" />
              <h2 className="font-display font-bold text-2xl mb-2 uppercase">AI 智能助手</h2>
              <Text className="text-gray-600">您可以問我任何關於文檔的問題</Text>
            </div>
          )}

          {/* Auto Scroll Anchor */}
          <div ref={messagesEndRef} />
          
          {/* 輸入框區域 - 跟隨內容流動 */}
          <div className="mt-6 sticky bottom-0 pb-6 z-50">
            <div className="max-w-4xl mx-auto">
              {/* 主輸入卡片 - Neo-Brutalism 風格 */}
              <div className="bg-white border-3 border-neo-black shadow-[6px_6px_0px_0px_#000000] overflow-hidden">
                
                {/* CONTEXT 區域 - 簡潔版 */}
                {documentPool.length > 0 && (
                  <div className="bg-gray-50 border-b-3 border-neo-black">
                    {/* 文檔標籤行 */}
                    <div className="px-4 py-2.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* CONTEXT 標籤 */}
                        <div className="px-2 py-1 bg-gray-200 text-gray-600 text-[10px] font-bold uppercase tracking-wider">
                          CONTEXT
                        </div>
                        
                        {/* 文檔標籤 */}
                        {documentPool.slice(0, 3).map((doc: any, index: number) => {
                          // 根據文件類型決定圖標和顏色
                          const getFileIcon = (filename: string) => {
                            const ext = filename.split('.').pop()?.toLowerCase();
                            if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) {
                              return { icon: 'ph-image', color: 'text-orange-500' };
                            } else if (['pdf'].includes(ext || '')) {
                              return { icon: 'ph-file-pdf', color: 'text-red-500' };
                            } else if (['txt', 'md'].includes(ext || '')) {
                              return { icon: 'ph-file-text', color: 'text-blue-500' };
                            } else if (['doc', 'docx'].includes(ext || '')) {
                              return { icon: 'ph-file-doc', color: 'text-blue-600' };
                            } else if (['xls', 'xlsx'].includes(ext || '')) {
                              return { icon: 'ph-file-xls', color: 'text-green-600' };
                            }
                            return { icon: 'ph-file', color: 'text-gray-500' };
                          };
                          
                          const { icon, color } = getFileIcon(doc.filename);
                          
                          return (
                            <div
                              key={doc.document_id}
                              onClick={() => handleViewDocumentDetail(doc.document_id)}
                              className="group relative flex items-center gap-1.5 px-3 py-1.5 bg-white border-2 border-neo-black text-xs font-bold hover:bg-neo-hover transition-all cursor-pointer"
                              title={`${doc.filename}\n相關性: ${(doc.relevance_score * 100).toFixed(0)}%`}
                            >
                              <i className={`ph-fill ${icon} ${color}`}></i>
                              <span className="max-w-[140px] truncate">{doc.filename}</span>
                              {/* 移除按鈕 */}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemoveFromDocumentPool(doc.document_id);
                                }}
                                className="ml-1 opacity-30 group-hover:opacity-100 hover:text-red-600 hover:scale-125 transition-all"
                                title="移除"
                              >
                                <i className="ph-bold ph-x text-[10px]"></i>
                              </button>
                            </div>
                          );
                        })}
                        
                        {/* 展開/收起按鈕 */}
                        {documentPool.length > 3 && (
                          <button
                            onClick={() => setShowDocumentPool(!showDocumentPool)}
                            className="px-3 py-1.5 bg-neo-black text-white border-2 border-neo-black text-xs font-bold hover:bg-neo-primary hover:text-black transition-all flex items-center gap-1"
                            title={showDocumentPool ? "收起文檔" : "顯示所有文檔"}
                          >
                            {showDocumentPool ? (
                              <>
                                <i className="ph-bold ph-caret-up text-[10px]"></i>
                                <span>收起</span>
                              </>
                            ) : (
                              <>
                                <span>+{documentPool.length - 3} more</span>
                                <i className="ph-bold ph-caret-down text-[10px]"></i>
                              </>
                            )}
                          </button>
                        )}
                        
                        {/* 展開時顯示剩餘的文檔 */}
                        {showDocumentPool && documentPool.slice(3).map((doc: any) => {
                          const getFileIcon = (filename: string) => {
                            const ext = filename.split('.').pop()?.toLowerCase();
                            if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) {
                              return { icon: 'ph-image', color: 'text-orange-500' };
                            } else if (['pdf'].includes(ext || '')) {
                              return { icon: 'ph-file-pdf', color: 'text-red-500' };
                            } else if (['txt', 'md'].includes(ext || '')) {
                              return { icon: 'ph-file-text', color: 'text-blue-500' };
                            } else if (['doc', 'docx'].includes(ext || '')) {
                              return { icon: 'ph-file-doc', color: 'text-blue-600' };
                            } else if (['xls', 'xlsx'].includes(ext || '')) {
                              return { icon: 'ph-file-xls', color: 'text-green-600' };
                            }
                            return { icon: 'ph-file', color: 'text-gray-500' };
                          };
                          
                          const { icon, color } = getFileIcon(doc.filename);
                          
                          return (
                            <div
                              key={doc.document_id}
                              onClick={() => handleViewDocumentDetail(doc.document_id)}
                              className="group relative flex items-center gap-1.5 px-3 py-1.5 bg-white border-2 border-neo-black text-xs font-bold hover:bg-neo-hover transition-all cursor-pointer"
                              title={`${doc.filename}\n相關性: ${(doc.relevance_score * 100).toFixed(0)}%`}
                            >
                              <i className={`ph-fill ${icon} ${color}`}></i>
                              <span className="max-w-[140px] truncate">{doc.filename}</span>
                              {/* 移除按鈕 */}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemoveFromDocumentPool(doc.document_id);
                                }}
                                className="ml-1 opacity-30 group-hover:opacity-100 hover:text-red-600 hover:scale-125 transition-all"
                                title="移除"
                              >
                                <i className="ph-bold ph-x text-[10px]"></i>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
                
                {/* 輸入區域 */}
                <div className="px-4 py-3 bg-white">
                  {/* 輸入框 - 占滿整行 */}
                  <FileMentionInput
                    value={question}
                    onChange={setQuestion}
                    mentionedFiles={mentionedFiles}
                    onMentionedFilesChange={setMentionedFiles}
                    placeholder={
                      pendingWorkflow?.state?.current_step === 'need_clarification'
                        ? "輸入您的回答..."
                        : "Ask AI anything... (Type @ to tag files)"
                    }
                    disabled={isAsking}
                    minHeight="60px"
                    className=""
                    enableSemanticSearch={enableSemanticSearch}
                    showHint={false}
                    onFileSelected={(file) => {
                      // ✅ 立即添加到文件池
                      console.log('📎 @ 選擇文件，立即添加到文件池:', file);
                      const newDoc = {
                        document_id: file.id,
                        filename: file.filename,
                        summary: file.summary || '',
                        key_concepts: file.key_concepts || [],
                        relevance_score: 1.0,
                        access_count: 0
                      };
                      
                      setDocumentPool(prev => {
                        const existingIds = new Set(prev.map(d => d.document_id));
                        if (existingIds.has(newDoc.document_id)) {
                          console.log('⚠️ 文件已存在於文件池，跳過');
                          return prev;
                        }
                        console.log('✅ 添加文件到文件池');
                        return [newDoc, ...prev];
                      });
                    }}
                  />
                </div>
                
                {/* 底部狀態欄 - @ 提示 + RAG 模式 + 提交按鈕 */}
                <div className="px-4 py-2.5 bg-gray-50 border-t-2 border-gray-200 flex items-center justify-between">
                  {/* 左側：@ 提示 + RAG 模式 */}
                  <div className="flex items-center gap-3 text-[11px] font-bold">
                    {/* @ 提示 */}
                    <div className="flex items-center gap-1.5 text-gray-600">
                      <i className="ph-bold ph-at text-neo-active"></i>
                      <span>輸入 <span className="text-neo-black">@</span> 立即搜索文件（{enableSemanticSearch ? '文件名 + 語義搜索' : '僅文件名搜索'}）</span>
                    </div>
                    
                    {/* RAG 模式 */}
                    <button
                      onClick={() => setEnableSemanticSearch(!enableSemanticSearch)}
                      className="flex items-center gap-1.5 text-gray-600 hover:text-neo-black transition-colors cursor-pointer"
                      title="點擊切換 RAG 模式"
                    >
                      <i className={`ph-bold ${enableSemanticSearch ? 'ph-lightning-fill text-neo-active' : 'ph-lightning text-gray-400'}`}></i>
                      <span>RAG: <span className="text-neo-black">{enableSemanticSearch ? 'Hybrid' : 'Basic'}</span></span>
                    </button>
                  </div>
                  
                  {/* 右側：提交按鈕 */}
                  <button
                    onClick={() => {
                      if (pendingWorkflow?.state?.current_step === 'need_clarification') {
                        handleClarificationSubmit();
                      } else {
                        handleAskQuestionStream();
                      }
                    }}
                    disabled={!question.trim() || isAsking}
                    className={`w-10 h-10 flex items-center justify-center border-2 border-neo-black transition-all ${
                      !question.trim() || isAsking
                        ? 'bg-gray-300 cursor-not-allowed opacity-50'
                        : 'bg-neo-black shadow-neo-sm hover:shadow-neo-md hover:-translate-x-[1px] hover:-translate-y-[1px] active:shadow-none active:translate-x-[2px] active:translate-y-[2px]'
                    }`}
                  >
                    {isAsking ? (
                      <Spin size="small" />
                    ) : (
                      <div className="w-0 h-0 border-l-[10px] border-l-neo-primary border-t-[7px] border-t-transparent border-b-[7px] border-b-transparent ml-0.5"></div>
                    )}
                  </button>
                </div>
              </div>
              {/* 輸入框主容器結束 */}
            </div>
            {/* max-w-4xl 結束 */}
          </div>
          {/* 輸入框區域結束 */}
        </div>
        {/* max-w-5xl 容器結束 */}
        </div>
        {/* Main Content Area 結束 */}
      </div>
      {/* flex-1 flex flex-col 結束 */}
    </div>
    {/* h-screen flex 結束 */}

    {/* Settings Modal removed */}

    {/* ✅ AI Context Preview Drawer - Neo-Brutalism Style */}
    <Drawer
      title={
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-neo-primary rounded-full animate-pulse"></div>
          <span className="font-display font-bold uppercase text-sm">AI CONTEXT</span>
        </div>
      }
      placement="right"
      width={500}
      onClose={() => setPreviewDrawerOpen(false)}
      open={previewDrawerOpen}
      className="font-sans neo-drawer"
    >
      {previewDoc ? (
        <div className="space-y-4">
          {/* Document Info Card */}
          <div className="bg-white border-3 border-neo-black rounded-none overflow-hidden shadow-neo-md">
            {/* Header */}
            <div className="bg-neo-black text-white px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                <FileTextOutlined className="text-lg" />
                <span className="font-display font-bold text-sm uppercase">
                  {previewDoc?.filename}
                </span>
              </div>
              <div className="flex gap-2 text-xs">
                <span className="bg-neo-primary text-neo-black px-2 py-1 border-2 border-neo-black font-bold uppercase">
                  CITED
                </span>
                {previewDoc?.analysis?.ai_analysis_output?.confidence_level && (
                  <span className="bg-neo-active text-white px-2 py-1 border-2 border-neo-black font-bold uppercase">
                    {previewDoc.analysis.ai_analysis_output.confidence_level}
                  </span>
                )}
              </div>
            </div>
            
            {/* AI Context Section */}
            <div className="p-4 space-y-4">
              {/* Why This Document */}
              {previewDoc?.analysis?.ai_analysis_output?.key_information?.content_summary && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <i className="ph-bold ph-brain text-neo-primary"></i>
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-700">
                      AI 摘要
                    </span>
                  </div>
                  <div className="bg-gray-50 border-2 border-gray-300 p-3 text-sm text-gray-800 leading-relaxed">
                    {previewDoc.analysis.ai_analysis_output.key_information.content_summary}
                  </div>
                </div>
              )}

              {/* Key Information Provided to AI */}
              {previewDoc?.analysis?.ai_analysis_output?.key_information && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <i className="ph-bold ph-list-bullets text-neo-active"></i>
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-700">
                      提供給 AI 的關鍵信息
                    </span>
                  </div>
                  <div className="space-y-2">
                    {previewDoc.analysis.ai_analysis_output.key_information.main_topics?.length > 0 && (
                      <div className="bg-white border-2 border-neo-black p-3">
                        <div className="text-xs font-bold text-gray-600 mb-1">主題</div>
                        <div className="flex flex-wrap gap-2">
                          {previewDoc.analysis.ai_analysis_output.key_information.main_topics.slice(0, 5).map((topic: string, idx: number) => (
                            <span key={idx} className="bg-neo-hover text-neo-black px-2 py-1 text-xs font-bold border-2 border-neo-black">
                              {topic}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {previewDoc.analysis.ai_analysis_output.key_information.key_concepts?.length > 0 && (
                      <div className="bg-white border-2 border-neo-black p-3">
                        <div className="text-xs font-bold text-gray-600 mb-1">關鍵概念</div>
                        <div className="flex flex-wrap gap-2">
                          {previewDoc.analysis.ai_analysis_output.key_information.key_concepts.slice(0, 5).map((concept: string, idx: number) => (
                            <span key={idx} className="bg-neo-active text-white px-2 py-1 text-xs font-bold border-2 border-neo-black">
                              {concept}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata for AI */}
              {previewDoc?.analysis?.ai_analysis_output && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <i className="ph-bold ph-info text-gray-500"></i>
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-700">
                      文檔元數據
                    </span>
                  </div>
                  <div className="bg-gray-50 border-2 border-gray-300 p-3 text-xs space-y-1">
                    {previewDoc.analysis.ai_analysis_output.content_type && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">文檔類型:</span>
                        <span className="font-bold">{previewDoc.analysis.ai_analysis_output.content_type}</span>
                      </div>
                    )}
                    {previewDoc.analysis.ai_analysis_output.confidence_level && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">分析置信度:</span>
                        <span className="font-bold">{previewDoc.analysis.ai_analysis_output.confidence_level}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            
            {/* Footer Action */}
            <div className="border-t-3 border-neo-black bg-gray-50 px-4 py-3">
              <button 
                className="w-full bg-neo-primary border-2 border-neo-black text-neo-black font-bold text-xs uppercase px-4 py-2 shadow-neo-sm hover:shadow-neo-md hover:translate-x-[-2px] hover:translate-y-[-2px] transition-all flex items-center justify-center gap-2"
                onClick={() => {
                  // 先關閉 Drawer，再打開 Modal（確保 Modal 在最上層）
                  setPreviewDrawerOpen(false);
                  handleViewDocumentDetail(previewDoc.id);
                }}
              >
                VIEW FULL DETAILS
                <i className="ph-bold ph-arrow-square-out"></i>
              </button>
            </div>
          </div>
        </div>
      ) : (
        <Empty description="無文檔預覽" />
      )}
    </Drawer>

    {/* Document Details Modal */}
    <DocumentDetailsModal
      document={selectedDocForDetail}
      isOpen={!!selectedDocForDetail}
      onClose={() => setSelectedDocForDetail(null)}
    />

      {/* 文件搜索弹窗 */}
      <FileSearchModal
        isOpen={showFileSearchModal}
        onClose={() => setShowFileSearchModal(false)}
        onSelect={(file) => {
          // 将选中的文件添加到 mentionedFiles
          const mentionedFile: MentionedFile = {
            id: file.id,
            filename: file.filename,
            summary: file.enriched_data?.summary || (file.analysis?.ai_analysis_output as any)?.key_information?.content_summary,
            key_concepts: (file.enriched_data as any)?.key_concepts || (file.analysis?.ai_analysis_output as any)?.key_information?.key_concepts || [],
            file_type: file.file_type || undefined,
          };
          
          // 检查是否已经添加
          if (!mentionedFiles.some(f => f.id === mentionedFile.id)) {
            setMentionedFiles(prev => [...prev, mentionedFile]);
            showPCMessage(`已添加文件: ${file.filename}`, 'success');
          } else {
            showPCMessage('此文件已经添加', 'info');
          }
        }}
        showOnlyVectorized={true}
      />
    </>
  );
};

export default AIQAPageNeo;
