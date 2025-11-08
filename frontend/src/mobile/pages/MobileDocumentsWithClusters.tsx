import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message, Modal, Tag } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { getDocuments, deleteDocument } from '../../services/documentService';
import { getUserClusters } from '../../services/clusteringService';
import { apiClient } from '../../services/apiClient';
import { 
  FolderOutlined,
  FileTextOutlined, 
  SearchOutlined,
  DeleteOutlined,
  RightOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';
import DocumentTypeIcon from '../../components/document/DocumentTypeIcon';
import { formatBytes, formatCompactDate } from '../../utils/documentFormatters';

interface Document {
  id: string;
  filename: string;
  original_filename?: string | null;
  file_type?: string | null;
  size?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  status: string;
  clustering_status?: string;
  cluster_info?: {
    cluster_id: string;
    cluster_name: string;
    cluster_confidence: number;
  } | null;
}

interface ClusterSummary {
  cluster_id: string;
  cluster_name: string;
  document_count: number;
  keywords?: string[];
}

type ViewMode = 'clusters' | 'documents';

const MobileDocumentsWithClusters: React.FC = () => {
  const navigate = useNavigate();
  
  // 视图状态
  const [viewMode, setViewMode] = useState<ViewMode>('clusters');
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [selectedClusterName, setSelectedClusterName] = useState<string>('');
  
  // 分类数据
  const [clusters, setClusters] = useState<ClusterSummary[]>([]);
  const [unclusteredCount, setUnclusteredCount] = useState<number>(0);
  const [unclassifiableCount, setUnclassifiableCount] = useState<number>(0);
  const [loadingClusters, setLoadingClusters] = useState<boolean>(true);
  const [clusterPage, setClusterPage] = useState<number>(1);
  
  // 文档数据
  const [documents, setDocuments] = useState<Document[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalDocuments, setTotalDocuments] = useState<number>(0);
  const [loadingDocuments, setLoadingDocuments] = useState<boolean>(false);
  
  // 搜索
  const [searchTerm, setSearchTerm] = useState<string>('');
  
  const itemsPerPage = 20;
  const clustersPerPage = 10;
  const totalPages = Math.ceil(totalDocuments / itemsPerPage);
  const totalClusterPages = Math.ceil(clusters.length / clustersPerPage);

  // 加载分类列表
  useEffect(() => {
    if (viewMode === 'clusters') {
      fetchClusters();
    }
  }, [viewMode]);

  // 加载文档列表
  useEffect(() => {
    if (viewMode === 'documents') {
      fetchDocuments();
    }
  }, [viewMode, selectedClusterId, currentPage, searchTerm]);

  const fetchClusters = async () => {
    try {
      setLoadingClusters(true);
      
      // 获取所有分类
      const clustersData = await getUserClusters();
      setClusters(clustersData || []);
      
      // 获取未分类文档数量（clustering_status 为 null 或不存在）
      const pendingResult = await apiClient.get('/documents/', {
        params: { 
          limit: 1, 
          skip: 0,
          clustering_status: 'pending'
        }
      });
      const pendingCount = pendingResult.data.total || 0;
      setUnclusteredCount(pendingCount);
      console.log(`📄 未分類文件數量: ${pendingCount}`);
      
      // 获取无法分类文档数量
      const excludedResult = await apiClient.get('/documents/', {
        params: { 
          limit: 1, 
          skip: 0,
          clustering_status: 'excluded'
        }
      });
      const excludedCount = excludedResult.data.total || 0;
      setUnclassifiableCount(excludedCount);
      console.log(`⚠️ 無法分類文件數量: ${excludedCount}`);
      
      console.log(`✅ 加载分类成功: ${clustersData.length} 个分类, 未分類: ${pendingCount}, 無法分類: ${excludedCount}`);
    } catch (error: any) {
      console.error('❌ 获取分类失败:', error);
      message.error('获取分类失败');
    } finally {
      setLoadingClusters(false);
    }
  };

  const fetchDocuments = async () => {
    try {
      setLoadingDocuments(true);
      
      const skip = (currentPage - 1) * itemsPerPage;
      
      let params: any = {
        skip,
        limit: itemsPerPage,
        sort_by: 'created_at',
        sort_order: 'desc'
      };
      
      // 如果选择了特定分类
      if (selectedClusterId) {
        if (selectedClusterId === 'unclustered') {
          // 未分类：clustering_status = pending
          params.clustering_status = 'pending';
        } else if (selectedClusterId === 'unclassifiable') {
          // 无法分类：clustering_status = excluded
          params.clustering_status = 'excluded';
        } else {
          // 普通分类：使用 cluster_id
          params.cluster_id = selectedClusterId;
        }
      }
      
      // 搜索
      if (searchTerm) {
        params.filename_contains = searchTerm;
      }
      
      const result = await apiClient.get('/documents/', { params });
      
      setDocuments(result.data.items || []);
      setTotalDocuments(result.data.total || 0);
      
      console.log(`✅ 加载文档成功: ${result.data.items?.length} / ${result.data.total}`);
    } catch (error: any) {
      console.error('❌ 获取文档失败:', error);
      message.error('获取文档失败');
    } finally {
      setLoadingDocuments(false);
    }
  };

  const handleClusterClick = (clusterId: string, clusterName: string) => {
    setSelectedClusterId(clusterId);
    setSelectedClusterName(clusterName);
    setViewMode('documents');
    setCurrentPage(1);
    setSearchTerm('');
  };

  const handleBackToClusters = () => {
    setViewMode('clusters');
    setSelectedClusterId(null);
    setSelectedClusterName('');
    setDocuments([]);
    setSearchTerm('');
    setClusterPage(1);
  };

  const handleClusterPageChange = (page: number) => {
    setClusterPage(page);
    window.scrollTo(0, 0);
  };

  // 获取当前页的分类
  const getCurrentPageClusters = () => {
    const startIndex = (clusterPage - 1) * clustersPerPage;
    const endIndex = startIndex + clustersPerPage;
    return clusters.slice(startIndex, endIndex);
  };

  const handleDelete = async (docId: string, docName: string) => {
    Modal.confirm({
      title: '確認刪除',
      icon: <ExclamationCircleOutlined />,
      content: `確定要刪除文件「${docName}」嗎？`,
      okText: '確認刪除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result = await deleteDocument(docId);
          if (result.success) {
            message.success('刪除成功');
            fetchDocuments();
          } else {
            message.error(`刪除失敗: ${result.message || '未知錯誤'}`);
          }
        } catch (error) {
          console.error('刪除失敗:', error);
          message.error('刪除失敗');
        }
      }
    });
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo(0, 0);
  };

  const getStatusConfig = (status: string): { text: string; color: string } => {
    const statusMap: Record<string, { text: string; color: string }> = {
      'uploaded': { text: '已上傳', color: 'blue' },
      'analyzing': { text: '分析中', color: 'orange' },
      'analysis_completed': { text: '分析完成', color: 'green' },
      'completed': { text: '完成', color: 'green' },
      'processing_error': { text: '處理錯誤', color: 'red' },
      'analysis_failed': { text: '分析失敗', color: 'red' }
    };
    return statusMap[status] || { text: status, color: 'default' };
  };

  // 渲染文档卡片
  const renderDocumentCard = (doc: Document) => {
    const statusConfig = getStatusConfig(doc.status);
    const displayName = doc.original_filename || doc.filename || '未命名文件';

    return (
      <div
        key={doc.id}
        onClick={() => navigate(`/mobile/documents/${doc.id}`)}
        style={{
          backgroundColor: '#fff',
          borderRadius: '8px',
          padding: '12px',
          marginBottom: '8px',
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-start',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          border: '1px solid #e8e8e8',
          cursor: 'pointer'
        }}
      >
        <div style={{ flexShrink: 0, marginTop: '4px' }}>
          <DocumentTypeIcon 
            fileType={doc.file_type} 
            fileName={doc.filename}
            className="w-10 h-10"
          />
        </div>
        
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: '14px',
            fontWeight: '500',
            marginBottom: '4px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            {displayName}
          </div>
          
          <div style={{
            display: 'flex',
            gap: '8px',
            alignItems: 'center',
            fontSize: '12px',
            color: '#999',
            flexWrap: 'wrap'
          }}>
            <span>{formatBytes(doc.size || 0)}</span>
            <span>•</span>
            <span>{doc.created_at ? formatCompactDate(doc.created_at) : '未知'}</span>
          </div>
          
          <div style={{ marginTop: '6px' }}>
            <Tag color={statusConfig.color} style={{ fontSize: '11px' }}>
              {statusConfig.text}
            </Tag>
          </div>
        </div>
        
        <div
          onClick={(e) => {
            e.stopPropagation(); // 阻止事件冒泡到父元素
            handleDelete(doc.id, displayName);
          }}
          style={{
            padding: '8px',
            cursor: 'pointer',
            color: '#ff4d4f',
            fontSize: '16px'
          }}
        >
          <DeleteOutlined />
        </div>
      </div>
    );
  };

  // 渲染分类卡片
  const renderClusterCard = (cluster: ClusterSummary) => {
    return (
      <div
        key={cluster.cluster_id}
        onClick={() => handleClusterClick(cluster.cluster_id, cluster.cluster_name)}
        style={{
          backgroundColor: '#fff',
          borderRadius: '8px',
          padding: '16px',
          marginBottom: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          cursor: 'pointer',
          border: '1px solid #e8e8e8',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          transition: 'all 0.2s'
        }}
        onTouchStart={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f5f5f5';
        }}
        onTouchEnd={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = '#fff';
        }}
      >
        <div style={{ fontSize: '28px', color: '#29bf12' }}>
          <FolderOutlined />
        </div>
        
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '15px', fontWeight: '600', marginBottom: '4px' }}>
            {cluster.cluster_name}
          </div>
          <div style={{ fontSize: '13px', color: '#999' }}>
            {cluster.document_count} 個文件
          </div>
        </div>
        
        <div style={{ fontSize: '16px', color: '#999' }}>
          <RightOutlined />
        </div>
      </div>
    );
  };

  // 渲染特殊文件夹（未分类/无法分类）
  const renderSpecialFolder = (type: 'unclustered' | 'unclassifiable', count: number) => {
    if (count === 0) return null;
    
    const config = type === 'unclustered' 
      ? { icon: '📄', title: '未分類', color: '#999', desc: '尚未執行智能分類' }
      : { icon: '⚠️', title: '無法分類', color: '#ff9800', desc: '已執行分類但無法歸類' };
    
    return (
      <div
        onClick={() => handleClusterClick(type, config.title)}
        style={{
          backgroundColor: '#fff',
          borderRadius: '8px',
          padding: '16px',
          marginBottom: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          cursor: 'pointer',
          border: `1px solid ${config.color}20`,
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          transition: 'all 0.2s'
        }}
        onTouchStart={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f5f5f5';
        }}
        onTouchEnd={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = '#fff';
        }}
      >
        <div style={{ fontSize: '28px' }}>
          {config.icon}
        </div>
        
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '15px', fontWeight: '600', marginBottom: '4px', color: config.color }}>
            {config.title}
          </div>
          <div style={{ fontSize: '12px', color: '#999' }}>
            {count} 個文件 · {config.desc}
          </div>
        </div>
        
        <div style={{ fontSize: '16px', color: '#999' }}>
          <RightOutlined />
        </div>
      </div>
    );
  };

  // 渲染分页
  const renderPagination = () => {
    if (totalPages <= 1) return null;
    
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        gap: '12px',
        marginTop: '20px',
        padding: '16px 0'
      }}>
        <button
          onClick={() => handlePageChange(currentPage - 1)}
          disabled={currentPage === 1}
          className="mobile-btn mobile-btn-secondary"
          style={{ minWidth: '80px' }}
        >
          上一頁
        </button>
        
        <span style={{ fontSize: '14px', color: '#666' }}>
          {currentPage} / {totalPages}
        </span>
        
        <button
          onClick={() => handlePageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="mobile-btn mobile-btn-secondary"
          style={{ minWidth: '80px' }}
        >
          下一頁
        </button>
      </div>
    );
  };

  return (
    <>
      <MobileHeader 
        title={viewMode === 'clusters' ? '文件分類' : selectedClusterName}
        showBack={viewMode === 'documents'}
        onBack={handleBackToClusters}
      />
      
      <div style={{ 
        padding: '16px',
        paddingBottom: 'max(80px, calc(80px + env(safe-area-inset-bottom)))',
        maxWidth: '100vw',
        overflowX: 'hidden'
      }}>
        {/* 分类列表视图 */}
        {viewMode === 'clusters' && (
          <>
            {loadingClusters ? (
              <div className="mobile-loading">
                <div className="mobile-loading-spinner" />
              </div>
            ) : (
              <>
                <div style={{ 
                  marginBottom: '12px', 
                  padding: '12px', 
                  backgroundColor: '#f5f5f5', 
                  borderRadius: '8px',
                  fontSize: '14px',
                  color: '#666'
                }}>
                  📊 共 {clusters.length} 個智能分類
                  {totalClusterPages > 1 && ` · 第 ${clusterPage}/${totalClusterPages} 頁`}
                  {(unclusteredCount > 0 || unclassifiableCount > 0) && (
                    <div style={{ fontSize: '12px', marginTop: '4px', color: '#999' }}>
                      {unclassifiableCount > 0 && `⚠️ ${unclassifiableCount} 個無法分類`}
                      {unclassifiableCount > 0 && unclusteredCount > 0 && ' · '}
                      {unclusteredCount > 0 && `📄 ${unclusteredCount} 個未分類`}
                    </div>
                  )}
                </div>

                {/* 特殊文件夹 - 只在第一页显示 */}
                {clusterPage === 1 && (
                  <>
                    {renderSpecialFolder('unclassifiable', unclassifiableCount)}
                    {renderSpecialFolder('unclustered', unclusteredCount)}
                  </>
                )}

                {/* 智能分类列表 */}
                {clusters.length > 0 ? (
                  <>
                    {clusterPage === 1 && (
                      <h3 style={{ fontSize: '14px', color: '#666', marginBottom: '12px', marginTop: '16px', paddingLeft: '4px' }}>
                        📁 智能分類 ({clusters.length})
                      </h3>
                    )}
                    {getCurrentPageClusters().map(cluster => renderClusterCard(cluster))}
                    
                    {/* 分类分页 */}
                    {totalClusterPages > 1 && (
                      <div style={{
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        gap: '12px',
                        marginTop: '20px',
                        padding: '16px 0'
                      }}>
                        <button
                          onClick={() => handleClusterPageChange(clusterPage - 1)}
                          disabled={clusterPage === 1}
                          className="mobile-btn mobile-btn-secondary"
                          style={{ minWidth: '80px' }}
                        >
                          上一頁
                        </button>
                        
                        <span style={{ fontSize: '14px', color: '#666' }}>
                          {clusterPage} / {totalClusterPages}
                        </span>
                        
                        <button
                          onClick={() => handleClusterPageChange(clusterPage + 1)}
                          disabled={clusterPage === totalClusterPages}
                          className="mobile-btn mobile-btn-secondary"
                          style={{ minWidth: '80px' }}
                        >
                          下一頁
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="mobile-empty">
                    <div className="mobile-empty-icon">📁</div>
                    <div className="mobile-empty-text">尚無智能分類</div>
                    <div className="mobile-empty-subtext">上傳文件後執行智能分類</div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* 文档列表视图 */}
        {viewMode === 'documents' && (
          <>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ position: 'relative', marginBottom: '12px' }}>
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
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="mobile-input"
                  style={{ paddingLeft: '44px' }}
                />
              </div>

              <div style={{ 
                padding: '8px 12px', 
                backgroundColor: '#f5f5f5', 
                borderRadius: '8px',
                fontSize: '13px',
                color: '#666'
              }}>
                共 {totalDocuments} 個文件
                {totalPages > 1 && ` · 第 ${currentPage}/${totalPages} 頁`}
              </div>
            </div>

            {loadingDocuments ? (
              <div className="mobile-loading">
                <div className="mobile-loading-spinner" />
              </div>
            ) : documents.length > 0 ? (
              <>
                {documents.map(doc => renderDocumentCard(doc))}
                {renderPagination()}
              </>
            ) : (
              <div className="mobile-empty">
                <div className="mobile-empty-icon">📄</div>
                <div className="mobile-empty-text">
                  {searchTerm ? '找不到文件' : '此分類暫無文件'}
                </div>
                <div className="mobile-empty-subtext">
                  {searchTerm ? '嘗試其他關鍵字' : ''}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
};

export default MobileDocumentsWithClusters;
