import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Alert,
  Space,
  List,
  Spin,
  Empty,
  Tooltip,
  Input,
  Typography,
  Tag,
  Steps,
  Card,
  Button,
  Collapse,
  Modal,
  Drawer
} from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  RobotOutlined,
  SendOutlined,
  BulbOutlined,
  FileTextOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  ClearOutlined,
  CheckCircleOutlined,
  UserOutlined,
  RetweetOutlined,
  EditOutlined,
  QuestionCircleOutlined,
  DeleteOutlined,
  CloseCircleOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import type {
  AIQAResponse,
  VectorDatabaseStats,
  QueryRewriteResult,
  LLMContextDocument,
  SemanticContextDocument,
  AIQARequestUnified,
  AIResponse,
  Document
} from '../types/apiTypes';
import { askAIQuestionUnified } from '../services/unifiedAIService';
import { getVectorDatabaseStats } from '../services/vectorDBService';
import { getDocumentsByIds, getDocumentById } from '../services/documentService';
import AIQASettings, { AIQASettingsConfig, defaultAIQASettings, AIQAPresetModes } from '../components/settings/AIQASettings';
import { DocumentTypeIcon } from '../components/document';
import AIQADataPanel from '../components/AIQADataPanel';
import conversationService from '../services/conversationService';
import type { Conversation } from '../types/conversation';
import QAAnalyticsPanel from '../components/QAAnalyticsPanel';
import QAWorkflowDisplay from '../components/QAWorkflowDisplay';
import type { WorkflowState } from '../types/qaWorkflow';
import '../styles/qaWorkflow.css';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;
const { Panel } = Collapse;

interface AIQAPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface QASession {
  id: string;
  question: string;
  answer: string;
  timestamp: Date;
  sourceDocuments: string[];
  tokensUsed: number;
  processingTime: number;
  confidenceScore?: number;
  queryRewriteResult?: QueryRewriteResult | null;
  llmContextDocuments?: LLMContextDocument[] | null;
  semanticSearchContexts?: SemanticContextDocument[] | null;
  detailedDocumentDataFromAiQuery?: any[] | null;
  detailedQueryReasoning?: string | null;
  sessionId?: string;
  usedSettings?: AIQASettingsConfig;
  // 新增:工作流相關
  classification?: any;
  workflowState?: any;
  nextAction?: string;
}

