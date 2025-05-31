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
  Collapse
} from 'antd';
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
  SlidersOutlined
} from '@ant-design/icons';
import type {
  AIQARequest,
  AIQAResponse,
  VectorDatabaseStats,
  Document,
  QueryRewriteResult,
  LLMContextDocument,
  SemanticContextDocument,
  AIQARequestUnified,
  AIResponse
} from '../types/apiTypes';
import { askAIQuestionUnified } from '../services/unifiedAIService';
import { getVectorDatabaseStats } from '../services/vectorDBService';
import SemanticSearchInterface from '../components/SemanticSearchInterface';

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
  sessionId?: string;
}

const AIQAPage: React.FC<AIQAPageProps> = ({ showPCMessage }) => {
  // 狀態管理
  const [vectorStats, setVectorStats] = useState<VectorDatabaseStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // AI 問答相關狀態
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [qaHistory, setQAHistory] = useState<QASession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  
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
        use_semantic_search: true,
        context_limit: 10,
        ensure_chinese_output: true
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
        sessionId: responseContent.session_id || undefined
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
            <Text type="secondary">按 Ctrl+Enter 發送問題</Text>
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
                      <Paragraph 
                        ellipsis={{ rows: 3, expandable: true, symbol: '展開' }}
                        className="text-sm mb-2"
                      >
                        {session.answer}
                      </Paragraph>
                      <Collapse ghost size="small" className="mb-2">
                        {session.queryRewriteResult && (
                          <Panel 
                            header="查詢重寫過程" 
                            key="query-rewrite"
                            extra={<Tooltip title="AI如何理解並優化您的問題"><InfoCircleOutlined style={{color: '#1890ff'}} /></Tooltip>}
                          >
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
                      </Collapse>

                      {session.sourceDocuments.length > 0 && (
                        <div>
                          <Text type="secondary" className="text-xs">
                            參考文檔: {session.sourceDocuments.length} 個
                          </Text>
                        </div>
                      )}
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
                      <Paragraph ellipsis={{ rows: 3, expandable: true }}>
                        {session.answer}
                      </Paragraph>
                      <Collapse ghost size="small" className="mb-2">
                        {session.queryRewriteResult && (
                          <Panel header="查詢重寫過程" key="modal-query-rewrite">
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
                      </Collapse>
                      <div className="flex flex-wrap gap-2">
                        <Tag color="blue">{session.tokensUsed} tokens</Tag>
                        <Tag color="green">{session.processingTime.toFixed(2)}s</Tag>
                        {session.confidenceScore && (
                          <Tag color="purple">
                            {(session.confidenceScore * 100).toFixed(0)}% 置信度
                          </Tag>
                        )}
                        <Tag color="default">
                          {session.sourceDocuments.length} 個主要參考文檔
                        </Tag>
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