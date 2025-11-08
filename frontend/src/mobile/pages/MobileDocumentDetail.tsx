import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { message, Tag, Collapse, Spin } from 'antd';
import MobileHeader from '../components/MobileHeader';
import MobilePdfViewer from '../components/MobilePdfViewer';
import { apiClient } from '../../services/apiClient';
import { 
  FileTextOutlined,
  CalendarOutlined,
  TagsOutlined,
  InfoCircleOutlined,
  ZoomInOutlined,
  DownloadOutlined,
  CloseOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import DocumentTypeIcon from '../../components/document/DocumentTypeIcon';
import { formatBytes, formatDate, mapMimeTypeToSimpleType } from '../../utils/documentFormatters';

interface Document {
  id: string;
  filename: string;
  original_filename?: string | null;
  file_type?: string | null;
  size?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  status: string;
  extracted_text?: string | null;
  tags?: string[];
  metadata?: any;
  analysis?: {
    ai_analysis_output?: any;
    tokens_used?: number;
    analysis_started_at?: string;
    analysis_completed_at?: string;
    analysis_model_used?: string;
  };
  cluster_info?: {
    cluster_id: string;
    cluster_name: string;
    cluster_confidence: number;
  } | null;
}

const MobileDocumentDetail: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams<{ id: string }>();
  const [document, setDocument] = useState<Document | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageBlob, setImageBlob] = useState<string | null>(null); // 用于存储图片的 blob URL
  const [pdfPreview, setPdfPreview] = useState<string | null>(null);
  const [pdfBlob, setPdfBlob] = useState<string | null>(null); // 用于存储 PDF 的 blob URL
  const [isRetrying, setIsRetrying] = useState<boolean>(false); // 重试状态
  const [isLoadingPdf, setIsLoadingPdf] = useState<boolean>(false); // PDF 加載狀態
  
  // 從導航狀態中獲取返回信息
  const fromConversation = (location.state as any)?.fromConversation;
  const returnPath = (location.state as any)?.returnPath;

  useEffect(() => {
    if (id) {
      fetchDocumentDetail();
    }
  }, [id]);

  // 自动加载图片缩略图（如果是图片文件）
  useEffect(() => {
    if (document && isImageFile(document.file_type)) {
      loadImageThumbnail();
    }
  }, [document]);

  const loadImageThumbnail = async () => {
    if (!document) return;
    try {
      const response = await apiClient.get(`/documents/${document.id}/file`, {
        responseType: 'blob'
      });
      const blobUrl = URL.createObjectURL(response.data);
      setImageBlob(blobUrl);
      console.log('✅ 圖片縮略圖加載成功');
    } catch (error) {
      console.error('❌ 加載圖片縮略圖失敗:', error);
    }
  };

  // 處理返回邏輯
  const handleBack = () => {
    if (fromConversation && returnPath) {
      // 如果是從對話頁面來的，返回到對話頁面並恢復對話狀態
      console.log('🔙 返回到對話:', fromConversation);
      navigate(returnPath, { 
        state: { 
          conversationId: fromConversation 
        } 
      });
    } else {
      // 否則使用默認的返回行為
      navigate(-1);
    }
  };

  const fetchDocumentDetail = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/documents/${id}`);
      setDocument(response.data);
      console.log('✅ 文件詳情:', response.data);
    } catch (error: any) {
      console.error('❌ 獲取文件詳情失敗:', error);
      message.error('獲取文件詳情失敗');
      navigate('/mobile/documents');
    } finally {
      setLoading(false);
    }
  };

  const getStatusConfig = (status: string): { text: string; color: string } => {
    const statusMap: Record<string, { text: string; color: string }> = {
      'uploaded': { text: '已上傳', color: 'blue' },
      'analyzing': { text: '分析中', color: 'orange' },
      'analysis_completed': { text: '分析完成', color: 'green' },
      'completed': { text: '完成', color: 'green' },
      'processing_error': { text: '處理錯誤', color: 'red' },
      'analysis_failed': { text: '分析失敗', color: 'red' },
      'failed': { text: '失敗', color: 'red' }
    };
    return statusMap[status] || { text: status, color: 'default' };
  };

  // 判断是否需要显示重试按钮
  const shouldShowRetry = (): boolean => {
    if (!document) return false;
    const errorStatuses = ['processing_error', 'analysis_failed', 'failed'];
    return errorStatuses.includes(document.status);
  };

  // 重試分析
  const handleRetryAnalysis = async () => {
    if (!document) return;
    
    setIsRetrying(true);
    try {
      await apiClient.patch(`/documents/${document.id}`, {
        trigger_content_processing: true
      });
      
      message.success('重新分析已啟動！', 2);
      
      // 等待一下後重新獲取文檔狀態
      setTimeout(() => {
        fetchDocumentDetail();
      }, 1500);
    } catch (error: any) {
      console.error('❌ 重試分析失敗:', error);
      message.error(error.response?.data?.detail || '重試失敗，請稍後再試');
    } finally {
      setIsRetrying(false);
    }
  };

  const isImageFile = (fileType: string | null | undefined): boolean => {
    if (!fileType) return false;
    return fileType.startsWith('image/');
  };

  const isPdfFile = (fileType: string | null | undefined): boolean => {
    if (!fileType) return false;
    return fileType === 'application/pdf';
  };

  const handleImagePreview = async () => {
    if (!document) return;
    
    // 如果已经加载了图片，直接显示
    if (imageBlob) {
      setImagePreview(imageBlob);
      return;
    }
    
    try {
      // 通过 apiClient 获取图片，这样会自动添加 Authorization header
      const response = await apiClient.get(`/documents/${document.id}/file`, {
        responseType: 'blob' // 重要：指定响应类型为 blob
      });
      
      // 创建 blob URL
      const blobUrl = URL.createObjectURL(response.data);
      setImageBlob(blobUrl);
      setImagePreview(blobUrl);
      
      console.log('✅ 圖片預覽加載成功');
    } catch (error) {
      console.error('❌ 獲取圖片預覽失敗:', error);
      message.error('無法預覽圖片');
    }
  };

  // 清理 blob URL
  useEffect(() => {
    return () => {
      if (imageBlob) {
        URL.revokeObjectURL(imageBlob);
      }
      if (pdfBlob) {
        URL.revokeObjectURL(pdfBlob);
      }
    };
  }, [imageBlob, pdfBlob]);

  const handlePdfPreview = async () => {
    if (!document) return;
    
    console.log('📄 開始加載 PDF 預覽:', document.filename);
    
    // 如果已经加载了 PDF，直接显示
    if (pdfBlob) {
      console.log('✅ 使用已緩存的 PDF');
      setPdfPreview(pdfBlob);
      return;
    }
    
    setIsLoadingPdf(true);
    message.loading({ content: '正在加載 PDF...', key: 'pdf-loading', duration: 0 });
    
    try {
      console.log('🌐 發送請求獲取 PDF:', `/documents/${document.id}/file`);
      
      // 通过 apiClient 获取 PDF
      const response = await apiClient.get(`/documents/${document.id}/file`, {
        responseType: 'blob',
        timeout: 30000 // 30秒超時
      });
      
      console.log('📦 收到 PDF 響應:', {
        size: response.data.size,
        type: response.data.type
      });
      
      // 检查响应是否为 PDF
      if (!response.data.type.includes('pdf')) {
        console.warn('⚠️ 響應不是 PDF 類型:', response.data.type);
      }
      
      // 创建 blob URL
      const blobUrl = URL.createObjectURL(response.data);
      console.log('🔗 創建 Blob URL:', blobUrl);
      
      setPdfBlob(blobUrl);
      setPdfPreview(blobUrl);
      
      message.destroy('pdf-loading');
      message.success('PDF 加載成功');
      console.log('✅ PDF 預覽加載成功');
    } catch (error: any) {
      console.error('❌ 獲取 PDF 預覽失敗:', error);
      console.error('錯誤詳情:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      
      message.destroy('pdf-loading');
      
      let errorMsg = '無法預覽 PDF';
      if (error.response?.status === 401) {
        errorMsg = '未授權，請重新登錄';
      } else if (error.response?.status === 404) {
        errorMsg = '文件不存在';
      } else if (error.code === 'ECONNABORTED') {
        errorMsg = '加載超時，請重試';
      }
      
      message.error(errorMsg);
    } finally {
      setIsLoadingPdf(false);
    }
  };

  const handleDownload = async () => {
    if (!document) return;
    try {
      // 通过 apiClient 下载文件，自动添加 Authorization header
      const response = await apiClient.get(`/documents/${document.id}/file`, {
        responseType: 'blob'
      });
      
      // 创建下载链接
      const blobUrl = URL.createObjectURL(response.data);
      const link = window.document.createElement('a');
      link.href = blobUrl;
      link.download = document.original_filename || document.filename || 'download';
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      
      // 清理 blob URL
      setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
      
      message.success('下載成功');
      console.log('✅ 文件下載成功');
    } catch (error) {
      console.error('❌ 下載文件失敗:', error);
      message.error('下載失敗');
    }
  };

  if (loading) {
    return (
      <>
        <MobileHeader title="文件詳情" showBack onBack={handleBack} />
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '60vh' 
        }}>
          <Spin size="large" />
        </div>
      </>
    );
  }

  if (!document) {
    return (
      <>
        <MobileHeader title="文件詳情" showBack onBack={handleBack} />
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <p>找不到文件</p>
        </div>
      </>
    );
  }

  const statusConfig = getStatusConfig(document.status);
  const displayName = document.original_filename || document.filename || '未命名文件';

  return (
    <>
      <MobileHeader 
        title="文件詳情" 
        showBack 
        onBack={() => navigate(-1)} 
      />
      
      {/* 图片预览 Modal */}
      {imagePreview && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.95)',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center'
          }}
          onClick={() => setImagePreview(null)}
        >
          <div style={{ 
            position: 'absolute', 
            top: '16px', 
            right: '16px',
            color: 'white',
            fontSize: '24px',
            cursor: 'pointer',
            zIndex: 10000
          }}>
            <CloseOutlined onClick={() => setImagePreview(null)} />
          </div>
          <img 
            src={imagePreview}
            alt={displayName}
            style={{
              maxWidth: '90vw',
              maxHeight: '90vh',
              objectFit: 'contain'
            }}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      {/* PDF 預覽組件 */}
      {pdfPreview && (
        <MobilePdfViewer
          pdfUrl={pdfPreview}
          fileName={displayName}
          onClose={() => setPdfPreview(null)}
        />
      )}
      
      <div style={{ 
        padding: '16px',
        paddingBottom: 'max(80px, calc(80px + env(safe-area-inset-bottom)))',
        maxWidth: '100vw',
        overflowX: 'hidden'
      }}>
        {/* 文件预览卡片 */}
        <div style={{
          backgroundColor: '#fff',
          borderRadius: '12px',
          padding: '20px',
          marginBottom: '16px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          textAlign: 'center'
        }}>
          <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'center' }}>
            {isImageFile(document.file_type) && imageBlob ? (
              <img 
                src={imageBlob}
                alt={displayName}
                style={{
                  maxWidth: '200px',
                  maxHeight: '200px',
                  borderRadius: '8px',
                  objectFit: 'contain',
                  cursor: 'pointer'
                }}
                onClick={handleImagePreview}
              />
            ) : (
              <DocumentTypeIcon 
                fileType={document.file_type} 
                fileName={document.filename}
                className="w-20 h-20"
              />
            )}
          </div>
          
          <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px', wordBreak: 'break-word' }}>
            {displayName}
          </div>
          
          <div style={{ fontSize: '13px', color: '#999', marginBottom: '12px' }}>
            {mapMimeTypeToSimpleType(document.file_type)} · {formatBytes(document.size || 0)}
          </div>
          
          <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
          
          {/* 操作按钮 */}
          {/* 錯誤狀態提示 */}
          {shouldShowRetry() && (
            <div style={{
              marginTop: '16px',
              padding: '12px',
              backgroundColor: '#fff2e8',
              borderRadius: '8px',
              border: '1px solid #ffbb96',
              fontSize: '13px',
              color: '#d4380d'
            }}>
              <div style={{ marginBottom: '8px', fontWeight: '500' }}>
                ⚠️ 文件處理失敗
              </div>
              <div style={{ color: '#8c8c8c', marginBottom: '8px' }}>
                該文件在分析過程中遇到錯誤，您可以嘗試重新處理。
              </div>
            </div>
          )}

          <div style={{ 
            display: 'flex', 
            gap: '12px', 
            marginTop: '16px',
            justifyContent: 'center',
            flexWrap: 'wrap'
          }}>
            {/* 重試按鈕 - 僅在錯誤狀態顯示 */}
            {shouldShowRetry() && (
              <button
                onClick={handleRetryAnalysis}
                disabled={isRetrying}
                className="mobile-btn mobile-btn-warning"
                style={{ 
                  flex: 1, 
                  maxWidth: '150px', 
                  minWidth: '120px',
                  background: isRetrying ? '#d9d9d9' : 'linear-gradient(135deg, #fa8c16 0%, #fa541c 100%)',
                  border: 'none'
                }}
              >
                <ReloadOutlined spin={isRetrying} /> {isRetrying ? '處理中...' : '重試分析'}
              </button>
            )}
            
            {isImageFile(document.file_type) && (
              <button
                onClick={handleImagePreview}
                className="mobile-btn mobile-btn-secondary"
                style={{ flex: 1, maxWidth: '150px', minWidth: '120px' }}
              >
                <ZoomInOutlined /> 預覽
              </button>
            )}
            {isPdfFile(document.file_type) && (
              <button
                onClick={handlePdfPreview}
                disabled={isLoadingPdf}
                className="mobile-btn mobile-btn-secondary"
                style={{ 
                  flex: 1, 
                  maxWidth: '150px', 
                  minWidth: '120px',
                  opacity: isLoadingPdf ? 0.6 : 1,
                  cursor: isLoadingPdf ? 'not-allowed' : 'pointer'
                }}
              >
                {isLoadingPdf ? <ReloadOutlined spin /> : <FileTextOutlined />} 
                {isLoadingPdf ? '加載中...' : '預覽'}
              </button>
            )}
            <button
              onClick={handleDownload}
              className="mobile-btn mobile-btn-secondary"
              style={{ flex: 1, maxWidth: '150px', minWidth: '120px' }}
            >
              <DownloadOutlined /> 下載
            </button>
          </div>
        </div>

        {/* 基本信息 */}
        <div style={{
          backgroundColor: '#fff',
          borderRadius: '12px',
          padding: '16px',
          marginBottom: '16px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
        }}>
          <h3 style={{ 
            fontSize: '15px', 
            fontWeight: '600', 
            marginBottom: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <InfoCircleOutlined /> 基本信息
          </h3>
          
          <div style={{ fontSize: '14px' }}>
            <InfoRow label="文件 ID" value={document.id} />
            <InfoRow label="文件名稱" value={document.filename} />
            <InfoRow label="上傳時間" value={formatDate(document.created_at ?? undefined)} />
            <InfoRow label="最後修改" value={formatDate(document.updated_at ?? undefined)} />
            
            {document.cluster_info && (
              <InfoRow 
                label="智能分類" 
                value={
                  <Tag color="green">
                    {document.cluster_info.cluster_name} ({Math.round(document.cluster_info.cluster_confidence * 100)}%)
                  </Tag>
                }
              />
            )}
            
            {document.tags && document.tags.length > 0 && (
              <InfoRow 
                label="標籤" 
                value={
                  <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                    {document.tags.map(tag => (
                      <Tag key={tag} color="blue" style={{ margin: 0 }}>{tag}</Tag>
                    ))}
                  </div>
                }
              />
            )}
          </div>
        </div>

        {/* 提取文本 */}
        {document.extracted_text && (
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '16px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <h3 style={{ 
              fontSize: '15px', 
              fontWeight: '600', 
              marginBottom: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <FileTextOutlined /> 提取內容
            </h3>
            
            <div style={{
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: '8px',
              maxHeight: '200px',
              overflowY: 'auto',
              fontSize: '13px',
              lineHeight: '1.6',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}>
              {document.extracted_text}
            </div>
          </div>
        )}

        {/* AI 分析结果 */}
        {document.analysis && document.analysis.ai_analysis_output && (
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '16px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <h3 style={{ 
              fontSize: '15px', 
              fontWeight: '600', 
              marginBottom: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <TagsOutlined /> AI 分析結果
            </h3>
            
            <div style={{ fontSize: '14px' }}>
              {document.analysis.analysis_model_used && (
                <InfoRow label="分析模型" value={document.analysis.analysis_model_used} />
              )}
              {document.analysis.tokens_used && (
                <InfoRow label="Tokens 用量" value={document.analysis.tokens_used.toString()} />
              )}
              
              {document.analysis.ai_analysis_output.initial_summary && (
                <InfoRow label="AI 摘要" value={document.analysis.ai_analysis_output.initial_summary} />
              )}
              {document.analysis.ai_analysis_output.content_type && (
                <InfoRow label="內容類型" value={document.analysis.ai_analysis_output.content_type} />
              )}
              
              {/* 关键信息 */}
              {document.analysis.ai_analysis_output.key_information && (
                <div style={{ marginTop: '12px' }}>
                  <Collapse size="small" ghost>
                    <Collapse.Panel header="關鍵信息" key="1">
                      <div style={{ 
                        backgroundColor: '#f5f5f5', 
                        padding: '12px', 
                        borderRadius: '8px',
                        fontSize: '13px'
                      }}>
                        <pre style={{ 
                          margin: 0, 
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'inherit'
                        }}>
                          {JSON.stringify(document.analysis.ai_analysis_output.key_information, null, 2)}
                        </pre>
                      </div>
                    </Collapse.Panel>
                  </Collapse>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
};

// 辅助组件：信息行
const InfoRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => {
  return (
    <div style={{
      display: 'flex',
      padding: '8px 0',
      borderBottom: '1px solid #f0f0f0'
    }}>
      <div style={{ 
        width: '90px', 
        flexShrink: 0, 
        color: '#999', 
        fontSize: '13px' 
      }}>
        {label}
      </div>
      <div style={{ 
        flex: 1, 
        fontSize: '13px',
        wordBreak: 'break-word'
      }}>
        {value || '-'}
      </div>
    </div>
  );
};

export default MobileDocumentDetail;