// Markdown 渲染組件
const MarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  // 預處理內容：處理換行符和格式
  const processedContent = content.replace(/\\n/g, '\n');
  
  return (
    <div 
      className="markdown-content"
      style={{
        color: '#262626', // 更深的文字顏色
        fontSize: '14px',
        lineHeight: '1.6'
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 自定義樣式
          h1: (props) => <h1 style={{fontSize: '1.5em', fontWeight: 'bold', marginBottom: '0.5em', color: '#262626'}} {...props} />,
          h2: (props) => <h2 style={{fontSize: '1.3em', fontWeight: 'bold', marginBottom: '0.4em', color: '#262626'}} {...props} />,
          h3: (props) => <h3 style={{fontSize: '1.1em', fontWeight: 'bold', marginBottom: '0.3em', color: '#262626'}} {...props} />,
          p: (props) => <p style={{marginBottom: '0.8em', lineHeight: '1.6', color: '#262626', whiteSpace: 'pre-wrap'}} {...props} />,
          ul: (props) => <ul style={{marginBottom: '0.8em', paddingLeft: '1.5em', color: '#262626'}} {...props} />,
          ol: (props) => <ol style={{marginBottom: '0.8em', paddingLeft: '1.5em', color: '#262626'}} {...props} />,
          li: (props) => <li style={{marginBottom: '0.2em', color: '#262626'}} {...props} />,
          blockquote: (props) => (
            <blockquote 
              style={{
                borderLeft: '4px solid #d9d9d9',
                paddingLeft: '1em',
                margin: '1em 0',
                color: '#595959',
                fontStyle: 'italic',
                backgroundColor: '#fafafa',
                borderRadius: '4px',
                padding: '1em'
              }} 
              {...props} 
            />
          ),
          code: (props) => {
            const { children, className, ...rest } = props;
            const isInline = typeof children === 'string' && !children.includes('\n');
            
            return isInline ? (
              <code 
                style={{
                  backgroundColor: '#f5f5f5',
                  padding: '0.2em 0.4em',
                  borderRadius: '3px',
                  fontSize: '0.9em',
                  color: '#d32f2f',
                  border: '1px solid #e8e8e8'
                }}
                className={className}
              >
                {children}
              </code>
            ) : (
              <pre 
                style={{
                  backgroundColor: '#f5f5f5',
                  padding: '1em',
                  borderRadius: '6px',
                  fontSize: '0.9em',
                  overflow: 'auto',
                  border: '1px solid #e8e8e8',
                  marginBottom: '1em'
                }}
                className={className}
              >
                <code style={{ color: '#262626' }}>{children}</code>
              </pre>
            );
          },
          table: (props) => (
            <table 
              style={{
                borderCollapse: 'collapse',
                width: '100%',
                marginBottom: '1em',
                border: '1px solid #d9d9d9'
              }} 
              {...props} 
            />
          ),
          th: (props) => (
            <th 
              style={{
                border: '1px solid #d9d9d9',
                padding: '0.5em',
                backgroundColor: '#fafafa',
                fontWeight: 'bold',
                color: '#262626'
              }} 
              {...props} 
            />
          ),
          td: (props) => (
            <td 
              style={{
                border: '1px solid #d9d9d9',
                padding: '0.5em',
                color: '#262626'
              }} 
              {...props} 
            />
          )
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
};


const AIQAPage: React.FC<AIQAPageProps> = ({ showPCMessage }) => {
  // 狀態管理
  const [vectorStats, setVectorStats] = useState<VectorDatabaseStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // AI 問答相關狀態
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [qaHistory, setQAHistory] = useState<QASession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  
  // 對話管理狀態
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [loadingConversations, setLoadingConversations] = useState(false);
  
  // 新增：AI 問答設定狀態
  const [aiQASettings, setAIQASettings] = useState<AIQASettingsConfig>(() => {
    // 從 localStorage 讀取用戶的偏好設定
    const savedSettings = localStorage.getItem('aiqa-settings');
    if (savedSettings) {
      try {
        return { ...defaultAIQASettings, ...JSON.parse(savedSettings) };
      } catch (error) {
        console.warn('Failed to parse saved AI QA settings:', error);
      }
    }
    return defaultAIQASettings;
  });
  
  // UI 狀態
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [referenceDocuments, setReferenceDocuments] = useState<Record<string, Document>>({});
  
  // 文件內容查看模態框狀態
  const [viewingDocument, setViewingDocument] = useState<Document | null>(null);
  const [isLoadingDocumentContent, setIsLoadingDocumentContent] = useState(false);
  
  // 統計面板狀態
  const [showAnalytics, setShowAnalytics] = useState(false);
  
  // 澄清輸入狀態
  const [clarificationInput, setClarificationInput] = useState('');
  
  // 工作流狀態管理
  const [pendingWorkflow, setPendingWorkflow] = useState<{
    request: AIQARequestUnified;
    response: AIQAResponse;
  } | null>(null);
  
  // 檢查是否有待處理的澄清問題
  const hasPendingClarification = qaHistory.length > 0 && 
    qaHistory[0].classification?.intent === 'clarification_needed' &&
    qaHistory[0].nextAction === 'provide_clarification';
  
  // 檢查是否有待處理的搜索批准
  const hasPendingSearchApproval = pendingWorkflow?.response?.workflow_state?.current_step === 'awaiting_search_approval';

  // 示例問題
  const exampleQuestions = [
    "文檔中提到的主要結論是什麼？",
    "有沒有關於財務數據的內容？",
    "請總結文檔的核心內容",
    "文檔中提到哪些重要的日期？",
    "請列出文檔中的主要人物或組織",
    "有什麼需要注意的風險或問題嗎？"
  ];

  // 載入對話列表
  const loadConversations = useCallback(async () => {
    try {
      setLoadingConversations(true);
      const response = await conversationService.listConversations(0, 50);
      setConversations(response.conversations);
    } catch (error) {
      console.error('載入對話列表失敗:', error);
      showPCMessage('載入對話列表失敗', 'error');
    } finally {
      setLoadingConversations(false);
    }
  }, [showPCMessage]);

  // 載入初始數據
  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const stats = await getVectorDatabaseStats();
      setVectorStats(stats);
      await loadConversations();
    } catch (error) {
      console.error('載入 AI 問答頁面數據失敗:', error);
      showPCMessage('載入數據失敗', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [showPCMessage, loadConversations]);

  // 保存設定到 localStorage
  const handleSettingsChange = (newSettings: AIQASettingsConfig) => {
    setAIQASettings(newSettings);
    localStorage.setItem('aiqa-settings', JSON.stringify(newSettings));
  };

  // 重置設定
  const handleSettingsReset = () => {
    localStorage.removeItem('aiqa-settings');
    showPCMessage('已重置為預設設定', 'success');
  };

  // AI 問答處理
  const handleAskQuestion = async (customQuestion?: string) => {
    const questionToAsk = customQuestion || question.trim();
    
    if (!questionToAsk.trim()) {
      showPCMessage('請輸入問題', 'error');
      return;
    }

    if (!vectorStats || vectorStats.total_vectors === 0) {
      showPCMessage('向量數據庫中沒有可用的文檔，請先向量化一些文檔', 'error');
      return;
    }

    try {
      setIsAsking(true);
      
      // 如果沒有當前對話，先創建一個新對話
      let conversationId = currentConversationId;
      if (!conversationId) {
        try {
          const newConversation = await conversationService.createConversation(questionToAsk);
          conversationId = newConversation.id;
          setCurrentConversationId(conversationId);
          
          // 優化: 只將新對話添加到列表,而不是重新載入所有對話
          setConversations(prev => [newConversation, ...prev]);
        } catch (error) {
          console.error('創建對話失敗:', error);
          showPCMessage('創建對話失敗，但將繼續處理問題', 'info');
        }
      }
      
      const request: AIQARequestUnified = {
        question: questionToAsk,
        session_id: currentSessionId || undefined,
        conversation_id: conversationId || undefined,
        // 使用用戶設定的參數
        use_semantic_search: aiQASettings.use_semantic_search,
        use_structured_filter: aiQASettings.use_structured_filter,
        context_limit: aiQASettings.context_limit,
        use_ai_detailed_query: aiQASettings.use_ai_detailed_query,
        detailed_text_max_length: aiQASettings.detailed_text_max_length,
        max_chars_per_doc: aiQASettings.max_chars_per_doc,
        query_rewrite_count: aiQASettings.query_rewrite_count,
        max_documents_for_selection: aiQASettings.max_documents_for_selection,
        similarity_threshold: aiQASettings.similarity_threshold,
        ai_selection_limit: aiQASettings.ai_selection_limit,
        enable_query_expansion: aiQASettings.enable_query_expansion,
        context_window_overlap: aiQASettings.context_window_overlap,
      };
      const unifiedResponse: AIResponse<AIQAResponse> = await askAIQuestionUnified(request);
      
      if (!unifiedResponse.success || !unifiedResponse.content) {
        const errorMessage = unifiedResponse.error_message || 'AI 問答失敗，未收到預期內容。';
        console.error('AI 問答失敗:', errorMessage, unifiedResponse);
        showPCMessage(errorMessage, 'error');
        setIsAsking(false);
        return;
      }
      
      const responseContent = unifiedResponse.content;

      // 🔍 調試：查看後端返回的完整workflow_state
      if (responseContent.workflow_state) {
        console.log('📥 收到的 workflow_state:', JSON.stringify(responseContent.workflow_state, null, 2));
      }
      
      // 檢查是否需要工作流交互(批准、澄清等)
      const needsInteraction = responseContent.workflow_state?.current_step === 'awaiting_search_approval' ||
                               responseContent.workflow_state?.current_step === 'awaiting_detail_query_approval' ||  // ⭐ 新增
                               responseContent.workflow_state?.current_step === 'need_clarification';
      
      console.log('🔍 needsInteraction檢查:', {
        current_step: responseContent.workflow_state?.current_step,
        needsInteraction: needsInteraction
      });
      
      if (needsInteraction) {
        // 轉換蛇形命名為駝峰命名（後端用current_step，前端用currentStep）
        const normalizedWorkflowState = {
          ...responseContent.workflow_state,
          currentStep: responseContent.workflow_state.current_step,
          clarificationQuestion: responseContent.workflow_state.clarification_question,
          suggestedResponses: responseContent.workflow_state.suggested_responses,
          // 詳細查詢相關
          targetDocuments: responseContent.workflow_state.target_documents,
          documentNames: responseContent.workflow_state.document_names,
          queryType: responseContent.workflow_state.query_type
        };
        
        // 保存待處理的工作流狀態
        setPendingWorkflow({
          request: request,
          response: {
            ...responseContent,
            workflow_state: normalizedWorkflowState
          }
        });
        
        console.log('✅ 設置待處理工作流:', normalizedWorkflowState);
        
        // 重要：需要在歷史中顯示用戶問題，這樣用戶才知道自己問了什麼
        // 但只添加用戶問題，不添加澄清回答（避免重複顯示）
        const interactionSession: QASession = {
          id: `qa_${Date.now()}`,
          question: questionToAsk,
          answer: '', // 暫時不顯示答案（工作流UI會處理）
          timestamp: new Date(),
          sourceDocuments: [],
          tokensUsed: 0,
          processingTime: 0,
          classification: responseContent.classification,
          workflowState: normalizedWorkflowState,
          nextAction: responseContent.next_action
        };
        
        setQAHistory(prev => [interactionSession, ...prev]);
        setQuestion('');
        setIsAsking(false);
        return; // 等待用戶交互
      }

      // 正常完成的響應,添加到歷史
      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: questionToAsk,
        answer: responseContent.answer,
        timestamp: new Date(),
        sourceDocuments: responseContent.source_documents,
        tokensUsed: responseContent.tokens_used,
        processingTime: responseContent.processing_time,
        confidenceScore: responseContent.confidence_score || undefined,
        queryRewriteResult: responseContent.query_rewrite_result || null,
        llmContextDocuments: responseContent.llm_context_documents || null,
        semanticSearchContexts: responseContent.semantic_search_contexts || null,
        detailedDocumentDataFromAiQuery: responseContent.detailed_document_data_from_ai_query || null,
        detailedQueryReasoning: responseContent.detailed_query_reasoning || null,
        sessionId: responseContent.session_id || undefined,
        usedSettings: { ...aiQASettings },
        classification: responseContent.classification,
        workflowState: responseContent.workflow_state,
        nextAction: responseContent.next_action
      };

      setQAHistory(prev => [newSession, ...prev]);
      setCurrentSessionId(responseContent.session_id || null);
      setQuestion('');
      setPendingWorkflow(null); // 清除待處理狀態
      
      // 優化: 只更新當前對話的時間戳,不重新載入所有對話
      if (conversationId) {
        setConversations(prev => 
          prev.map(conv => 
            conv.id === conversationId
              ? { ...conv, updated_at: new Date().toISOString(), message_count: (conv.message_count || 0) + 2 }
              : conv
          )
        );
        // 注意: cached_documents 會在切換對話時從後端載入,無需每次都重新載入所有對話
      }
      
      showPCMessage(`問答完成，使用了 ${responseContent.tokens_used} 個 token`, 'success');
    } catch (error) {
      console.error('AI 問答失敗:', error);
      const message = error instanceof Error ? error.message : 'AI 問答時發生未知錯誤';
      showPCMessage(message, 'error');
    } finally {
      setIsAsking(false);
    }
  };

  // 使用示例問題
  const handleExampleQuestion = (exampleQuestion: string) => {
    setQuestion(exampleQuestion);
  };

  // 處理搜索批准
  const handleApproveSearch = async () => {
    if (!pendingWorkflow) {
      console.error('沒有待處理的工作流');
      return;
    }

    try {
      setIsAsking(true);
      
      // 創建新請求,帶上批准動作
      const approvedRequest: AIQARequestUnified = {
        ...pendingWorkflow.request,
        workflow_action: 'approve_search'
      };

      const unifiedResponse: AIResponse<AIQAResponse> = await askAIQuestionUnified(approvedRequest);
      
      if (!unifiedResponse.success || !unifiedResponse.content) {
        showPCMessage('批准後處理失敗', 'error');
        return;
      }

      const responseContent = unifiedResponse.content;

      // 添加完整回答到歷史
      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: pendingWorkflow.request.question,
        answer: responseContent.answer,
        timestamp: new Date(),
        sourceDocuments: responseContent.source_documents,
        tokensUsed: responseContent.tokens_used,
        processingTime: responseContent.processing_time,
        confidenceScore: responseContent.confidence_score || undefined,
        queryRewriteResult: responseContent.query_rewrite_result || null,
        llmContextDocuments: responseContent.llm_context_documents || null,
        semanticSearchContexts: responseContent.semantic_search_contexts || null,
        classification: responseContent.classification,
        workflowState: responseContent.workflow_state,
        usedSettings: { ...aiQASettings }
      };

      setQAHistory(prev => [newSession, ...prev]);
      setPendingWorkflow(null);
      showPCMessage('搜索完成', 'success');
      
    } catch (error) {
      console.error('批准搜索失敗:', error);
      showPCMessage('批准搜索失敗', 'error');
    } finally {
      setIsAsking(false);
    }
  };

  // 處理跳過搜索
  const handleSkipSearch = async () => {
    if (!pendingWorkflow) {
      console.error('沒有待處理的工作流');
      return;
    }

    try {
      setIsAsking(true);
      
      // 創建新請求,帶上跳過動作
      const skipRequest: AIQARequestUnified = {
        ...pendingWorkflow.request,
        workflow_action: 'skip_search'
      };

      const unifiedResponse: AIResponse<AIQAResponse> = await askAIQuestionUnified(skipRequest);
      
      if (!unifiedResponse.success || !unifiedResponse.content) {
        showPCMessage('跳過搜索失敗', 'error');
        return;
      }

      const responseContent = unifiedResponse.content;

      // 添加通用知識回答到歷史
      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: pendingWorkflow.request.question,
        answer: responseContent.answer,
        timestamp: new Date(),
        sourceDocuments: [],
        tokensUsed: responseContent.tokens_used,
        processingTime: responseContent.processing_time,
        confidenceScore: responseContent.confidence_score || undefined,
        classification: responseContent.classification,
        workflowState: responseContent.workflow_state,
        usedSettings: { ...aiQASettings }
      };

      setQAHistory(prev => [newSession, ...prev]);
      setPendingWorkflow(null);
      showPCMessage('已使用通用知識回答', 'info');
      
    } catch (error) {
      console.error('跳過搜索失敗:', error);
      showPCMessage('跳過搜索失敗', 'error');
    } finally {
      setIsAsking(false);
    }
  };

  // 處理澄清回答(直接提交為新問題,利用對話歷史自動路由)
  const handleSubmitClarification = async (clarificationText: string) => {
    if (!clarificationText.trim()) {
      showPCMessage('請輸入澄清信息', 'error');
      return;
    }

    // 清除待處理工作流（澄清完成）
    setPendingWorkflow(null);
    
    // 直接作為新問題提交,系統會自動看到對話歷史並重新分類
    await handleAskQuestion(clarificationText);
    setClarificationInput('');
  };

  // 處理快速回答選項
  const handleQuickResponse = async (option: string) => {
    // 清除待處理工作流
    setPendingWorkflow(null);
    
    // 直接作為新問題提交
    await handleAskQuestion(option);
  };

  // 處理詳細查詢批准 ⭐ 新增
  const handleApproveDetailQuery = async () => {
    if (!pendingWorkflow) {
      console.error('沒有待處理的工作流');
      return;
    }

    try {
      setIsAsking(true);
      
      const approvedRequest: AIQARequestUnified = {
        ...pendingWorkflow.request,
        workflow_action: 'approve_detail_query'
      };

      const unifiedResponse: AIResponse<AIQAResponse> = await askAIQuestionUnified(approvedRequest);
      
      if (!unifiedResponse.success || !unifiedResponse.content) {
        showPCMessage('詳細查詢失敗', 'error');
        return;
      }

      const responseContent = unifiedResponse.content;

      // 🔍 調試：檢查是否有詳細查詢數據
      if (responseContent.detailed_document_data_from_ai_query) {
        console.log('✅ 收到詳細查詢數據:', responseContent.detailed_document_data_from_ai_query);
      } else {
        console.log('⚠️ 沒有詳細查詢數據');
      }

      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: pendingWorkflow.request.question,
        answer: responseContent.answer,
        timestamp: new Date(),
        sourceDocuments: responseContent.source_documents,
        tokensUsed: responseContent.tokens_used,
        processingTime: responseContent.processing_time,
        confidenceScore: responseContent.confidence_score || undefined,
        queryRewriteResult: responseContent.query_rewrite_result || null,
        llmContextDocuments: responseContent.llm_context_documents || null,
        semanticSearchContexts: responseContent.semantic_search_contexts || null,
        detailedDocumentDataFromAiQuery: responseContent.detailed_document_data_from_ai_query || null,
        detailedQueryReasoning: responseContent.detailed_query_reasoning || null,
        classification: responseContent.classification,
        workflowState: responseContent.workflow_state,
        usedSettings: { ...aiQASettings }
      };

      setQAHistory(prev => [newSession, ...prev]);
      setPendingWorkflow(null);
      showPCMessage('詳細查詢完成', 'success');
      
    } catch (error) {
      console.error('批准詳細查詢失敗:', error);
      showPCMessage('批准詳細查詢失敗', 'error');
    } finally {
      setIsAsking(false);
    }
  };

  // 處理跳過詳細查詢 ⭐ 新增
  const handleSkipDetailQuery = async () => {
    if (!pendingWorkflow) {
      console.error('沒有待處理的工作流');
      return;
    }

    try {
      setIsAsking(true);
      
      const skipRequest: AIQARequestUnified = {
        ...pendingWorkflow.request,
        workflow_action: 'skip_detail_query',
        use_ai_detailed_query: false  // 明確關閉詳細查詢
      };

      const unifiedResponse: AIResponse<AIQAResponse> = await askAIQuestionUnified(skipRequest);
      
      if (!unifiedResponse.success || !unifiedResponse.content) {
        showPCMessage('跳過查詢失敗', 'error');
        return;
      }

      const responseContent = unifiedResponse.content;

      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: pendingWorkflow.request.question,
        answer: responseContent.answer,
        timestamp: new Date(),
        sourceDocuments: responseContent.source_documents || [],
        tokensUsed: responseContent.tokens_used,
        processingTime: responseContent.processing_time,
        classification: responseContent.classification,
        workflowState: responseContent.workflow_state,
        usedSettings: { ...aiQASettings }
      };

      setQAHistory(prev => [newSession, ...prev]);
      setPendingWorkflow(null);
      showPCMessage('已使用摘要回答', 'info');
      
    } catch (error) {
      console.error('跳過詳細查詢失敗:', error);
      showPCMessage('跳過詳細查詢失敗', 'error');
    } finally {
      setIsAsking(false);
    }
  };

  // 新建對話
  const startNewConversation = async () => {
    setCurrentConversationId(null);
    setCurrentSessionId(null);
    setQAHistory([]);
    showPCMessage('請輸入問題以開始新對話', 'info');
  };
  
  // 切換對話
  const switchConversation = async (conversationId: string) => {
    try {
      setCurrentConversationId(conversationId);
      setQAHistory([]); // 清空當前顯示
      
      // 載入對話的消息歷史
      const conversationDetail = await conversationService.getConversation(conversationId);
      
      console.log('載入對話詳情:', {
        id: conversationDetail.id,
        messageCount: conversationDetail.messages.length,
        cachedDocuments: conversationDetail.cached_documents
      });
      
      // 將消息轉換為 QASession 格式顯示
      const sessions: QASession[] = [];
      const cachedDocs = conversationDetail.cached_documents || [];
      
      for (let i = 0; i < conversationDetail.messages.length; i += 2) {
        const userMsg = conversationDetail.messages[i];
        const assistantMsg = conversationDetail.messages[i + 1];
        
        if (userMsg && assistantMsg && userMsg.role === 'user' && assistantMsg.role === 'assistant') {
          sessions.push({
            id: `qa_${i}`,
            question: userMsg.content,
            answer: assistantMsg.content,
            timestamp: new Date(assistantMsg.timestamp),
            sourceDocuments: cachedDocs,  // 使用緩存的文檔ID
            tokensUsed: assistantMsg.tokens_used || 0,
            processingTime: 0,
          });
        }
      }
      
      setQAHistory(sessions.reverse());
      showPCMessage(`已切換對話 (${cachedDocs.length} 個緩存文檔)`, 'success');
    } catch (error) {
      console.error('切換對話失敗:', error);
      showPCMessage('切換對話失敗', 'error');
    }
  };
  
  // 刪除對話
  const handleDeleteConversation = async (conversationId: string) => {
    Modal.confirm({
      title: '確認刪除對話？',
      content: '刪除後無法恢復',
      okText: '確認刪除',
      cancelText: '取消',
      onOk: async () => {
        try {
          await conversationService.deleteConversation(conversationId);
          await loadConversations();
          
          // 如果刪除的是當前對話，清空狀態
          if (conversationId === currentConversationId) {
            setCurrentConversationId(null);
            setQAHistory([]);
          }
          
          showPCMessage('對話已刪除', 'success');
        } catch (error) {
          console.error('刪除對話失敗:', error);
          showPCMessage('刪除對話失敗', 'error');
        }
      },
    });
  };
  
  // 從緩存中移除文檔
  const handleRemoveCachedDocument = async (documentId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // 防止觸發查看文檔
    
    if (!currentConversationId) {
      showPCMessage('請先選擇一個對話', 'error');
      return;
    }
    
    Modal.confirm({
      title: '確認移除此文檔？',
      content: '移除後，下次提問時將不會優先使用此文檔',
      okText: '確認移除',
      cancelText: '取消',
      onOk: async () => {
        try {
          await conversationService.removeCachedDocument(currentConversationId, documentId);
          
          // 更新 QA 歷史，移除文檔
          setQAHistory(prev => prev.map(session => ({
            ...session,
            sourceDocuments: session.sourceDocuments.filter(id => id !== documentId)
          })));
          
          showPCMessage('文檔已從緩存中移除', 'success');
        } catch (error) {
          console.error('移除緩存文檔失敗:', error);
          showPCMessage('移除緩存文檔失敗', 'error');
        }
      }
    });
  };

  // 清除當前顯示的 QA 歷史（不刪除對話）
  const clearQAHistory = () => {
    setQAHistory([]);
    showPCMessage('已清除當前顯示', 'info');
  };
  
  // 組件掛載時載入數據
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 自動滾動到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [qaHistory]);

  // 獲取參考文檔的詳細信息
  useEffect(() => {
    const fetchReferenceDocuments = async () => {
      if (qaHistory.length > 0 && qaHistory[0].sourceDocuments && qaHistory[0].sourceDocuments.length > 0) {
        try {
          const docs = await getDocumentsByIds(qaHistory[0].sourceDocuments);
          const docsMap: Record<string, Document> = {};
          docs.forEach((doc: Document) => {
            docsMap[doc.id] = doc;
          });
          setReferenceDocuments(docsMap);
        } catch (error) {
          console.error('獲取參考文檔失敗:', error);
        }
      }
    };
    fetchReferenceDocuments();
  }, [qaHistory]);

  // 處理點擊文件卡片查看內容
  const handleViewDocument = async (docId: string) => {
    setIsLoadingDocumentContent(true);
    try {
      const doc = await getDocumentById(docId);
      setViewingDocument(doc);
    } catch (error) {
      console.error('獲取文件內容失敗:', error);
      showPCMessage('無法載入文件內容', 'error');
    } finally {
      setIsLoadingDocumentContent(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" tip="載入 AI 問答系統..." />
      </div>
    );
  }

  // 應用預設模式
  const applyPresetMode = (mode: keyof typeof AIQAPresetModes) => {
    handleSettingsChange(AIQAPresetModes[mode].settings);
  };

  // 獲取當前模式
  const getCurrentMode = (): keyof typeof AIQAPresetModes => {
    const settingsStr = JSON.stringify(aiQASettings);
    if (settingsStr === JSON.stringify(AIQAPresetModes.low.settings)) return 'low';
    if (settingsStr === JSON.stringify(AIQAPresetModes.high.settings)) return 'high';
    return 'medium';
  };

  return (
    <div className="h-screen flex overflow-hidden bg-gray-50">
      {/* 左側：完整的歷史對話側邊欄 */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* 標題區 */}
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center space-x-2 mb-3">
            <RobotOutlined className="text-xl text-blue-500" />
            <Title level={5} className="mb-0">AI 智能助手</Title>
          </div>
          
          {/* 新對話按鈕 */}
          <Button
            type="default"
            block
            icon={<PlusOutlined />}
            onClick={startNewConversation}
            className="flex items-center justify-center"
          >
            新的對話
          </Button>
        </div>

        {/* 對話列表 */}
        <div className="flex-1 overflow-y-auto">
          {loadingConversations ? (
            <div className="flex items-center justify-center py-8">
              <Spin size="small" />
            </div>
          ) : conversations.length > 0 ? (
            <div className="p-2">
              {conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`px-3 py-3 mb-1 cursor-pointer rounded-lg hover:bg-gray-100 transition-colors group ${
                    conversation.id === currentConversationId ? 'bg-blue-50 border border-blue-200' : 'border border-transparent'
                  }`}
                  onClick={() => switchConversation(conversation.id)}
                >
                  <div className="flex items-start space-x-2">
                    <EditOutlined className="text-gray-400 mt-1 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-900 truncate font-medium">
                        {conversation.title}
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <Text type="secondary" className="text-xs">
                          {conversation.message_count} 條消息
                        </Text>
                        <Text type="secondary" className="text-xs">
                          {new Date(conversation.updated_at).toLocaleDateString('zh-TW', { 
                            month: 'numeric', 
                            day: 'numeric' 
                          })}
                        </Text>
                      </div>
                    </div>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<ClearOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteConversation(conversation.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暫無對話記錄"
              className="mt-8"
            />
          )}
        </div>

        {/* 底部信息 */}
        <div className="p-3 border-t border-gray-200">
          <Button
            block
            icon={<ClearOutlined />}
            onClick={clearQAHistory}
            disabled={qaHistory.length === 0}
            size="small"
          >
            清除歷史
          </Button>
        </div>
      </div>

      {/* 右側：主內容區域 */}
      <div className="flex-1 flex flex-col">
        {/* 頂部控制欄 */}
        <div className="bg-white border-b border-gray-200 px-6 py-3">
          <div className="flex items-center space-x-3">
            <Text type="secondary" className="text-sm">AI 模式:</Text>
              <Button
              type={getCurrentMode() === 'low' ? 'primary' : 'default'}
              icon={<ThunderboltOutlined />}
              onClick={() => applyPresetMode('low')}
              size="small"
            >
              輕量
              </Button>
            <Button
              type={getCurrentMode() === 'medium' ? 'primary' : 'default'}
              onClick={() => applyPresetMode('medium')}
              size="small"
            >
              平衡
            </Button>
            <Button
              type={getCurrentMode() === 'high' ? 'primary' : 'default'}
              onClick={() => applyPresetMode('high')}
              size="small"
            >
              高精度
            </Button>
            <Tooltip 
              title="詳細參數設定"
              overlayInnerStyle={{
                backgroundColor: '#1f2937',
                color: '#ffffff',
                fontSize: '13px',
                fontWeight: 500,
              }}
            >
              <Button
                type="text"
                icon={<QuestionCircleOutlined />}
                onClick={() => setShowSettingsModal(true)}
                size="small"
              />
            </Tooltip>
            
            <Tooltip title="統計分析">
              <Button
                type="text"
                icon={<BarChartOutlined />}
                onClick={() => setShowAnalytics(true)}
                size="small"
              >
                統計
              </Button>
            </Tooltip>
          </div>
        </div>

        {/* 主內容區：對話 + 右側面板 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 對話內容區域 */}
          <div className="flex-1 overflow-y-auto p-6">
          {qaHistory.length === 0 ? (
            // 空狀態 - 顯示示例問題
            <div className="max-w-3xl mx-auto mt-20">
              <div className="text-center mb-8">
                <RobotOutlined className="text-6xl text-blue-500 mb-4" />
                <Title level={3}>AI 智能助手</Title>
                <Text type="secondary">您可以問我任何關於文檔的問題</Text>
              </div>

              {/* 示例問題卡片 */}
              <div className="grid grid-cols-2 gap-4 mt-8">
                {exampleQuestions.map((example, index) => (
                  <Card
                    key={index}
                    hoverable
                    className="cursor-pointer"
                    onClick={() => handleExampleQuestion(example)}
                  >
                    <div className="flex items-start">
                      <BulbOutlined className="text-yellow-500 mr-2 mt-1" />
                      <Text className="text-sm">{example}</Text>
                    </div>
                  </Card>
                ))}
          </div>

          {(!vectorStats || vectorStats.total_vectors === 0) && (
            <Alert
              message="向量數據庫為空"
              description="請先在向量數據庫管理頁面中向量化一些文檔，然後回來進行問答。"
              type="warning"
              showIcon
                  className="mt-8"
            />
          )}
        </div>
          ) : (
            // 對話記錄 - 聊天氣泡樣式
            <div className="max-w-4xl mx-auto space-y-6">
              {[...qaHistory].reverse().map((session) => (
                <div key={session.id} className="space-y-4">
                  {/* 用戶問題氣泡 */}
                  <div className="flex justify-end">
                    <div className="max-w-[70%] bg-blue-500 text-white rounded-2xl px-4 py-3 shadow-sm">
                      <div className="flex items-start">
                        <div className="flex-1">
                          <Text className="text-white font-medium">{session.question}</Text>
        </div>
                        <UserOutlined className="ml-2 mt-1 text-white" />
                      </div>
                    </div>
                  </div>

                  {/* AI 回答氣泡 */}
                  <div className="flex justify-start">
                    <div className="max-w-[80%] bg-white rounded-2xl px-4 py-3 shadow-sm border border-gray-200">
                      <div className="flex items-start">
                        <RobotOutlined className="text-blue-500 mr-2 mt-1 text-lg" />
                        <div className="flex-1">
                          {/* 顯示意圖標籤 */}
                          {session.classification && (
                            <Tag 
                              color={
                                session.classification.intent === 'greeting' ? 'green' :
                                session.classification.intent === 'clarification_needed' ? 'orange' :
                                session.classification.intent === 'simple_factual' ? 'blue' :
                                session.classification.intent === 'document_search' ? 'purple' :
                                session.classification.intent === 'complex_analysis' ? 'red' : 'default'
                              }
                              style={{ marginBottom: 8 }}
                            >
                              {session.classification.intent === 'greeting' && '寒暄問候'}
                              {session.classification.intent === 'clarification_needed' && '需要澄清'}
                              {session.classification.intent === 'simple_factual' && '簡單查詢'}
                              {session.classification.intent === 'document_search' && '文檔搜索'}
                              {session.classification.intent === 'complex_analysis' && '複雜分析'}
                            </Tag>
                          )}
                          
                          {/* 只顯示答案，澄清交互由底部工作流UI處理 */}
                          {session.answer && <MarkdownRenderer content={session.answer} />}
                          
                          {/* 如果是等待交互的狀態，顯示提示 */}
                          {!session.answer && session.workflowState && (
                            <Text type="secondary" style={{ fontStyle: 'italic', fontSize: '13px' }}>
                              ⏳ 等待您的回應...
                            </Text>
                          )}

                          {/* 時間戳和性能指標 */}
                          <div className="flex items-center justify-between mt-3">
                            <Text type="secondary" className="text-xs">
                              {session.timestamp.toLocaleString('zh-TW')}
                            </Text>
                            {session.workflowState?.api_calls && (
                              <Tag color="blue" style={{ fontSize: 11, marginLeft: 8 }}>
                                {session.workflowState.api_calls} 次API
                              </Tag>
                            )}
                          </div>
                        </div>
                                    </div>
                                      </div>
                                      </div>
                                  </div>
              ))}
              {/* 自動滾動錨點 */}
              <div ref={messagesEndRef} />
                              </div>
                            )}
    </div>

          {/* 右側面板：處理數據 + 參考資料 */}
          <div className="w-96 border-l border-gray-200 bg-white flex flex-col overflow-y-auto">
            <Collapse
              defaultActiveKey={['processing-data', 'references']}
              ghost
            >
              {/* 處理數據面板 */}
              {qaHistory.length > 0 && (
                <Panel
                  header={
                    <div className="flex items-center space-x-2">
                      <BulbOutlined className="text-blue-500" />
                      <Text strong>處理過程數據</Text>
                    </div>
                  }
                  key="processing-data"
                  className="flex-1"
                >
                  <AIQADataPanel
                    queryRewriteResult={qaHistory[0].queryRewriteResult}
                    semanticSearchContexts={qaHistory[0].semanticSearchContexts}
                    llmContextDocuments={qaHistory[0].llmContextDocuments}
                    tokensUsed={qaHistory[0].tokensUsed}
                    processingTime={qaHistory[0].processingTime}
                    confidenceScore={qaHistory[0].confidenceScore}
                    detailedDocumentDataFromAiQuery={qaHistory[0].detailedDocumentDataFromAiQuery}
                    detailedQueryReasoning={qaHistory[0].detailedQueryReasoning}
                  />
                </Panel>
              )}

              {/* 參考資料面板 */}
              <Panel 
                header={
                  <div className="flex items-center space-x-2">
                    <FileTextOutlined className="text-green-500" />
                    <Text strong>參考資料</Text>
                    {qaHistory.length > 0 && qaHistory[0].sourceDocuments && (
                      <Tag color="green" className="ml-2 text-xs">
                        {qaHistory[0].sourceDocuments.length} 個文檔
                      </Tag>
                    )}
                  </div>
                }
                key="references"
              >
                <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
                  {qaHistory.length > 0 && qaHistory[0].sourceDocuments && qaHistory[0].sourceDocuments.length > 0 ? (
                    qaHistory[0].sourceDocuments.map((docId, index) => {
                      const doc = referenceDocuments[docId];
                      return (
                        <Card
                          key={index}
                          size="small"
                          className="cursor-pointer hover:shadow-md transition-shadow relative group"
                          bodyStyle={{ padding: '8px 12px' }}
                          onClick={() => handleViewDocument(docId)}
                        >
                          {/* 刪除按鈕 */}
                          {currentConversationId && (
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<CloseCircleOutlined />}
                              className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                              onClick={(e) => handleRemoveCachedDocument(docId, e)}
                              style={{ padding: '2px 4px' }}
                            />
                          )}
                          
                          <div className="flex items-start space-x-2">
                            {doc ? (
                              <DocumentTypeIcon
                                fileType={doc.file_type}
                                fileName={doc.filename}
                                className="w-8 h-8 flex-shrink-0"
                              />
                            ) : (
                              <FileTextOutlined className="text-green-500 mt-1 flex-shrink-0 text-xl" />
                            )}
                            <div className="flex-1 min-w-0">
                              <Text strong className="text-xs block truncate">
                                {doc ? doc.filename : `文檔 ${index + 1}`}
                              </Text>
                              {doc && doc.file_type && (
                                <Text type="secondary" className="text-xs block">
                                  {doc.file_type}
                                </Text>
                              )}
                              <div className="flex items-center justify-between mt-1">
                                <Tag color="green" className="text-xs">參考文檔</Tag>
                                <Text type="secondary" className="text-xs">
                                  {doc && doc.updated_at
                                    ? new Date(doc.updated_at).toLocaleDateString('zh-TW', {
                                        month: 'numeric',
                                        day: 'numeric',
                                      })
                                    : ''}
                                </Text>
                              </div>
                            </div>
                          </div>
                        </Card>
                      );
                    })
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="暫無參考資料"
                      className="py-4"
                    />
                  )}
                </div>
              </Panel>
            </Collapse>
          </div>
        </div>

        {/* 底部輸入區域 */}
        <div className="border-t border-gray-200 bg-white p-4">
          <div className="max-w-4xl mx-auto">
            {/* 工作流交互UI - 全寬布局 */}
            {pendingWorkflow && pendingWorkflow.response.workflow_state && (
              <div style={{ marginBottom: 16, maxWidth: '100%' }}>
                <QAWorkflowDisplay
                  workflowState={pendingWorkflow.response.workflow_state as WorkflowState}
                  onApproveSearch={handleApproveSearch}
                  onSkipSearch={handleSkipSearch}
                  onApproveDetailQuery={handleApproveDetailQuery}
                  onSkipDetailQuery={handleSkipDetailQuery}
                  onSubmitClarification={handleSubmitClarification}
                  onQuickResponse={handleQuickResponse}
                  isSearching={isAsking}
                />
              </div>
            )}
            
            {/* 只在有待處理工作流時隱藏主輸入框 */}
            {!pendingWorkflow && (
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <TextArea
                    placeholder="請輸入您想要問的問題... (Ctrl+Enter 發送)"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    rows={3}
                    onPressEnter={(e) => {
                      if (e.ctrlKey || e.metaKey) {
                        handleAskQuestion();
                      }
                    }}
                    className="resize-none"
                    disabled={!vectorStats?.total_vectors || isAsking}
                  />
                </div>
                <Button 
                  type="primary"
                  size="large"
                  icon={<SendOutlined />}
                  onClick={() => handleAskQuestion()}
                  loading={isAsking}
                  disabled={!question.trim() || !vectorStats?.total_vectors || isAsking}
                  className="h-[72px]"
                >
                  發送
                </Button>
              </div>
            )}

            {/* 狀態提示 */}
            <div className="mt-2 flex items-center justify-between">
              <Text type="secondary" className="text-xs">
                按 Ctrl+Enter 快速發送
              </Text>
              {currentSessionId && (
                <Text type="secondary" className="text-xs">
                  會話ID: {currentSessionId.substring(0, 8)}...
                </Text>
      )}
    </div>
      </div>
        </div>
      </div>

      {/* AI 參數設定模態框 */}
      <Modal
        title="AI 問答參數設定"
        open={showSettingsModal}
        onCancel={() => setShowSettingsModal(false)}
        footer={null}
        width={800}
      >
        <AIQASettings
          settings={aiQASettings}
          onChange={handleSettingsChange}
          onReset={handleSettingsReset}
        />
      </Modal>

      {/* 文件內容查看模態框 */}
      <Modal
        title={
          <div className="flex items-center space-x-2">
            {viewingDocument && (
              <>
                <DocumentTypeIcon
                  fileType={viewingDocument.file_type}
                  fileName={viewingDocument.filename}
                  className="w-6 h-6"
                />
                <span>{viewingDocument.filename}</span>
              </>
            )}
          </div>
        }
        open={!!viewingDocument}
        onCancel={() => setViewingDocument(null)}
        footer={[
          <Button key="close" onClick={() => setViewingDocument(null)}>
            關閉
          </Button>
        ]}
        width={900}
        style={{ top: 20 }}
      >
        {isLoadingDocumentContent ? (
          <div className="flex items-center justify-center py-12">
            <Spin size="large" tip="載入文件內容..." />
          </div>
        ) : viewingDocument ? (
          <div className="space-y-4">
            {/* 文件基本信息 */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                  <Text type="secondary">文件類型：</Text>
                  <Text strong>{viewingDocument.file_type || 'N/A'}</Text>
                      </div>
                                <div>
                  <Text type="secondary">文件大小：</Text>
                  <Text strong>
                    {viewingDocument.size
                      ? `${(viewingDocument.size / 1024).toFixed(2)} KB`
                      : 'N/A'}
                  </Text>
                                </div>
                              <div>
                  <Text type="secondary">上傳時間：</Text>
                  <Text strong>
                    {viewingDocument.created_at
                      ? new Date(viewingDocument.created_at).toLocaleString('zh-TW')
                      : 'N/A'}
                  </Text>
                                </div>
                                    <div>
                  <Text type="secondary">更新時間：</Text>
                  <Text strong>
                    {viewingDocument.updated_at
                      ? new Date(viewingDocument.updated_at).toLocaleString('zh-TW')
                      : 'N/A'}
                  </Text>
                                      </div>
                                    </div>
              {viewingDocument.tags && viewingDocument.tags.length > 0 && (
                <div className="mt-3">
                  <Text type="secondary">標籤：</Text>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {viewingDocument.tags.map((tag, idx) => (
                      <Tag key={idx} color="blue">
                        {tag}
                                        </Tag>
                    ))}
                                      </div>
                                      </div>
                                    )}
                                  </div>

            {/* AI 摘要 */}
            {(viewingDocument.enriched_data?.summary || 
              viewingDocument.analysis?.ai_analysis_output?.initial_summary) && (
              <div>
                <Title level={5}>AI 摘要</Title>
                <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                  <MarkdownRenderer 
                    content={
                      viewingDocument.enriched_data?.summary || 
                      viewingDocument.analysis?.ai_analysis_output?.initial_summary || 
                      ''
                    } 
                  />
                                </div>
                              </div>
            )}

            {/* 文件內容 */}
            {viewingDocument.extracted_text && (
              <div>
                <Title level={5}>文件內容</Title>
                <div className="bg-white p-4 rounded-lg border border-gray-200 max-h-96 overflow-y-auto">
                  <MarkdownRenderer content={viewingDocument.extracted_text} />
                      </div>
                    </div>
            )}

            {/* 如果沒有內容顯示提示 */}
            {!viewingDocument.extracted_text && 
             !viewingDocument.enriched_data?.summary && 
             !viewingDocument.analysis?.ai_analysis_output?.initial_summary && (
              <Empty
                description="該文件暫無可顯示的內容"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </div>
        ) : null}
      </Modal>

      {/* 統計分析面板 Drawer */}
      <Drawer
        title={
          <Space>
            <BarChartOutlined />
            <span>AI問答統計分析</span>
          </Space>
        }
        placement="right"
        width={800}
        onClose={() => setShowAnalytics(false)}
        open={showAnalytics}
      >
        <QAAnalyticsPanel />
      </Drawer>
    </div>
  );
};

export default AIQAPage; 