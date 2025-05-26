import React from 'react';
import { Card, Button } from './index';
import { Descriptions, Alert, Collapse, Tag, Tooltip } from 'antd';
import { Document, DocumentAnalysis, AITextAnalysisOutput, AITextAnalysisIntermediateStep } from '../services/api';
import {
  InfoCircleOutlined,
  CloudUploadOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
  FileProtectOutlined
} from '@ant-design/icons';

interface DocumentDetailsModalProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

// 輔助函數：格式化文件大小
const formatBytes = (bytes?: number, decimals = 2): string => {
  if (bytes === undefined || bytes === null || bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

// 輔助函數：格式化日期
const formatDate = (dateString?: string): string => {
  if (!dateString) return 'N/A';
  try {
    let adjustedDateString = dateString;
    if (dateString.includes('T') && !dateString.endsWith('Z') && dateString.length >= 19) {
      adjustedDateString = dateString + 'Z';
    }
    const dateObj = new Date(adjustedDateString);
    return dateObj.toLocaleString('zh-TW', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch (e) {
    console.error("Error formatting date:", dateString, e);
    return dateString;
  }
};

// 輔助函數：文件類型映射
const mapMimeTypeToSimpleType = (mimeType?: string | null): string => {
  if (!mimeType) return '未知類型';

  const lowerMimeType = mimeType.toLowerCase();

  // 精確匹配
  if (lowerMimeType === 'application/pdf') return 'PDF 文件';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return 'Word 文件 (DOCX)';
  if (lowerMimeType === 'application/msword') return 'Word 文件 (DOC)';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') return 'Excel 文件 (XLSX)';
  if (lowerMimeType === 'application/vnd.ms-excel') return 'Excel 文件 (XLS)';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') return 'PowerPoint 文件 (PPTX)';
  if (lowerMimeType === 'application/vnd.ms-powerpoint') return 'PowerPoint 文件 (PPT)';
  if (lowerMimeType === 'application/zip') return 'ZIP 壓縮檔';
  if (lowerMimeType === 'application/json') return 'JSON 文件';
  if (lowerMimeType === 'application/xml') return 'XML 文件';

  // 前綴匹配
  if (lowerMimeType.startsWith('text/plain')) return '純文字文件';
  if (lowerMimeType.startsWith('text/')) return '文字文件';
  if (lowerMimeType.startsWith('image/jpeg')) return 'JPEG 圖片';
  if (lowerMimeType.startsWith('image/png')) return 'PNG 圖片';
  if (lowerMimeType.startsWith('image/gif')) return 'GIF 圖片';
  if (lowerMimeType.startsWith('image/svg+xml')) return 'SVG 圖片';
  if (lowerMimeType.startsWith('image/')) return '圖片';
  if (lowerMimeType.startsWith('audio/')) return '音訊檔案';
  if (lowerMimeType.startsWith('video/')) return '影片檔案';

  return mimeType;
};

// 獲取狀態顯示文本的輔助函數
const getStatusText = (status: string): string => {
  switch (status) {
    case 'uploaded': return '已上傳';
    case 'pending_extraction': return '等待提取';
    case 'text_extracted': return '文本已提取';
    case 'extraction_failed': return '提取失敗';
    case 'pending_analysis': return '等待分析';
    case 'analyzing': return '分析中';
    case 'analysis_completed': return '分析完成';
    case 'analysis_failed': return '分析失敗';
    case 'processing_error': return '處理錯誤';
    case 'completed': return '已完成';
    default: return status;
  }
};

// 狀態標籤組件
const DocumentStatusTag: React.FC<{ status: string; errorDetails?: string | null }> = ({ status, errorDetails }) => {
  let color = 'default';
  let icon = <InfoCircleOutlined />;

  switch (status) {
    case 'uploaded': color = 'blue'; icon = <CloudUploadOutlined />; break;
    case 'pending_extraction': color = 'gold'; icon = <ClockCircleOutlined />; break;
    case 'text_extracted': color = 'geekblue'; icon = <FileTextOutlined />; break;
    case 'extraction_failed': color = 'volcano'; icon = <ExclamationCircleOutlined />; break;
    case 'pending_analysis': color = 'orange'; icon = <ExperimentOutlined />; break;
    case 'analyzing': color = 'purple'; icon = <SyncOutlined spin />; break;
    case 'analysis_completed': color = 'green'; icon = <CheckCircleOutlined />; break;
    case 'analysis_failed': color = 'red'; icon = <CloseCircleOutlined />; break;
    case 'processing_error': color = 'magenta'; icon = <WarningOutlined />; break;
    case 'completed': color = 'cyan'; icon = <FileProtectOutlined />; break;
    default: break;
  }

  return (
    <Tag icon={icon} color={color}>
      {getStatusText(status)}
      {errorDetails && (status === 'processing_error' || status === 'extraction_failed' || status === 'analysis_failed') && (
        <Tooltip title={errorDetails}>
          <QuestionCircleOutlined style={{ marginLeft: 4, color: 'red' }} />
        </Tooltip>
      )}
    </Tag>
  );
};

// 基本資訊組件
const DocumentBasicInfo: React.FC<{ document: Document }> = ({ document }) => {
  return (
    <Descriptions bordered column={1} size="small">
      <Descriptions.Item label="文件 ID">{document.id}</Descriptions.Item>
      <Descriptions.Item label="文件名稱">{document.filename}</Descriptions.Item>
      <Descriptions.Item label="文件類型">{mapMimeTypeToSimpleType(document.file_type)}</Descriptions.Item>
      <Descriptions.Item label="文件大小">{formatBytes(document.size ?? undefined)}</Descriptions.Item>
      <Descriptions.Item label="上傳時間">{formatDate(document.created_at)}</Descriptions.Item>
      <Descriptions.Item label="最後修改">{formatDate(document.updated_at)}</Descriptions.Item>
      <Descriptions.Item label="狀態">
        <DocumentStatusTag status={document.status} errorDetails={document.error_details} />
      </Descriptions.Item>
      {document.owner_id && (
        <Descriptions.Item label="擁有者 ID">{document.owner_id}</Descriptions.Item>
      )}
      {document.file_path && (
        <Descriptions.Item label="文件路徑">{document.file_path}</Descriptions.Item>
      )}
      {document.tags && document.tags.length > 0 && (
        <Descriptions.Item label="標籤">
          {document.tags.map(tag => (
            <Tag key={tag} color="blue">{tag}</Tag>
          ))}
        </Descriptions.Item>
      )}
    </Descriptions>
  );
};

// 提取文本組件
const ExtractedTextSection: React.FC<{ extractedText: string }> = ({ extractedText }) => {
  return (
    <div className="mt-4">
      <h4 className="font-semibold text-sm mb-2 text-gray-700">提取文本</h4>
      <div className="p-3 border rounded bg-surface-100 max-h-48 overflow-y-auto">
        <pre className="text-xs whitespace-pre-wrap font-mono">{extractedText}</pre>
      </div>
    </div>
  );
};

// AI 分析結果組件
const DocumentAnalysisInfo: React.FC<{ analysis: DocumentAnalysis }> = ({ analysis }) => {
  const aiOutput = analysis.ai_analysis_output as AITextAnalysisOutput;

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <h4 className="text-md font-semibold mb-3 text-gray-700">
        AI 分析結果 (模型: {analysis.analysis_model_used || aiOutput?.model_used || '未知'})
      </h4>

      <Descriptions bordered column={1} size="small">
        {analysis.tokens_used !== null && analysis.tokens_used !== undefined && (
          <Descriptions.Item label="Tokens 使用量">{analysis.tokens_used}</Descriptions.Item>
        )}
        {analysis.analysis_started_at && (
          <Descriptions.Item label="分析開始時間">{formatDate(analysis.analysis_started_at)}</Descriptions.Item>
        )}
        {analysis.analysis_completed_at && (
          <Descriptions.Item label="分析完成時間">{formatDate(analysis.analysis_completed_at)}</Descriptions.Item>
        )}
        {analysis.error_message && (
          <Descriptions.Item label="分析過程錯誤">
            <Alert message={analysis.error_message} type="error" showIcon className="ai-qa-alert" />
          </Descriptions.Item>
        )}

        {/* AI 分析輸出內容 */}
        {aiOutput && (
          <>
            {aiOutput.initial_summary && (
              <Descriptions.Item label="AI 初步摘要">{aiOutput.initial_summary}</Descriptions.Item>
            )}
            {aiOutput.content_type && (
              <Descriptions.Item label="內容類型">{aiOutput.content_type}</Descriptions.Item>
            )}

            {/* 關鍵資訊 */}
            {aiOutput.key_information && Object.entries(aiOutput.key_information).map(([key, value]) => {
              if (!value || (Array.isArray(value) && value.length === 0) || (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0)) {
                return null;
              }

              let displayValue: React.ReactNode;
              if (Array.isArray(value)) {
                displayValue = value.join(', ');
              } else if (typeof value === 'object' && value !== null) {
                displayValue = <pre className="whitespace-pre-wrap text-xs bg-surface-100 p-2 rounded">{JSON.stringify(value, null, 2)}</pre>;
              } else {
                displayValue = String(value);
              }

              const label = key.replace(/_/g, ' ').replace(/\b(\w)/g, c => c.toUpperCase());
              return (
                <Descriptions.Item label={label} key={key}>
                  {displayValue}
                </Descriptions.Item>
              );
            })}

            {/* 中間分析步驟 */}
            {Array.isArray(aiOutput.intermediate_analysis) && aiOutput.intermediate_analysis.length > 0 && (
              <Descriptions.Item label="中間分析步驟">
                <Collapse accordion size="small">
                  {(aiOutput.intermediate_analysis as AITextAnalysisIntermediateStep[]).map((step, index) => (
                    <Collapse.Panel header={`步驟 ${index + 1}: ${step.potential_field}`} key={index}>
                      <div className="space-y-2">
                        <div>
                          <strong>文本片段:</strong>
                          <div className="mt-1 p-2 bg-surface-100 rounded text-sm">
                            {step.text_fragment || '無'}
                          </div>
                        </div>
                        <div>
                          <strong>分析原因:</strong>
                          <div className="mt-1 p-2 bg-surface-100 rounded text-sm">
                            {step.reasoning}
                          </div>
                        </div>
                      </div>
                    </Collapse.Panel>
                  ))}
                </Collapse>
              </Descriptions.Item>
            )}

            {aiOutput.error_message && (
              <Descriptions.Item label="AI 服務內部錯誤">
                <Alert message={aiOutput.error_message} type="warning" showIcon className="ai-qa-alert" />
              </Descriptions.Item>
            )}
          </>
        )}
      </Descriptions>
    </div>
  );
};

const DocumentDetailsModal: React.FC<DocumentDetailsModalProps> = ({ document, isOpen, onClose }) => {
  if (!isOpen || !document) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div onClick={(e: React.MouseEvent) => e.stopPropagation()} className="max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <Card title={`文件詳情: ${document.filename}`} className="shadow-xl">
          <div className="p-6 space-y-6">
            {/* 基本資訊 */}
            <section>
              <h3 className="text-lg font-semibold mb-3 text-gray-800 border-b pb-2">基本資訊</h3>
              <DocumentBasicInfo document={document} />
            </section>

            {/* 提取文本 */}
            {document.extracted_text && (
              <section>
                <h3 className="text-lg font-semibold mb-3 text-gray-800 border-b pb-2">提取內容</h3>
                <ExtractedTextSection extractedText={document.extracted_text} />
              </section>
            )}

            {/* AI 分析結果 */}
            {document.analysis && (
              <section>
                <h3 className="text-lg font-semibold mb-3 text-gray-800 border-b pb-2">分析結果</h3>
                <DocumentAnalysisInfo analysis={document.analysis} />
              </section>
            )}

            {/* 元數據 */}
            {document.metadata && Object.keys(document.metadata).length > 0 && (
              <section>
                <h3 className="text-lg font-semibold mb-3 text-gray-800 border-b pb-2">元數據</h3>
                <div className="bg-surface-100 p-3 rounded">
                  <pre className="text-xs whitespace-pre-wrap">
                    {JSON.stringify(document.metadata, null, 2)}
                  </pre>
                </div>
              </section>
            )}
          </div>

          <div className="p-6 border-t bg-surface-100 flex justify-end">
            <Button onClick={onClose} variant="primary">
              關閉
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DocumentDetailsModal; 