import React, { useState, useEffect, useCallback } from 'react';
import {
  PageHeader
} from '../components';
import {
  Alert,
  Space,
  Modal,
  List,
  Row,
  Col,
  Spin,
  Empty,
  message,
  Tooltip,
  Input,
  Typography,
  Divider,
  Tag,
  Badge,
  Steps,
  Progress,
  Tabs,
  Card,
  Statistic,
  Button,
  Collapse,
  Switch
} from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  HistoryOutlined,
  BulbOutlined,
  FileTextOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  ClearOutlined,
  QuestionCircleOutlined,
  CheckCircleOutlined,
  EyeOutlined,
  InfoCircleOutlined,
  UserOutlined,
  RetweetOutlined,
  SlidersOutlined,
  ApartmentOutlined,
  SettingOutlined,
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
import { getDocumentsByIds } from '../services/documentService';
import SemanticSearchInterface from '../components/SemanticSearchInterface';
import AIQASettings, { AIQASettingsConfig, defaultAIQASettings } from '../components/settings/AIQASettings';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;
const { TabPane } = Tabs;
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
  detailedDocumentDataFromAiQuery?: Record<string, any> | null;
  detailedQueryReasoning?: string | null;
  sessionId?: string;
  usedSettings?: AIQASettingsConfig;
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

