/**
 * QA工作流顯示組件
 * 
 * 展示AI問答的漸進式處理流程,類似Cursor的交互模式
 */
import React from 'react';
import {
  Card,
  Space,
  Alert,
  Button,
  List,
  Tag,
  Avatar,
  Typography,
  Input,
  Spin,
  Progress,
  Steps
} from 'antd';
import {
  BulbOutlined,
  FileSearchOutlined,
  QuestionCircleOutlined,
  CheckOutlined,
  CloseOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  SendOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import {
  QAWorkflowStep,
  QuestionIntent,
  WorkflowState,
  INTENT_LABELS,
  getIntentColor,
  getCurrentStepIndex
} from '../types/qaWorkflow';
import '../styles/qaWorkflow.css';

const { Text, Paragraph } = Typography;
const { Step } = Steps;

interface QAWorkflowDisplayProps {
  workflowState: WorkflowState;
  onApproveSearch?: () => void;
  onSkipSearch?: () => void;
  onApproveDetailQuery?: () => void;  // ⭐ 新增
  onSkipDetailQuery?: () => void;     // ⭐ 新增
  onConfirmDocuments?: () => void;
  onRequestMoreSearch?: () => void;
  onSubmitClarification?: (clarification: string) => void;
  onQuickResponse?: (response: string) => void;
  isSearching?: boolean;
  generationProgress?: number;
}

const QAWorkflowDisplay: React.FC<QAWorkflowDisplayProps> = ({
  workflowState,
  onApproveSearch,
  onSkipSearch,
  onApproveDetailQuery,  // ⭐ 新增
  onSkipDetailQuery,     // ⭐ 新增
  onConfirmDocuments,
  onRequestMoreSearch,
  onSubmitClarification,
  onQuickResponse,
  isSearching = false,
  generationProgress = 0
}) => {
  const [clarificationInput, setClarificationInput] = React.useState('');

  const handleSubmitClarification = () => {
    if (clarificationInput.trim() && onSubmitClarification) {
      onSubmitClarification(clarificationInput);
      setClarificationInput('');
    }
  };

  const handleQuickResponse = (option: string) => {
    if (onQuickResponse) {
      onQuickResponse(option);
    }
  };

  // 流程步驟指示器（精簡版，不占太多空間）
  const renderProcessingTimeline = () => {
    // 只在真正需要時顯示，澄清和批准階段不顯示
    if (workflowState.currentStep === QAWorkflowStep.COMPLETED || 
        workflowState.currentStep === QAWorkflowStep.ERROR ||
        workflowState.currentStep === QAWorkflowStep.NEED_CLARIFICATION ||
        workflowState.currentStep === QAWorkflowStep.AWAITING_SEARCH_APPROVAL) {
      return null;
    }

    return null; // 暫時完全隱藏，節省空間
  };

  // 分類結果展示 - 簡化版，不占太多空間
  const renderClassificationResult = () => {
    // 分類結果不需要單獨顯示，直接進入對應的UI即可
    return null;
  };

  // 澄清問題交互
  const renderClarificationCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.NEED_CLARIFICATION) {
      return null;
    }

    return (
      <Card className="clarification-card" bordered={false}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* 澄清問題標題 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <QuestionCircleOutlined style={{ color: '#faad14', fontSize: '20px' }} />
            <Text strong style={{ fontSize: '15px', color: '#d46b08' }}>需要澄清</Text>
          </div>

          {/* 澄清問題內容 */}
          <div style={{ paddingLeft: '28px' }}>
            <Paragraph style={{ marginBottom: 16, color: '#595959' }}>
              {workflowState.clarificationQuestion}
            </Paragraph>

            {/* 建議的回答選項 */}
            {workflowState.suggestedResponses && workflowState.suggestedResponses.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Text type="secondary" style={{ fontSize: '13px', display: 'block', marginBottom: 8 }}>
                  💡 快速選擇:
                </Text>
                <Space wrap size="small">
                  {workflowState.suggestedResponses.map((option, idx) => (
                    <Button
                      key={idx}
                      size="middle"
                      onClick={() => handleQuickResponse(option)}
                      style={{ borderRadius: '6px' }}
                    >
                      {option}
                    </Button>
                  ))}
                </Space>
              </div>
            )}

            {/* 自定義輸入 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <Text type="secondary" style={{ fontSize: '13px' }}>或輸入自定義回答:</Text>
              <div style={{ display: 'flex', gap: '8px' }}>
                <Input.TextArea
                  placeholder="請輸入更詳細的說明..."
                  value={clarificationInput}
                  onChange={(e) => setClarificationInput(e.target.value)}
                  autoSize={{ minRows: 2, maxRows: 3 }}
                  style={{ flex: 1 }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSubmitClarification}
                  disabled={!clarificationInput.trim()}
                  style={{ alignSelf: 'flex-end' }}
                >
                  提交
                </Button>
              </div>
            </div>
          </div>
        </Space>
      </Card>
    );
  };

  // 搜索批准卡片
  const renderSearchApprovalCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.AWAITING_SEARCH_APPROVAL) {
      return null;
    }

    // 獲取搜索預覽信息
    const searchPreview = (workflowState as any).search_preview;

    return (
      <Card className="approval-card search-approval">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div className="approval-header">
            <Avatar icon={<FileSearchOutlined />} style={{ backgroundColor: '#1890ff' }} size={48} />
            <div className="approval-content">
              <Text strong>需要查找文檔</Text>
              <Paragraph type="secondary">
                AI 需要查找您的文檔庫以提供更準確的答案。這可能需要幾秒鐘時間。
              </Paragraph>
            </div>
          </div>

          {/* AI理解的查詢預覽 */}
          {searchPreview && (
            <div style={{ 
              background: '#f0f7ff', 
              padding: '12px 16px', 
              borderRadius: '8px',
              border: '1px solid #91d5ff'
            }}>
              <div style={{ marginBottom: 8 }}>
                <Text strong style={{ fontSize: '13px', color: '#1890ff' }}>
                  🔍 AI 理解的查詢:
                </Text>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: '12px' }}>您的問題:</Text>
                <Text style={{ fontSize: '13px' }}>{searchPreview.original_question}</Text>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <Text type="secondary" style={{ fontSize: '12px', whiteSpace: 'nowrap' }}>AI 理解為:</Text>
                <Text strong style={{ fontSize: '14px', color: '#1890ff' }}>
                  {searchPreview.ai_understanding}
                </Text>
              </div>
              {searchPreview.will_use_rewrite && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: '11px', fontStyle: 'italic' }}>
                    💡 將使用 AI 查詢重寫功能進一步優化搜索
                  </Text>
                </div>
              )}
            </div>
          )}

          {/* 操作按鈕 */}
          <div className="approval-actions">
            <Space size="middle">
              <Button
                type="primary"
                icon={<CheckOutlined />}
                onClick={onApproveSearch}
                loading={isSearching}
                size="large"
              >
                批准搜索
              </Button>
              <Button
                icon={<CloseOutlined />}
                onClick={onSkipSearch}
                size="large"
              >
                跳過,直接回答
              </Button>
            </Space>
            <Text type="secondary" style={{ fontSize: '12px', marginTop: 8, textAlign: 'center', display: 'block' }}>
              💡 提示: 跳過搜索將基於 AI 的通用知識回答
            </Text>
          </div>
        </Space>
      </Card>
    );
  };

  // 詳細查詢批准卡片 ⭐ 新增
  const renderDetailQueryApprovalCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.AWAITING_DETAIL_QUERY_APPROVAL) {
      return null;
    }

    const targetDocs = (workflowState as any).document_names || [];
    const queryType = (workflowState as any).query_type || '詳細數據查詢';

    return (
      <Card className="approval-card detail-query-approval">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div className="approval-header">
            <Avatar icon={<FileTextOutlined />} style={{ backgroundColor: '#52c41a' }} size={48} />
            <div className="approval-content">
              <Text strong>需要查詢文檔詳細數據</Text>
              <Paragraph type="secondary">
                AI 將對已找到的文檔執行精確查詢，提取具體數據（如金額、日期、人名等）。
              </Paragraph>
            </div>
          </div>

          {/* 目標文檔預覽 */}
          {targetDocs.length > 0 && (
            <div style={{ 
              background: '#f6ffed', 
              padding: '12px 16px', 
              borderRadius: '8px',
              border: '1px solid #b7eb8f'
            }}>
              <div style={{ marginBottom: 8 }}>
                <Text strong style={{ fontSize: '13px', color: '#52c41a' }}>
                  📄 目標文檔:
                </Text>
              </div>
              {targetDocs.map((name: string, idx: number) => (
                <div key={idx} style={{ marginLeft: 8, marginBottom: 4 }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 4 }} />
                  <Text style={{ fontSize: '13px' }}>{name}</Text>
                </div>
              ))}
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: '11px', fontStyle: 'italic' }}>
                  💡 將使用 MongoDB 精確查詢提取詳細信息
                </Text>
              </div>
            </div>
          )}

          {/* 操作按鈕 */}
          <div className="approval-actions">
            <Space size="middle">
              <Button
                type="primary"
                icon={<CheckOutlined />}
                onClick={onApproveDetailQuery}
                loading={isSearching}
                size="large"
              >
                批准查詢
              </Button>
              <Button
                icon={<CloseOutlined />}
                onClick={onSkipDetailQuery}
                size="large"
              >
                跳過,使用摘要回答
              </Button>
            </Space>
            <Text type="secondary" style={{ fontSize: '12px', marginTop: 8, textAlign: 'center', display: 'block' }}>
              💡 提示: 跳過將使用文檔摘要回答，可能不夠精確
            </Text>
          </div>
        </Space>
      </Card>
    );
  };

  // 搜索中動畫
  const renderSearchingCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.SEARCHING_DOCUMENTS) {
      return null;
    }

    return (
      <Card style={{ textAlign: 'center', padding: '24px' }}>
        <Space direction="vertical" align="center" style={{ width: '100%' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} spin />} />
          <Text type="secondary">正在搜索相關文檔...</Text>
        </Space>
      </Card>
    );
  };
  
  // 查詢詳細數據中動畫 ⭐ 新增
  const renderQueryingDetailsCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.QUERYING_DETAILS) {
      return null;
    }

    return (
      <Card style={{ textAlign: 'center', padding: '24px' }}>
        <Space direction="vertical" align="center" style={{ width: '100%' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 32, color: '#52c41a' }} spin />} />
          <Text type="secondary">正在查詢文檔詳細數據...</Text>
        </Space>
      </Card>
    );
  };

  // 文檔搜索結果展示
  const renderDocumentsFoundCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.DOCUMENTS_FOUND || !workflowState.foundDocuments) {
      return null;
    }

    return (
      <Card className="documents-found-card">
        <div className="documents-header">
          <CheckCircleOutlined style={{ color: '#52c41a', fontSize: '24px' }} />
          <Text strong>找到 {workflowState.foundDocuments.length} 個相關文檔</Text>
        </div>

        {/* 文檔列表 */}
        <List
          size="small"
          dataSource={workflowState.foundDocuments}
          renderItem={(doc) => (
            <List.Item>
              <List.Item.Meta
                avatar={<FileTextOutlined style={{ fontSize: '20px', color: '#1890ff' }} />}
                title={doc.filename}
                description={
                  <div style={{ 
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical'
                  }}>
                    <Text type="secondary">{doc.summary}</Text>
                  </div>
                }
              />
              <Tag color="blue">{(doc.similarity * 100).toFixed(0)}% 相關</Tag>
            </List.Item>
          )}
        />

        {/* 確認是否足夠回答 */}
        <Alert
          type="info"
          message="這些資料足夠回答您的問題嗎?"
          action={
            <Space>
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                onClick={onConfirmDocuments}
              >
                足夠,生成答案
              </Button>
              <Button size="small" onClick={onRequestMoreSearch}>
                繼續查找
              </Button>
            </Space>
          }
          style={{ margin: '16px' }}
        />
      </Card>
    );
  };

  // 答案生成進度
  const renderGeneratingCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.GENERATING_ANSWER) {
      return null;
    }

    return (
      <Card className="generating-card">
        <Space direction="vertical" align="center" style={{ width: '100%' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 32, color: 'white' }} spin />} />
          <Text style={{ color: 'white', fontSize: '16px' }}>
            AI 正在基於找到的文檔生成答案...
          </Text>
          {generationProgress > 0 && (
            <Progress
              percent={generationProgress}
              size="small"
              status="active"
              showInfo={false}
              strokeColor="white"
            />
          )}
        </Space>
      </Card>
    );
  };

  // 錯誤顯示
  const renderErrorCard = () => {
    if (workflowState.currentStep !== QAWorkflowStep.ERROR || !workflowState.errorMessage) {
      return null;
    }

    return (
      <Alert
        type="error"
        message="處理失敗"
        description={workflowState.errorMessage}
        showIcon
      />
    );
  };

  return (
    <div className="qa-workflow-display">
      {renderProcessingTimeline()}
      {renderClassificationResult()}
      {renderClarificationCard()}
      {renderSearchApprovalCard()}
      {renderDetailQueryApprovalCard()}  {/* ⭐ 新增 */}
      {renderSearchingCard()}
      {renderQueryingDetailsCard()}      {/* ⭐ 新增 */}
      {renderDocumentsFoundCard()}
      {renderGeneratingCard()}
      {renderErrorCard()}
    </div>
  );
};

export default QAWorkflowDisplay;

