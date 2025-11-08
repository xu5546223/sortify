import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message, Tag } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { apiClient } from '../../services/apiClient';
import { FileTextOutlined, SearchOutlined, FilterOutlined, SyncOutlined } from '@ant-design/icons';
import DocumentTypeIcon from '../../components/document/DocumentTypeIcon';
import { formatBytes, formatCompactDate, mapMimeTypeToSimpleType } from '../../utils/documentFormatters';

interface Document {
  id: string;
  filename: string;
  original_filename?: string | null;
  file_type?: string | null;
  size?: number | null;  // 改為 size 以匹配後端
  created_at?: string | null;  // 改為 created_at 以匹配後端
  updated_at?: string | null;
  status: string;  // 改為 status 以匹配後端
  cluster_labels?: string[];
  error_details?: string | null;
  extracted_text?: string | null;
}

const MobileDocuments: React.FC = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [pullStartY, setPullStartY] = useState<number>(0);
  const [pullDistance, setPullDistance] = useState<number>(0);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async (isRefresh: boolean = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      
      const response = await apiClient.get('/documents/', {
        params: { limit: 100, skip: 0 }
      });
      
      setDocuments(response.data.items || []);
      
      if (isRefresh) {
        message.success('刷新成功');
      }
    } catch (error: any) {
      console.error('❌ 獲取文件列表失敗:', error);
      
      if (error.response?.status === 401) {
        message.error('認證失敗，請重新配對裝置');
      } else if (error.response?.status === 403) {
        message.error('沒有權限訪問文件列表');
      } else {
        message.error('獲取文件列表失敗');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
      setPullDistance(0);
    }
  };

  // 下拉刷新處理
  const handleTouchStart = (e: React.TouchEvent) => {
    if (window.scrollY === 0 && !refreshing) {
      setPullStartY(e.touches[0].clientY);
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (pullStartY > 0 && window.scrollY === 0 && !refreshing) {
      const distance = e.touches[0].clientY - pullStartY;
      if (distance > 0) {
        setPullDistance(Math.min(distance, 80));
        if (distance > 10) {
          e.preventDefault();
        }
      }
    }
  };

  const handleTouchEnd = () => {
    if (pullDistance > 60 && !refreshing) {
      fetchDocuments(true);
    } else {
      setPullDistance(0);
    }
    setPullStartY(0);
  };

  // 獲取狀態標籤顏色和文本
  const getStatusConfig = (status: string): { text: string; color: string; icon?: React.ReactNode } => {
    const statusMap: Record<string, { text: string; color: string; icon?: React.ReactNode }> = {
      'uploaded': { text: '已上傳', color: 'blue' },
      'pending_extraction': { text: '等待提取', color: 'gold' },
      'text_extracted': { text: '已提取', color: 'geekblue' },
      'extraction_failed': { text: '提取失敗', color: 'volcano' },
      'pending_analysis': { text: '等待分析', color: 'orange' },
      'analyzing': { text: '分析中', color: 'purple', icon: <SyncOutlined spin /> },
      'analysis_completed': { text: '分析完成', color: 'green' },
      'analysis_failed': { text: '分析失敗', color: 'red' },
      'processing_error': { text: '處理錯誤', color: 'magenta' },
      'completed': { text: '已完成', color: 'cyan' }
    };
    
    return statusMap[status] || { text: status, color: 'default' };
  };

  const filteredDocuments = documents.filter(doc => {
    // 檢查 original_filename 是否存在
    if (!doc.original_filename) {
      // 如果沒有 original_filename，檢查 filename
      const filename = doc.filename || '';
      return filename.toLowerCase().includes(searchTerm.toLowerCase());
    }
    return doc.original_filename.toLowerCase().includes(searchTerm.toLowerCase());
  });

  return (
    <>
      <MobileHeader title="文件列表" />
      
      <div 
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{ 
          padding: '16px',
          paddingBottom: 'max(16px, env(safe-area-inset-bottom))',
          maxWidth: '100vw',
          overflowX: 'hidden',
          position: 'relative',
          transition: pullDistance > 0 ? 'none' : 'transform 0.3s',
          transform: `translateY(${Math.min(pullDistance, 80)}px)`
        }}
      >
        {/* 下拉刷新提示 */}
        {pullDistance > 0 && (
          <div style={{
            position: 'absolute',
            top: `-${Math.min(pullDistance + 20, 100)}px`,
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '8px',
            color: '#29bf12',
            fontSize: '14px',
            zIndex: 10
          }}>
            <SyncOutlined spin={refreshing || pullDistance > 60} style={{ fontSize: '24px' }} />
            <span>{refreshing ? '刷新中...' : pullDistance > 60 ? '釋放刷新' : '下拉刷新'}</span>
          </div>
        )}

        <div style={{ position: 'relative', marginBottom: '16px' }}>
          <SearchOutlined 
            style={{
              position: 'absolute',
              left: '16px',
              top: '50%',
              transform: 'translateY(-50%)',
              fontSize: '16px',
              color: '#999'
            }}
          />
          <input
            type="text"
            placeholder="搜尋文件..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="mobile-input"
            style={{ paddingLeft: '44px' }}
          />
        </div>

        {loading ? (
          <div className="mobile-loading">
            <div className="mobile-loading-spinner" />
          </div>
        ) : filteredDocuments.length > 0 ? (
          <div>
            {filteredDocuments.map((doc) => {
              const statusConfig = getStatusConfig(doc.status);
              
              return (
                <div 
                  key={doc.id} 
                  style={{
                    backgroundColor: '#fff',
                    borderRadius: '12px',
                    padding: '16px',
                    marginBottom: '12px',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                    display: 'flex',
                    gap: '12px',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    border: '1px solid #e8e8e8'
                  }}
                  onClick={() => {
                    // TODO: 導航到文件詳情頁面
                    message.info('文件詳情功能開發中');
                  }}
                >
                  {/* 文件圖標 */}
                  <div style={{ flexShrink: 0 }}>
                    <DocumentTypeIcon 
                      fileType={doc.file_type}
                      fileName={doc.filename}
                      className="w-12 h-12"
                    />
                  </div>

                  {/* 文件信息 */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {/* 文件名 */}
                    <div style={{
                      fontSize: '14px',
                      fontWeight: 600,
                      color: '#262626',
                      marginBottom: '6px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {doc.original_filename || doc.filename || '未命名文件'}
                    </div>

                    {/* 文件類型和大小 */}
                    <div style={{
                      fontSize: '12px',
                      color: '#8c8c8c',
                      marginBottom: '6px'
                    }}>
                      <span style={{ fontWeight: 500, color: '#595959' }}>
                        {mapMimeTypeToSimpleType(doc.file_type)}
                      </span>
                      <span style={{ margin: '0 4px' }}>•</span>
                      {formatBytes(doc.size ?? undefined)}
                    </div>

                    {/* 修改時間 */}
                    <div style={{
                      fontSize: '11px',
                      color: '#bfbfbf',
                      marginBottom: '8px'
                    }}>
                      {doc.updated_at ? formatCompactDate(doc.updated_at) : (doc.created_at ? formatCompactDate(doc.created_at) : '未知日期')}
                    </div>

                    {/* 狀態標籤 */}
                    <div style={{ marginBottom: '4px' }}>
                      <Tag 
                        icon={statusConfig.icon}
                        color={statusConfig.color}
                        style={{ 
                          fontSize: '11px',
                          padding: '2px 8px',
                          border: 'none',
                          borderRadius: '4px'
                        }}
                      >
                        {statusConfig.text}
                      </Tag>
                    </div>

                    {/* 聚類標籤 */}
                    {doc.cluster_labels && doc.cluster_labels.length > 0 && (
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '6px' }}>
                        {doc.cluster_labels.slice(0, 3).map((label, index) => (
                          <span 
                            key={index}
                            style={{
                              fontSize: '10px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#f0f0f0',
                              color: '#595959'
                            }}
                          >
                            {label}
                          </span>
                        ))}
                        {doc.cluster_labels.length > 3 && (
                          <span style={{
                            fontSize: '10px',
                            padding: '2px 6px',
                            color: '#8c8c8c'
                          }}>
                            +{doc.cluster_labels.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mobile-empty">
            <div className="mobile-empty-icon">📄</div>
            <div className="mobile-empty-text">
              {searchTerm ? '沒有找到符合的文件' : '尚無文件'}
            </div>
            <div className="mobile-empty-subtext">
              {searchTerm ? '嘗試使用其他關鍵字搜尋' : '開始上傳您的第一份文件'}
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default MobileDocuments;

