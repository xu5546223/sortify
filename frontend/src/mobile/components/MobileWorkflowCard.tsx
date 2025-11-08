/**
 * 手機端工作流卡片組件
 * 
 * 適配手機端的澄清問題、搜索批准、詳細查詢批准等互動
 */
import React, { useState } from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  FileTextOutlined,
  SendOutlined
} from '@ant-design/icons';

interface MobileWorkflowCardProps {
  type: 'clarification' | 'search_approval' | 'detail_query_approval';
  
  // 澄清問題相關
  clarificationQuestion?: string;
  suggestedResponses?: string[];
  onSubmitClarification?: (text: string) => void;
  onFillMainInput?: (text: string) => void;
  
  // 搜索批准相關
  searchPreview?: {
    original_question: string;
    ai_understanding: string;
    will_use_rewrite?: boolean;
  };
  onApproveSearch?: () => void;
  onSkipSearch?: () => void;
  
  // 詳細查詢批准相關
  documentNames?: string[];
  queryType?: string;
  onApproveDetailQuery?: () => void;
  onSkipDetailQuery?: () => void;
  
  // 通用
  isLoading?: boolean;
}

const MobileWorkflowCard: React.FC<MobileWorkflowCardProps> = ({
  type,
  clarificationQuestion,
  suggestedResponses,
  onSubmitClarification,
  onFillMainInput,
  searchPreview,
  onApproveSearch,
  onSkipSearch,
  documentNames,
  queryType,
  onApproveDetailQuery,
  onSkipDetailQuery,
  isLoading = false
}) => {

  // 渲染澄清問題卡片
  const renderClarificationCard = () => (
    <div className="mobile-workflow-card clarification">
      <div className="card-header">
        <QuestionCircleOutlined className="card-icon" />
        <span className="card-title">需要澄清</span>
      </div>
      
      <div className="card-body">
        <p className="clarification-question">
          {clarificationQuestion}
        </p>
        
        {/* 快速選項 */}
        {suggestedResponses && suggestedResponses.length > 0 && (
          <div className="quick-options">
            <div className="quick-options-label">💡 快速選擇（點擊填入下方輸入框）：</div>
            <div className="quick-options-list">
              {suggestedResponses.map((option, idx) => (
                <button
                  key={idx}
                  className="quick-option-btn"
                  onClick={() => onFillMainInput?.(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        )}
        
        <div style={{ 
          marginTop: '12px', 
          padding: '8px 12px', 
          background: '#f0f7ff', 
          borderRadius: '6px',
          fontSize: '13px',
          color: '#595959',
          textAlign: 'center'
        }}>
          💬 請在下方輸入框中輸入您的回答
        </div>
      </div>
    </div>
  );

  // 渲染搜索批准卡片
  const renderSearchApprovalCard = () => (
    <div className="mobile-workflow-card search-approval">
      <div className="card-header">
        <SearchOutlined className="card-icon" />
        <span className="card-title">需要查找文檔</span>
      </div>
      
      <div className="card-body">
        <p className="approval-description">
          AI 需要查找您的文檔庫以提供更準確的答案
        </p>
        
        {/* AI 理解的查詢預覽 */}
        {searchPreview && (
          <div className="search-preview">
            <div className="preview-title">🔍 AI 理解的查詢</div>
            <div className="preview-item">
              <span className="preview-label">您的問題：</span>
              <span className="preview-value">{searchPreview.original_question}</span>
            </div>
            <div className="preview-item">
              <span className="preview-label">AI 理解為：</span>
              <span className="preview-value highlight">
                {searchPreview.ai_understanding}
              </span>
            </div>
            {searchPreview.will_use_rewrite && (
              <div className="preview-note">
                💡 將使用 AI 查詢重寫功能進一步優化搜索
              </div>
            )}
          </div>
        )}
        
        {/* 操作按鈕 */}
        <div className="action-buttons">
          <button
            className="action-btn primary"
            onClick={onApproveSearch}
            disabled={isLoading}
          >
            <CheckCircleOutlined />
            {isLoading ? '搜索中...' : '批准搜索'}
          </button>
          <button
            className="action-btn secondary"
            onClick={onSkipSearch}
            disabled={isLoading}
          >
            <CloseCircleOutlined />
            跳過搜索
          </button>
        </div>
        
        <div className="action-hint">
          💡 跳過搜索將基於 AI 的通用知識回答
        </div>
      </div>
    </div>
  );

  // 渲染詳細查詢批准卡片
  const renderDetailQueryApprovalCard = () => (
    <div className="mobile-workflow-card detail-query-approval">
      <div className="card-header">
        <FileTextOutlined className="card-icon" />
        <span className="card-title">需要查詢詳細數據</span>
      </div>
      
      <div className="card-body">
        <p className="approval-description">
          AI 將對已找到的文檔執行精確查詢，提取具體數據（如金額、日期、人名等）
        </p>
        
        {/* 目標文檔列表 */}
        {documentNames && documentNames.length > 0 && (
          <div className="document-list">
            <div className="document-list-title">📄 目標文檔：</div>
            {documentNames.map((name, idx) => (
              <div key={idx} className="document-item">
                <CheckCircleOutlined className="document-check" />
                <span className="document-name">{name}</span>
              </div>
            ))}
            <div className="document-list-note">
              💡 將使用 MongoDB 精確查詢提取詳細信息
            </div>
          </div>
        )}
        
        {/* 操作按鈕 */}
        <div className="action-buttons">
          <button
            className="action-btn primary"
            onClick={onApproveDetailQuery}
            disabled={isLoading}
          >
            <CheckCircleOutlined />
            {isLoading ? '查詢中...' : '批准查詢'}
          </button>
          <button
            className="action-btn secondary"
            onClick={onSkipDetailQuery}
            disabled={isLoading}
          >
            <CloseCircleOutlined />
            使用摘要回答
          </button>
        </div>
        
        <div className="action-hint">
          💡 跳過將使用文檔摘要回答，可能不夠精確
        </div>
      </div>
    </div>
  );

  // 根據類型渲染對應的卡片
  switch (type) {
    case 'clarification':
      return renderClarificationCard();
    case 'search_approval':
      return renderSearchApprovalCard();
    case 'detail_query_approval':
      return renderDetailQueryApprovalCard();
    default:
      return null;
  }
};

export default MobileWorkflowCard;

