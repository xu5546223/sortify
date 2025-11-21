/**
 * Reasoning Chain Display Component
 * Neo-Brutalism 風格的 AI 推理鏈展示組件
 * 類似 Cursor/Windsurf 的流式狀態機效果
 */
import React, { useState, useEffect } from 'react';
import { Collapse } from 'antd';
import './ReasoningChainDisplay.css';

const { Panel } = Collapse;

export interface ReasoningStep {
  type: 'thought' | 'action' | 'observation' | 'approval' | 'generating';
  stage: string;
  message: string;
  detail?: any;
  status?: 'active' | 'done' | 'pending';
  timestamp?: number;
}

interface ReasoningChainDisplayProps {
  steps: ReasoningStep[];
  isStreaming?: boolean;
  processingTime?: number;
  onApprove?: (action: 'approve_search' | 'skip_search' | 'approve_detail_query' | 'skip_detail_query') => void;
  isApproving?: boolean;
  onClarificationResponse?: (response: string) => void;
  onCitationClick?: (docId: number) => void;
}

const ReasoningChainDisplay: React.FC<ReasoningChainDisplayProps> = ({
  steps,
  isStreaming = false,
  processingTime,
  onApprove,
  isApproving = false,
  onClarificationResponse,
  onCitationClick
}) => {
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  // 根據類型獲取圖標
  const getIcon = (type: string): string => {
    const icons: Record<string, string> = {
      thought: 'ph-bold ph-brain',
      action: 'ph-bold ph-wrench',
      observation: 'ph-bold ph-eye',
      approval: 'ph-bold ph-hand-palm',
      generating: 'ph-bold ph-text-t'
    };
    return icons[type] || 'ph-bold ph-circle';
  };

  // 根據類型獲取標籤文字
  const getLabel = (type: string): string => {
    const labels: Record<string, string> = {
      thought: 'THOUGHT',
      action: 'ACTION',
      observation: 'OBSERVATION',
      approval: 'APPROVAL',
      generating: 'GENERATING'
    };
    return labels[type] || type.toUpperCase();
  };

  // 格式化詳情數據為 JSON
  const formatDetail = (detail: any): string => {
    if (typeof detail === 'string') return detail;
    try {
      return JSON.stringify(detail, null, 2);
    } catch {
      return String(detail);
    }
  };

  return (
    <div className="reasoning-chain-container">
      {/* 頂部狀態條 */}
      <div className="reasoning-chain-header">
        <i className="ph-fill ph-brain text-neo-teal"></i>
        <span className="reasoning-chain-title">Reasoning Chain</span>
        {processingTime && (
          <span className="reasoning-chain-time">{processingTime.toFixed(1)}s</span>
        )}
        {isStreaming && (
          <span className="reasoning-chain-streaming">
            <span className="streaming-dot"></span>
            streaming...
          </span>
        )}
      </div>

      {/* 推理步驟列表 */}
      <div className="reasoning-chain-steps">
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          const statusClass = step.status || 'done';

          return (
            <div
              key={index}
              className={`reasoning-step ${statusClass} ${isLast ? 'last' : ''}`}
            >
              {/* 連接線 */}
              {!isLast && <div className="reasoning-step-line"></div>}

              {/* 步驟圖標 */}
              <div className={`reasoning-step-icon ${statusClass}`}>
                <i className={getIcon(step.type)}></i>
              </div>

              {/* 步驟內容 */}
              <div className="reasoning-step-content">
                {/* 步驟類型標籤 */}
                <div className="reasoning-step-label">
                  {getLabel(step.type)}
                </div>

                {/* 步驟訊息 */}
                <div className="reasoning-step-message">
                  {step.message}
                </div>

                {/* 可折疊的詳細資訊 */}
                {step.detail && (
                  <details className="reasoning-step-details">
                    <summary className="reasoning-details-summary">
                      <span>查看詳細資訊</span>
                      <i className="ph-bold ph-caret-down"></i>
                    </summary>
                    <div className="reasoning-details-content">
                      {/* 特殊處理：查詢重寫結果 */}
                      {step.stage === 'query_rewriting' && step.detail?.queries && Array.isArray(step.detail.queries) ? (
                        <div className="source-documents-list">
                          <p className="documents-label" style={{ fontWeight: 700, marginBottom: '12px', color: '#374151' }}>
                            🔄 重寫後的查詢（{step.detail.queries.length} 個）：
                          </p>
                          <div className="documents-grid" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {step.detail.queries.map((query: string, idx: number) => (
                              <div
                                key={idx}
                                className="document-item"
                                style={{
                                  padding: '12px 16px',
                                  background: '#f9fafb',
                                  border: '2px solid #e5e7eb',
                                  borderRadius: '8px',
                                  transition: 'all 0.2s',
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                                  <span style={{ 
                                    fontSize: '12px', 
                                    fontWeight: 700,
                                    color: '#6b7280',
                                    flexShrink: 0,
                                    marginTop: '2px'
                                  }}>
                                    {idx + 1}.
                                  </span>
                                  <span style={{ 
                                    fontSize: '14px', 
                                    color: '#111827',
                                    lineHeight: '1.6',
                                    flex: 1
                                  }}>
                                    {query}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : /* 特殊處理：搜索結果顯示文檔列表 */
                      step.type === 'observation' && step.detail?.queries && Array.isArray(step.detail.queries) ? (
                        <div className="source-documents-list">
                          <p className="documents-label" style={{ fontWeight: 700, marginBottom: '12px', color: '#374151' }}>
                            找到的文檔：
                          </p>
                          <div className="documents-grid" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {step.detail.queries.slice(0, 5).map((doc: any, idx: number) => (
                              <div
                                key={idx}
                                className="document-item"
                                onClick={() => onCitationClick?.(doc.document_id || idx + 1)}
                                style={{
                                  padding: '12px',
                                  background: 'white',
                                  border: '2px solid #e5e7eb',
                                  borderRadius: '8px',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s',
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.borderColor = '#29bf12';
                                  e.currentTarget.style.transform = 'translateX(4px)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = '#e5e7eb';
                                  e.currentTarget.style.transform = 'translateX(0)';
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                  <i className="ph-fill ph-file-text" style={{ color: '#29bf12', fontSize: '16px' }}></i>
                                  <span style={{ fontWeight: 600, fontSize: '13px', color: '#111827' }}>
                                    {doc.filename || doc.document_name || `文檔 ${idx + 1}`}
                                  </span>
                                  <span style={{ 
                                    marginLeft: 'auto', 
                                    fontSize: '11px', 
                                    padding: '2px 8px', 
                                    background: '#f0fdf4', 
                                    color: '#166534', 
                                    borderRadius: '4px',
                                    fontWeight: 600
                                  }}>
                                    {(doc.score * 100).toFixed(0)}%
                                  </span>
                                </div>
                                {doc.extracted_text && (
                                  <p style={{ 
                                    fontSize: '12px', 
                                    color: '#6b7280', 
                                    marginTop: '4px',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical'
                                  }}>
                                    {doc.extracted_text.substring(0, 100)}...
                                  </p>
                                )}
                              </div>
                            ))}
                            {step.detail.queries.length > 5 && (
                              <p style={{ fontSize: '12px', color: '#9ca3af', textAlign: 'center', marginTop: '4px' }}>
                                還有 {step.detail.queries.length - 5} 個文檔...
                              </p>
                            )}
                          </div>
                        </div>
                      ) : typeof step.detail === 'object' && !Array.isArray(step.detail) ? (
                        <pre className="reasoning-code-block">
                          {formatDetail(step.detail)}
                        </pre>
                      ) : (
                        <div className="reasoning-detail-text">
                          {String(step.detail)}
                        </div>
                      )}
                    </div>
                  </details>
                )}

                {/* 批准卡片 - 文檔搜索 */}
                {step.type === 'approval' && step.status === 'active' && step.detail?.current_step === 'awaiting_search_approval' && onApprove && (
                  <div className="reasoning-approval-card">
                    <div className="approval-card-header">
                      <i className="ph-fill ph-lock-key"></i>
                      <span>需要權限批准：文檔搜索</span>
                    </div>
                    <div className="approval-card-content">
                      <p className="approval-description">
                        AI 準備在數據庫中搜索相關文檔，這可能會：
                      </p>
                      <ul className="approval-list">
                        <li>• 預計搜索 {step.detail.estimated_documents || '若干'} 個文檔</li>
                        <li>• 使用語義搜索技術</li>
                        <li>• 耗時約 {step.detail.estimated_time || '幾秒鐘'}</li>
                      </ul>
                      
                      {/* 顯示查詢重寫結果（如果有） */}
                      {step.detail.query_rewrite_result?.rewritten_queries && step.detail.query_rewrite_result.rewritten_queries.length > 0 && (
                        <div style={{ marginTop: '16px', marginBottom: '12px' }}>
                          <p className="documents-label" style={{ fontWeight: 600, fontSize: '12px', color: '#374151', marginBottom: '8px' }}>
                            🔄 優化後的搜索查詢：
                          </p>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {step.detail.query_rewrite_result.rewritten_queries.slice(0, 3).map((query: string, idx: number) => (
                              <div
                                key={idx}
                                style={{
                                  padding: '8px 12px',
                                  background: '#f0fdf4',
                                  border: '1px solid #86efac',
                                  borderRadius: '6px',
                                  fontSize: '13px',
                                  color: '#166534',
                                  display: 'flex',
                                  gap: '8px'
                                }}
                              >
                                <span style={{ fontWeight: 700, flexShrink: 0 }}>{idx + 1}.</span>
                                <span>{query}</span>
                              </div>
                            ))}
                            {step.detail.query_rewrite_result.rewritten_queries.length > 3 && (
                              <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '4px' }}>
                                還有 {step.detail.query_rewrite_result.rewritten_queries.length - 3} 個查詢...
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                      
                      <div className="approval-actions">
                        <button
                          onClick={() => onApprove('approve_search')}
                          disabled={isApproving}
                          className="approval-button approve"
                        >
                          ✅ 批准搜索
                        </button>
                        <button
                          onClick={() => onApprove('skip_search')}
                          disabled={isApproving}
                          className="approval-button skip"
                        >
                          ⏭️ 跳過
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* 批准卡片 - 詳細查詢 */}
                {step.type === 'approval' && step.status === 'active' && step.detail?.current_step === 'awaiting_detail_query_approval' && onApprove && (
                  <div className="reasoning-approval-card">
                    <div className="approval-card-header">
                      <i className="ph-fill ph-database"></i>
                      <span>需要權限批准：詳細查詢</span>
                    </div>
                    <div className="approval-card-content">
                      <p className="approval-description">
                        AI 準備執行 MongoDB 詳細查詢以獲取更多信息：
                      </p>
                      {step.detail.document_names && step.detail.document_names.length > 0 && (
                        <div className="approval-documents">
                          <p className="documents-label">目標文檔：</p>
                          <ul className="documents-list">
                            {step.detail.document_names.slice(0, 3).map((name: string, idx: number) => (
                              <li key={idx}>• {name}</li>
                            ))}
                            {step.detail.document_names.length > 3 && (
                              <li>• 還有 {step.detail.document_names.length - 3} 個...</li>
                            )}
                          </ul>
                        </div>
                      )}
                      <div className="approval-actions">
                        <button
                          onClick={() => onApprove('approve_detail_query')}
                          disabled={isApproving}
                          className="approval-button approve"
                        >
                          ✅ 批准查詢
                        </button>
                        <button
                          onClick={() => onApprove('skip_detail_query')}
                          disabled={isApproving}
                          className="approval-button skip"
                        >
                          ⏭️ 跳過
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* 澄清卡片 */}
                {step.type === 'approval' && step.status === 'active' && step.detail?.current_step === 'need_clarification' && onClarificationResponse && (
                  <div className="reasoning-approval-card">
                    <div className="approval-card-header" style={{ background: 'linear-gradient(135deg, #facc15 0%, #fde047 100%)' }}>
                      <i className="ph-fill ph-question"></i>
                      <span>需要澄清問題</span>
                    </div>
                    <div className="approval-card-content">
                      <p className="approval-description" style={{ color: '#713f12' }}>
                        {step.detail.clarification_question || '需要更多資訊以繼續'}
                      </p>
                      {step.detail.suggested_responses && step.detail.suggested_responses.length > 0 && (
                        <div className="approval-documents">
                          <p className="documents-label" style={{ color: '#854d0e' }}>建議回答：</p>
                          <div className="approval-actions" style={{ gap: '8px', flexWrap: 'wrap' }}>
                            {step.detail.suggested_responses.map((suggestion: string, idx: number) => (
                              <button
                                key={idx}
                                onClick={() => onClarificationResponse(suggestion)}
                                disabled={isApproving}
                                className="approval-button"
                                style={{ 
                                  flex: '0 0 auto',
                                  background: 'white',
                                  color: '#854d0e',
                                  borderColor: '#facc15'
                                }}
                              >
                                {suggestion}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      <p className="text-xs mt-3" style={{ color: '#a16207' }}>
                        💡 請在下方輸入框提供更多資訊
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 流式輸出的游標效果 */}
      {isStreaming && steps.length > 0 && (
        <div className="reasoning-cursor">▋</div>
      )}
    </div>
  );
};

export default ReasoningChainDisplay;