// 參考文件顯示組件
const SourceDocumentsDisplay: React.FC<{ documents: string[] }> = ({ documents }) => {
  const [documentNames, setDocumentNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchDocumentNames = async () => {
      if (!documents || documents.length === 0) return;
      
      setLoading(true);
      try {
        const documentsData = await getDocumentsByIds(documents);
        const nameMap: Record<string, string> = {};
        
        documentsData.forEach((doc: Document) => {
          nameMap[doc.id] = doc.filename;
        });
        
        // 對於沒有找到的文件，使用ID作為顯示名稱
        documents.forEach(docId => {
          if (!nameMap[docId]) {
            nameMap[docId] = `文件 ${docId.substring(0, 8)}...`;
          }
        });
        
        setDocumentNames(nameMap);
      } catch (error) {
        console.error('獲取文件名稱失敗:', error);
        // 如果獲取失敗，使用文件ID的縮短版本
        const fallbackMap: Record<string, string> = {};
        documents.forEach(docId => {
          fallbackMap[docId] = `文件 ${docId.substring(0, 8)}...`;
        });
        setDocumentNames(fallbackMap);
      } finally {
        setLoading(false);
      }
    };

    fetchDocumentNames();
  }, [documents]);

  if (!documents || documents.length === 0) return null;
  
  return (
    <Card 
      size="small" 
      title={
        <span style={{ color: '#1890ff' }}>
          <FileTextOutlined style={{ marginRight: '0.5em' }} />
          參考文件 ({documents.length} 個)
        </span>
      }
      style={{ 
        marginTop: '1em',
        border: '2px solid #e6f7ff',
        backgroundColor: '#f6ffed'
      }}
      headStyle={{
        backgroundColor: '#e6f7ff',
        borderBottom: '1px solid #91d5ff'
      }}
    >
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1em' }}>
          <Spin size="small" />
          <span style={{ marginLeft: '0.5em' }}>載入文件名稱...</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5em' }}>
          {documents.map((docId, index) => (
            <Tooltip key={index} title={`文件ID: ${docId}`}>
              <Tag 
                color="blue" 
                icon={<FileTextOutlined />}
                style={{ 
                  marginBottom: '0.5em',
                  fontSize: '0.85em',
                  padding: '0.3em 0.6em',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}
              >
                {documentNames[docId] || `文件 ${docId.substring(0, 8)}...`}
              </Tag>
            </Tooltip>
          ))}
        </div>
      )}
    </Card>
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
  const [activeTab, setActiveTab] = useState('qa');
  const [showHistoryModal, setShowHistoryModal] = useState(false);

  // 示例問題
  const exampleQuestions = [
    "文檔中提到的主要結論是什麼？",
    "有沒有關於財務數據的內容？",
    "請總結文檔的核心內容",
    "文檔中提到哪些重要的日期？",
    "請列出文檔中的主要人物或組織",
    "有什麼需要注意的風險或問題嗎？"
  ];

  // 載入初始數據
  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const stats = await getVectorDatabaseStats();
      setVectorStats(stats);
    } catch (error) {
      console.error('載入 AI 問答頁面數據失敗:', error);
      showPCMessage('載入數據失敗', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [showPCMessage]);

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
  const handleAskQuestion = async () => {
    if (!question.trim()) {
      showPCMessage('請輸入問題', 'error');
      return;
    }

    if (!vectorStats || vectorStats.total_vectors === 0) {
      showPCMessage('向量數據庫中沒有可用的文檔，請先向量化一些文檔', 'error');
      return;
    }

    try {
      setIsAsking(true);
      const request: AIQARequestUnified = {
        question: question.trim(),
        session_id: currentSessionId || undefined,
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

      const newSession: QASession = {
        id: `qa_${Date.now()}`,
        question: question.trim(),
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
        usedSettings: { ...aiQASettings }
      };

      setQAHistory(prev => [newSession, ...prev]);
      setCurrentSessionId(responseContent.session_id || null);
      setQuestion('');
      
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

  // 新建會話
  const startNewSession = () => {
    setCurrentSessionId(null);
    showPCMessage('已開始新的對話會話', 'info');
  };

  // 清除 QA 歷史
  const clearQAHistory = () => {
    setQAHistory([]);
    showPCMessage('已清除問答歷史記錄', 'info');
  };
  
  // 組件掛載時載入數據
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 渲染統計卡片
  const renderStatsCards = () => (
    <Row gutter={[16, 16]} className="mb-6">
      <Col xs={12} sm={6}>
        <Card className="text-center">
          <Statistic
            title="可用向量"
            value={vectorStats?.total_vectors || 0}
            prefix={<FileTextOutlined />}
            valueStyle={{ color: vectorStats?.total_vectors ? '#3f8600' : '#cf1322' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card className="text-center">
          <Statistic
            title="問答記錄"
            value={qaHistory.length}
            prefix={<RobotOutlined />}
            valueStyle={{ color: '#1890ff' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card className="text-center">
          <Statistic
            title="搜索調用" 
            value={"N/A"}
            prefix={<SearchOutlined />}
            valueStyle={{ color: '#722ed1' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card className="text-center">
          <Statistic
            title="模型設備"
            value={vectorStats?.embedding_model.device?.toUpperCase() || 'N/A'}
            prefix={<ThunderboltOutlined />}
            valueStyle={{ 
              color: vectorStats?.embedding_model.device === 'cuda' ? '#52c41a' : '#faad14' 
            }}
          />
        </Card>
      </Col>
    </Row>
  );

  // 渲染 AI 問答介面
  const renderQAInterface = () => (
    <div className="space-y-6">
      {/* AI 問答參數設定 */}
      <AIQASettings
        settings={aiQASettings}
        onChange={handleSettingsChange}
        onReset={handleSettingsReset}
      />

      {/* 問題輸入區域 */}
      <Card title="AI 智能問答" extra={
        <Space>
          <Button
            onClick={startNewSession}
            icon={<ReloadOutlined />}
          >
            新對話
          </Button>
          <Button
            onClick={() => setShowHistoryModal(true)}
            icon={<HistoryOutlined />}
          >
            歷史記錄
          </Button>
        </Space>
      }>
        <div className="space-y-4">
          <TextArea
            placeholder="請輸入您想要問的問題..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            onPressEnter={(e) => {
              if (e.ctrlKey || e.metaKey) {
                handleAskQuestion();
              }
            }}
          />
          
          <div className="flex justify-between items-center">
            <Space>
              <Text type="secondary" className="hidden sm:inline">按 Ctrl+Enter 發送</Text>
              <Text type="secondary" className="text-xs">
                當前模式: <Tag color={aiQASettings.use_ai_detailed_query ? 'green' : 'default'}>
                  {aiQASettings.use_ai_detailed_query ? '詳細查詢' : '快速查詢'}
                </Tag>
              </Text>
            </Space>
            <Space>
              <Button
                onClick={handleAskQuestion}
                loading={isAsking}
                icon={<SendOutlined />}
                disabled={!question.trim() || !vectorStats?.total_vectors}
              >
                提問
              </Button>
            </Space>
          </div>

          {(!vectorStats || vectorStats.total_vectors === 0) && (
            <Alert
              message="向量數據庫為空"
              description="請先在向量數據庫管理頁面中向量化一些文檔，然後回來進行問答。"
              type="warning"
              showIcon
              className="ai-qa-alert"
            />
          )}
        </div>
      </Card>

      {/* 示例問題 */}
      <Card title="示例問題" size="small">
        <div className="flex flex-wrap gap-2">
          {exampleQuestions.map((example, index) => (
            <Tag
              key={index}
              className="cursor-pointer mb-2"
              onClick={() => handleExampleQuestion(example)}
              icon={<BulbOutlined />}
            >
              {example}
            </Tag>
          ))}
        </div>
      </Card>

      {/* 問答歷史 */}
      {qaHistory.length > 0 && (
        <Card 
          title="最近的問答記錄" 
          extra={
            <Button 
              onClick={clearQAHistory} 
              icon={<ClearOutlined />}
              danger
            >
              清除歷史
            </Button>
          }
        >
          <List
            dataSource={qaHistory.slice(0, 3)}
            renderItem={(session) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<RobotOutlined className="text-lg text-blue-500" />}
                  title={
                    <div className="flex justify-between items-start">
                      <Text strong className="text-sm">{session.question}</Text>
                      <div className="flex items-center space-x-2 text-xs">
                        <Tag color="blue" className="text-xs">
                          {session.tokensUsed} tokens
                        </Tag>
                        <Tag color="green" className="text-xs">
                          {session.processingTime.toFixed(2)}s
                        </Tag>
                        {session.confidenceScore && (
                          <Tag color="purple" className="text-xs">
                            {(session.confidenceScore * 100).toFixed(0)}%
                          </Tag>
                        )}
                      </div>
                    </div>
                  }
                  description={
                    <div className="mt-2">
                      <div className="text-sm mb-2">
                        <MarkdownRenderer content={session.answer} />
                      </div>
                      <SourceDocumentsDisplay documents={session.sourceDocuments} />
                      <Collapse ghost size="small" className="mb-2">
                        {session.detailedDocumentDataFromAiQuery && (
                          <Panel
                            header="AI 詳細查詢結果"
                            key="detailed-query"
                            extra={<Tooltip title="AI 為了回答問題，對特定文檔進行了深入查詢，並獲取了以下精確信息。"><ApartmentOutlined style={{color: '#8A2BE2'}} /></Tooltip>}
                          >
                            <div className="space-y-2">
                              {session.detailedQueryReasoning && (
                                <div>
                                  <Text strong>AI 查詢原因:</Text>
                                  <Paragraph className="mt-1 p-2 bg-surface-100 rounded text-sm">
                                    {session.detailedQueryReasoning}
                                  </Paragraph>
                                </div>
                              )}
                              <div>
                                <Text strong>查詢到的詳細資料:</Text>
                                <div className="mt-1 p-2 bg-surface-100 rounded text-xs max-h-48 overflow-y-auto">
                                  <pre className="whitespace-pre-wrap font-mono">{JSON.stringify(session.detailedDocumentDataFromAiQuery, null, 2)}</pre>
                                </div>
                              </div>
                            </div>
                          </Panel>
                        )}
                        {session.queryRewriteResult && (
                          <Panel 
                            header="查詢重寫過程" 
                            key="query-rewrite"
                            extra={<Tooltip title="AI如何理解並優化您的問題"><InfoCircleOutlined style={{color: '#1890ff'}} /></Tooltip>}
                          >
                            {/* 新增：顯示AI分析結果 */}
                            {(session.queryRewriteResult.reasoning || 
                              session.queryRewriteResult.query_granularity || 
                              session.queryRewriteResult.search_strategy_suggestion) && (
                              <div className="mb-4 p-3 bg-blue-50 rounded-lg border-l-4 border-blue-400">
                                <div className="space-y-2">
                                  {session.queryRewriteResult.reasoning && (
                                    <div>
                                      <Text strong style={{color: '#1890ff'}}>🧠 AI分析推理：</Text>
                                      <div className="mt-1 text-sm text-gray-700">
                                        {session.queryRewriteResult.reasoning}
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    {session.queryRewriteResult.query_granularity && (
                                      <div>
                                        <Text strong style={{color: '#52c41a'}}>📊 問題粒度：</Text>
                                        <Tag color={
                                          session.queryRewriteResult.query_granularity === 'thematic' ? 'blue' :
                                          session.queryRewriteResult.query_granularity === 'detailed' ? 'green' : 'orange'
                                        }>
                                          {session.queryRewriteResult.query_granularity === 'thematic' ? '主題級' :
                                           session.queryRewriteResult.query_granularity === 'detailed' ? '細節級' : '不確定'}
                                        </Tag>
                                      </div>
                                    )}
                                    {session.queryRewriteResult.search_strategy_suggestion && (
                                      <div>
                                        <Text strong style={{color: '#722ed1'}}>🎯 建議策略：</Text>
                                        <Tag color={
                                          session.queryRewriteResult.search_strategy_suggestion === 'summary_only' ? 'cyan' :
                                          session.queryRewriteResult.search_strategy_suggestion === 'rrf_fusion' ? 'purple' : 'magenta'
                                        }>
                                          {session.queryRewriteResult.search_strategy_suggestion === 'summary_only' ? '摘要專用' :
                                           session.queryRewriteResult.search_strategy_suggestion === 'rrf_fusion' ? 'RRF融合' : '關鍵詞增強RRF'}
                                        </Tag>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                            
                            <Steps direction="vertical" size="small" current={session.queryRewriteResult.rewritten_queries.length}>
                              <Steps.Step 
                                title="原始問題" 
                                description={session.queryRewriteResult.original_query} 
                                icon={<UserOutlined />} 
                              />
                              {session.queryRewriteResult.rewritten_queries.map((rq, idx) => (
                                <Steps.Step 
                                  key={`rewrite-${idx}`} 
                                  title={`重寫查詢 ${idx + 1}`} 
                                  description={rq} 
                                  icon={<RetweetOutlined />} 
                                />
                              ))}
                              {session.queryRewriteResult.intent_analysis && (
                                <Steps.Step 
                                  title="意圖分析" 
                                  description={session.queryRewriteResult.intent_analysis} 
                                  icon={<BulbOutlined />} 
                                />
                              )}
                              {session.queryRewriteResult.extracted_parameters && 
                               Object.keys(session.queryRewriteResult.extracted_parameters).length > 0 && (
                                <Steps.Step 
                                  title="提取參數" 
                                  icon={<SlidersOutlined />}
                                  description={
                                    <List
                                      size="small"
                                      dataSource={Object.entries(session.queryRewriteResult.extracted_parameters)}
                                      renderItem={([key, value]) => (
                                        <List.Item>
                                          <Text strong style={{fontSize: '0.8em'}}>{key}: </Text>
                                          <Text style={{fontSize: '0.8em'}}>{JSON.stringify(value)}</Text>
                                        </List.Item>
                                      )}
                                    />
                                  }
                                />
                              )}
                            </Steps>
                          </Panel>
                        )}
                        {session.semanticSearchContexts && session.semanticSearchContexts.length > 0 && (
                          <Panel 
                            header={`向量搜索初步結果 (${session.semanticSearchContexts.length} 個)`} 
                            key="semantic-search-context"
                            extra={<Tooltip title="向量數據庫返回的直接匹配結果"><SearchOutlined style={{color: '#faad14'}} /></Tooltip>}
                          >
                            <List
                              dataSource={session.semanticSearchContexts}
                              renderItem={(doc, index) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={<Text strong style={{fontSize: '0.9em'}}>{`匹配 ${index + 1}: ${doc.document_id} (相似度: ${(doc.similarity_score * 100).toFixed(1)}%)`}</Text>}
                                    description={<Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展開' }} style={{fontSize: '0.85em'}}>{doc.summary_or_chunk_text}</Paragraph>}
                                  />
                                </List.Item>
                              )}
                            />
                          </Panel>
                        )}
                        {session.llmContextDocuments && session.llmContextDocuments.length > 0 && (
                          <Panel 
                            header={`LLM 使用的上下文 (${session.llmContextDocuments.length} 個片段)`} 
                            key="llm-context"
                            extra={<Tooltip title="AI回答時實際參考的文檔片段"><FileTextOutlined style={{color: '#52c41a'}} /></Tooltip>}
                          >
                            <List
                              dataSource={session.llmContextDocuments}
                              renderItem={(doc, index) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={<Text strong style={{fontSize: '0.9em'}}>{`片段 ${index + 1}: ${doc.document_id} (來源: ${doc.source_type})`}</Text>}
                                    description={<Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展開' }} style={{fontSize: '0.85em'}}>{doc.content_used}</Paragraph>}
                                  />
                                </List.Item>
                              )}
                            />
                          </Panel>
                        )}
                        {session.usedSettings && (
                          <Panel 
                            header="使用的參數設定" 
                            key="used-settings"
                            extra={<Tooltip title="本次查詢使用的具體參數設定"><SettingOutlined style={{color: '#52c41a'}} /></Tooltip>}
                          >
                            <Row gutter={[16, 8]}>
                              <Col xs={12} sm={6}>
                                <Text strong>詳細查詢:</Text><br />
                                <Tag color={session.usedSettings.use_ai_detailed_query ? 'green' : 'default'}>
                                  {session.usedSettings.use_ai_detailed_query ? '啟用' : '禁用'}
                                </Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>上下文數量:</Text><br />
                                <Tag color="blue">{session.usedSettings.context_limit}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>相似度閾值:</Text><br />
                                <Tag color="purple">{(session.usedSettings.similarity_threshold * 100).toFixed(0)}%</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>查詢重寫數:</Text><br />
                                <Tag color="orange">{session.usedSettings.query_rewrite_count}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>候選文件數:</Text><br />
                                <Tag color="cyan">{session.usedSettings.max_documents_for_selection}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>AI選擇限制:</Text><br />
                                <Tag color="magenta">{session.usedSettings.ai_selection_limit}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>詳細文本長度:</Text><br />
                                <Tag color="gold">{(session.usedSettings.detailed_text_max_length / 1000).toFixed(1)}K</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>查詢擴展:</Text><br />
                                <Tag color={session.usedSettings.enable_query_expansion ? 'green' : 'default'}>
                                  {session.usedSettings.enable_query_expansion ? '啟用' : '禁用'}
                                </Tag>
                              </Col>
                              {session.usedSettings.prompt_input_max_length && (
                                <Col xs={12} sm={6}>
                                  <Text strong>提示詞輸入限制:</Text><br />
                                  <Tag color="volcano">{(session.usedSettings.prompt_input_max_length / 1000).toFixed(1)}K</Tag>
                                </Col>
                              )}
                            </Row>
                          </Panel>
                        )}
                      </Collapse>


                      <Text type="secondary" className="text-xs">
                        {session.timestamp.toLocaleString('zh-TW')}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
          {qaHistory.length > 3 && (
            <div className="text-center mt-4">
              <Button 
                onClick={() => setShowHistoryModal(true)}
                icon={<HistoryOutlined />}
              >
                查看全部 {qaHistory.length} 條記錄
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );

  // 渲染語義搜索介面
  const renderSearchInterface = () => (
    <SemanticSearchInterface
      showPCMessage={showPCMessage}
    />
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" tip="載入 AI 問答系統..." />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex justify-between items-center mb-6">
        <PageHeader title="AI 智能問答與知識探索" />
        <Space>
          <Button
            onClick={loadData}
            icon={<ReloadOutlined />}
            loading={isLoading}
          >
            刷新數據
          </Button>
        </Space>
      </div>

      {/* 統計卡片 */}
      {renderStatsCards()}

      {/* 主要功能標籤頁 */}
      <Card className="shadow-lg">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'qa',
              label: (
                <span className="flex items-center">
                  <RobotOutlined className="mr-2" />
                  AI 問答
                </span>
              ),
              children: renderQAInterface()
            },
            {
              key: 'search',
              label: (
                <span className="flex items-center">
                  <SearchOutlined className="mr-2" />
                  知識搜索
                </span>
              ),
              children: renderSearchInterface()
            }
          ]}
        />
      </Card>

      {/* 歷史記錄模態框 (QA歷史) */}
      <Modal
        title="問答歷史記錄"
        open={showHistoryModal}
        onCancel={() => setShowHistoryModal(false)}
        footer={[
          <Button key="close" onClick={() => setShowHistoryModal(false)}>
            關閉
          </Button>,
          <Button key="clear" danger onClick={clearQAHistory}>
            清除所有記錄
          </Button>
        ]}
        width={800}
      >
        {qaHistory.length > 0 ? (
          <List
            dataSource={qaHistory}
            renderItem={(session) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<RobotOutlined className="text-lg text-blue-500" />}
                  title={<Text strong>{session.question}</Text>}
                  description={
                    <div className="space-y-2">
                      <div>
                        <MarkdownRenderer content={session.answer} />
                      </div>
                      <SourceDocumentsDisplay documents={session.sourceDocuments} />
                      <Collapse ghost size="small" className="mb-2">
                        {session.detailedDocumentDataFromAiQuery && (
                          <Panel
                            header="AI 詳細查詢結果"
                            key="modal-detailed-query"
                            extra={<Tooltip title="AI 為了回答問題，對特定文檔進行了深入查詢，並獲取了以下精確信息。"><ApartmentOutlined style={{color: '#8A2BE2'}} /></Tooltip>}
                          >
                            <div className="space-y-2">
                              {session.detailedQueryReasoning && (
                                <div>
                                  <Text strong>AI 查詢原因:</Text>
                                  <Paragraph className="mt-1 p-2 bg-surface-100 rounded text-sm">
                                    {session.detailedQueryReasoning}
                                  </Paragraph>
                                </div>
                              )}
                              <div>
                                <Text strong>查詢到的詳細資料:</Text>
                                <div className="mt-1 p-2 bg-surface-100 rounded text-xs max-h-48 overflow-y-auto">
                                  <pre className="whitespace-pre-wrap font-mono">{JSON.stringify(session.detailedDocumentDataFromAiQuery, null, 2)}</pre>
                                </div>
                              </div>
                            </div>
                          </Panel>
                        )}
                        {session.queryRewriteResult && (
                          <Panel header="查詢重寫過程" key="modal-query-rewrite">
                            {/* 新增：顯示AI分析結果 */}
                            {(session.queryRewriteResult.reasoning || 
                              session.queryRewriteResult.query_granularity || 
                              session.queryRewriteResult.search_strategy_suggestion) && (
                              <div className="mb-4 p-3 bg-blue-50 rounded-lg border-l-4 border-blue-400">
                                <div className="space-y-2">
                                  {session.queryRewriteResult.reasoning && (
                                    <div>
                                      <Text strong style={{color: '#1890ff'}}>🧠 AI分析推理：</Text>
                                      <div className="mt-1 text-sm text-gray-700">
                                        {session.queryRewriteResult.reasoning}
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    {session.queryRewriteResult.query_granularity && (
                                      <div>
                                        <Text strong style={{color: '#52c41a'}}>📊 問題粒度：</Text>
                                        <Tag color={
                                          session.queryRewriteResult.query_granularity === 'thematic' ? 'blue' :
                                          session.queryRewriteResult.query_granularity === 'detailed' ? 'green' : 'orange'
                                        }>
                                          {session.queryRewriteResult.query_granularity === 'thematic' ? '主題級' :
                                           session.queryRewriteResult.query_granularity === 'detailed' ? '細節級' : '不確定'}
                                        </Tag>
                                      </div>
                                    )}
                                    {session.queryRewriteResult.search_strategy_suggestion && (
                                      <div>
                                        <Text strong style={{color: '#722ed1'}}>🎯 建議策略：</Text>
                                        <Tag color={
                                          session.queryRewriteResult.search_strategy_suggestion === 'summary_only' ? 'cyan' :
                                          session.queryRewriteResult.search_strategy_suggestion === 'rrf_fusion' ? 'purple' : 'magenta'
                                        }>
                                          {session.queryRewriteResult.search_strategy_suggestion === 'summary_only' ? '摘要專用' :
                                           session.queryRewriteResult.search_strategy_suggestion === 'rrf_fusion' ? 'RRF融合' : '關鍵詞增強RRF'}
                                        </Tag>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                            <Steps direction="vertical" size="small" current={session.queryRewriteResult.rewritten_queries.length}>
                              <Steps.Step title="原始問題" description={session.queryRewriteResult.original_query} icon={<UserOutlined />} />
                              {session.queryRewriteResult.rewritten_queries.map((rq, idx) => (
                                <Steps.Step key={`modal-rewrite-${idx}`} title={`重寫查詢 ${idx + 1}`} description={rq} icon={<RetweetOutlined />} />
                              ))}
                              {session.queryRewriteResult.intent_analysis && (
                                <Steps.Step title="意圖分析" description={session.queryRewriteResult.intent_analysis} icon={<BulbOutlined />} />
                              )}
                               {session.queryRewriteResult.extracted_parameters && 
                                Object.keys(session.queryRewriteResult.extracted_parameters).length > 0 && (
                                <Steps.Step 
                                  title="提取參數" 
                                  icon={<SlidersOutlined />}
                                  description={
                                    <List
                                      size="small"
                                      dataSource={Object.entries(session.queryRewriteResult.extracted_parameters)}
                                      renderItem={([key, value]) => (
                                        <List.Item>
                                          <Text strong style={{fontSize: '0.8em'}}>{key}: </Text>
                                          <Text style={{fontSize: '0.8em'}}>{JSON.stringify(value)}</Text>
                                        </List.Item>
                                      )}
                                    />
                                  }
                                />
                              )}
                            </Steps>
                          </Panel>
                        )}
                        {session.semanticSearchContexts && session.semanticSearchContexts.length > 0 && (
                          <Panel header={`向量搜索初步結果 (${session.semanticSearchContexts.length} 個)`} key="modal-semantic-search-context">
                            <List
                              dataSource={session.semanticSearchContexts}
                              renderItem={(doc, index) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={<Text strong style={{fontSize: '0.9em'}}>{`匹配 ${index + 1}: ${doc.document_id} (相似度: ${(doc.similarity_score * 100).toFixed(1)}%)`}</Text>}
                                    description={<Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展開' }} style={{fontSize: '0.85em'}}>{doc.summary_or_chunk_text}</Paragraph>}
                                  />
                                </List.Item>
                              )}
                            />
                          </Panel>
                        )}
                        {session.llmContextDocuments && session.llmContextDocuments.length > 0 && (
                          <Panel header={`LLM 使用的上下文 (${session.llmContextDocuments.length} 個片段)`} key="modal-llm-context">
                            <List
                              dataSource={session.llmContextDocuments}
                              renderItem={(doc, index) => (
                                <List.Item>
                                  <List.Item.Meta
                                    title={<Text strong style={{fontSize: '0.9em'}}>{`片段 ${index + 1}: ${doc.document_id} (來源: ${doc.source_type})`}</Text>}
                                    description={<Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展開'}} style={{fontSize: '0.85em'}}>{doc.content_used}</Paragraph>}
                                  />
                                </List.Item>
                              )}
                            />
                          </Panel>
                        )}
                        {session.usedSettings && (
                          <Panel 
                            header="使用的參數設定" 
                            key="used-settings"
                            extra={<Tooltip title="本次查詢使用的具體參數設定"><SettingOutlined style={{color: '#52c41a'}} /></Tooltip>}
                          >
                            <Row gutter={[16, 8]}>
                              <Col xs={12} sm={6}>
                                <Text strong>詳細查詢:</Text><br />
                                <Tag color={session.usedSettings.use_ai_detailed_query ? 'green' : 'default'}>
                                  {session.usedSettings.use_ai_detailed_query ? '啟用' : '禁用'}
                                </Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>上下文數量:</Text><br />
                                <Tag color="blue">{session.usedSettings.context_limit}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>相似度閾值:</Text><br />
                                <Tag color="purple">{(session.usedSettings.similarity_threshold * 100).toFixed(0)}%</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>查詢重寫數:</Text><br />
                                <Tag color="orange">{session.usedSettings.query_rewrite_count}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>候選文件數:</Text><br />
                                <Tag color="cyan">{session.usedSettings.max_documents_for_selection}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>AI選擇限制:</Text><br />
                                <Tag color="magenta">{session.usedSettings.ai_selection_limit}</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>詳細文本長度:</Text><br />
                                <Tag color="gold">{(session.usedSettings.detailed_text_max_length / 1000).toFixed(1)}K</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>單文檔限制:</Text><br />
                                <Tag color="volcano">{(session.usedSettings.max_chars_per_doc / 1000).toFixed(1)}K</Tag>
                              </Col>
                              <Col xs={12} sm={6}>
                                <Text strong>查詢擴展:</Text><br />
                                <Tag color={session.usedSettings.enable_query_expansion ? 'green' : 'default'}>
                                  {session.usedSettings.enable_query_expansion ? '啟用' : '禁用'}
                                </Tag>
                              </Col>
                              {session.usedSettings.prompt_input_max_length && (
                                <Col xs={12} sm={6}>
                                  <Text strong>提示詞輸入限制:</Text><br />
                                  <Tag color="volcano">{(session.usedSettings.prompt_input_max_length / 1000).toFixed(1)}K</Tag>
                                </Col>
                              )}
                            </Row>
                          </Panel>
                        )}
                      </Collapse>
                      <div className="flex flex-wrap gap-2">
                        <Tag color="blue">{session.tokensUsed} tokens</Tag>
                        <Tag color="green">{session.processingTime.toFixed(2)}s</Tag>
                        {session.confidenceScore && (
                          <Tag color="purple">
                            {(session.confidenceScore * 100).toFixed(0)}% 置信度
                          </Tag>
                        )}

                      </div>
                      <Text type="secondary" className="text-xs mt-2 block">
                        {session.timestamp.toLocaleString('zh-TW')}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="暫無問答記錄" />
        )}
      </Modal>
    </div>
  );
};

export default AIQAPage; 