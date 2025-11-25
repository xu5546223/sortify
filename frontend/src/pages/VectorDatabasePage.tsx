import React, { useState, useEffect, useCallback } from 'react';
import { 
  Card, 
  PageHeader, 
  Table,
  TableRow,
  TableCell
} from '../components';
import { 
  Alert, 
  Space, 
  Descriptions, 
  Tag, 
  Progress, 
  Modal,
  Tabs, 
  List,
  Statistic,
  Row,
  Col,
  Spin,
  Empty,
  message,
  Tooltip,
  Input,
  Button,
  Badge,
  Typography,
  Pagination,
} from 'antd';
import {
  DatabaseOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  RocketOutlined,
  FileTextOutlined,
  BarChartOutlined,
  MonitorOutlined,
  ReloadOutlined,
  DesktopOutlined,
  EyeOutlined
} from '@ant-design/icons';
import type {
  VectorDatabaseStats,
  DatabaseConnectionStatus,
  BatchProcessDocumentsRequest,
  Document,
  BasicResponse
} from '../types/apiTypes';
import {
  getVectorDatabaseStats,
  getDatabaseConnectionStatus,
  batchProcessDocuments,
  initializeVectorDatabase,
  processDocumentToVector,
  deleteDocumentFromVectorDB,
  deleteDocumentsFromVectorDB,
  reindexAllDocuments,
} from '../services/vectorDBService';
import {
  getDocuments,
  getDocumentById,
} from '../services/documentService';
import ModelConfigCard from '../components/settings/ModelConfigCard';
import SemanticSearchInterface from '../components/SemanticSearchInterface';
import ConfirmDialog from '../components/ConfirmDialog';

const { Title, Paragraph, Text } = Typography;
const { TabPane } = Tabs;

interface VectorDatabasePageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const VectorDatabasePage: React.FC<VectorDatabasePageProps> = ({ showPCMessage }) => {
  // 狀態管理
  const [vectorStats, setVectorStats] = useState<VectorDatabaseStats | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<DatabaseConnectionStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // 語義搜索相關狀態 - 部分移至 SemanticSearchInterface，此處保留控制 Modal 的狀態
  const [showSearchModal, setShowSearchModal] = useState(false);
  
  // 文檔向量化相關狀態
  const [documents, setDocuments] = useState<Document[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [allDocumentIds, setAllDocumentIds] = useState<string[]>([]);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });
  
  // 模態框狀態 (除了搜索模態框)
  const [showVectorizeModal, setShowVectorizeModal] = useState(false);
  const [isDeletingFromVectorDB, setIsDeletingFromVectorDB] = useState<string | null>(null);
  
  // 確認對話框狀態
  const [deleteSingleConfirmDialog, setDeleteSingleConfirmDialog] = useState<{
    isOpen: boolean;
    docId: string | null;
  }>({ isOpen: false, docId: null });
  
  const [deleteBatchConfirmDialog, setDeleteBatchConfirmDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // 重新索引相關狀態
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexConfirmDialog, setReindexConfirmDialog] = useState(false);

  // 加載數據的函數
  const loadData = useCallback(async (page = pagination.current, pageSize = pagination.pageSize) => {
    try {
      setIsLoading(true);
      const [stats, connStatus, docsResponse] = await Promise.allSettled([
        getVectorDatabaseStats(),
        getDatabaseConnectionStatus(),
        getDocuments('', 'all', undefined, 'created_at', 'desc', (page - 1) * pageSize, pageSize)
      ]);

      if (stats.status === 'fulfilled') {
        setVectorStats(stats.value);
      } else {
        console.error('獲取向量數據庫統計失敗:', stats.reason);
        setVectorStats(null);
        showPCMessage('獲取向量數據庫統計失敗', 'error');
      }

      if (connStatus.status === 'fulfilled') {
        setConnectionStatus(connStatus.value);
      } else {
        console.error('獲取數據庫連接狀態失敗:', connStatus.reason);
        showPCMessage('獲取數據庫連接狀態失敗', 'error');
      }

      if (docsResponse.status === 'fulfilled') {
        setDocuments(docsResponse.value.documents);
        setTotalDocuments(docsResponse.value.totalCount);
      } else {
        console.error('獲取文檔列表失敗:', docsResponse.reason);
        showPCMessage('獲取文檔列表失敗', 'error');
      }

    } catch (error) {
      console.error('加載向量數據庫頁面數據失敗:', error);
      showPCMessage('載入數據失敗', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [showPCMessage, pagination]);

  // 刷新數據
  const refreshData = useCallback(async () => {
    setIsRefreshing(true);
    await loadData(1, pagination.pageSize);
    setIsRefreshing(false);
    showPCMessage('數據已刷新', 'success');
  }, [loadData, showPCMessage, pagination.pageSize]);

  // 初始化向量數據庫
  const handleInitializeVectorDB = async () => {
    try {
      setIsInitializing(true);
      await initializeVectorDatabase();
      showPCMessage('向量數據庫初始化成功', 'success');
      await refreshData();
    } catch (error) {
      console.error('初始化向量數據庫失敗:', error);
      showPCMessage('初始化向量數據庫失敗', 'error');
    } finally {
      setIsInitializing(false);
    }
  };

  // 語義搜索 - Modal 的開關由本地控制，具體搜索邏輯在 SemanticSearchInterface 中

  // 批量向量化文檔
  const handleBatchVectorize = async () => {
    if (selectedDocIds.length === 0) {
      showPCMessage('請選擇要向量化的文檔', 'error');
      return;
    }

    try {
      setIsProcessing(true);
      await batchProcessDocuments(selectedDocIds);
      showPCMessage(`已開始向量化 ${selectedDocIds.length} 個文檔`, 'success');
      setSelectedDocIds([]);
      setShowVectorizeModal(false);
      
      setTimeout(() => {
        refreshData();
      }, 2000);
    } catch (error) {
      console.error('批量向量化失敗:', error);
      showPCMessage('批量向量化失敗', 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  // 單個文檔向量化
  const handleSingleVectorize = async (docId: string) => {
    try {
      await processDocumentToVector(docId);
      showPCMessage('文檔向量化已開始', 'success');
      setTimeout(() => {
        refreshData();
      }, 2000);
    } catch (error) {
      console.error('文檔向量化失敗:', error);
      showPCMessage('文檔向量化失敗', 'error');
    }
  };

  // 從向量數據庫刪除單個文檔
  const handleDeleteFromVectorDB = (docId: string) => {
    setDeleteSingleConfirmDialog({ isOpen: true, docId });
  };
  
  const confirmDeleteSingleFromVectorDB = async () => {
    if (!deleteSingleConfirmDialog.docId) return;
    
    setIsDeleting(true);
    try {
      setIsDeletingFromVectorDB(deleteSingleConfirmDialog.docId);
      await deleteDocumentFromVectorDB(deleteSingleConfirmDialog.docId);
      showPCMessage('已從向量數據庫刪除文檔向量', 'success');
      await refreshData(); 
    } catch (error) {
      console.error('從向量數據庫刪除失敗:', error);
      showPCMessage('從向量數據庫刪除失敗', 'error');
    } finally {
      setIsDeleting(false);
      setIsDeletingFromVectorDB(null);
      setDeleteSingleConfirmDialog({ isOpen: false, docId: null });
    }
  };

  // 從向量數據庫批量刪除選中文檔的向量
  const handleBatchDeleteFromVectorDB = () => {
    if (selectedDocIds.length === 0) {
      showPCMessage('請選擇要從向量數據庫刪除的文檔', 'info');
      return;
    }
    setDeleteBatchConfirmDialog(true);
  };
  
  const confirmBatchDeleteFromVectorDB = async () => {
    setIsBatchDeleting(true);
    setIsDeleting(true);
    try {
      const response: BasicResponse = await deleteDocumentsFromVectorDB(selectedDocIds);
      if (response.success) {
        showPCMessage(`成功刪除 ${selectedDocIds.length} 個文檔的向量`, 'success');
      } else {
        showPCMessage(response.message || '批量刪除向量時發生錯誤', 'error');
      }
      setSelectedDocIds([]);
      await refreshData();
    } catch (error) {
      console.error('批量刪除向量失敗:', error);
      showPCMessage('批量刪除向量操作失敗', 'error');
    } finally {
      setIsBatchDeleting(false);
      setIsDeleting(false);
      setDeleteBatchConfirmDialog(false);
    }
  };

  // 重新索引所有文檔
  const handleReindexAll = () => {
    setReindexConfirmDialog(true);
  };

  const confirmReindexAll = async () => {
    setIsReindexing(true);
    try {
      const response = await reindexAllDocuments();
      if (response.success) {
        showPCMessage(response.message || '已開始重新索引所有文檔', 'success');
        // 延遲刷新以等待後台任務開始
        setTimeout(() => {
          refreshData();
        }, 2000);
      } else {
        showPCMessage(response.message || '重新索引失敗', 'error');
      }
    } catch (error) {
      console.error('重新索引失敗:', error);
      showPCMessage('重新索引操作失敗', 'error');
    } finally {
      setIsReindexing(false);
      setReindexConfirmDialog(false);
    }
  };

  const handleTableChange = (newPagination: any) => {
    setPagination({
      current: newPagination.current ?? 1,
      pageSize: newPagination.pageSize ?? 10,
    });
    loadData(newPagination.current, newPagination.pageSize);
  };

  // 獲取所有文檔ID（用於全選功能）
  const fetchAllDocumentIds = useCallback(async () => {
    try {
      const allIds: string[] = [];
      const batchSize = 100; // 後端 API 限制最大 100
      let currentSkip = 0;
      let hasMore = true;

      while (hasMore) {
        const response = await getDocuments('', 'all', undefined, 'created_at', 'desc', currentSkip, batchSize);
        
        if (response.documents.length === 0) {
          hasMore = false;
        } else {
          allIds.push(...response.documents.map(doc => doc.id));
          currentSkip += batchSize;
          
          // 如果這批數量少於 batchSize，說明已經是最後一批
          if (response.documents.length < batchSize) {
            hasMore = false;
          }
        }
      }

      setAllDocumentIds(allIds);
      console.log(`成功獲取 ${allIds.length} 個文檔ID`);
    } catch (error) {
      console.error('獲取所有文檔ID失敗:', error);
      showPCMessage('獲取所有文檔ID失敗', 'error');
    }
  }, [showPCMessage]);

  // 選中當前頁面所有文檔
  const selectCurrentPage = () => {
    const currentPageIds = documents.map(doc => doc.id);
    const combinedIds = [...selectedDocIds, ...currentPageIds];
    const newSelected = Array.from(new Set(combinedIds));
    setSelectedDocIds(newSelected);
  };

  // 取消選中當前頁面所有文檔
  const deselectCurrentPage = () => {
    const currentPageIds = documents.map(doc => doc.id);
    setSelectedDocIds(selectedDocIds.filter(id => !currentPageIds.includes(id)));
  };

  // 選中所有文檔
  const selectAllDocuments = async () => {
    if (allDocumentIds.length === 0) {
      await fetchAllDocumentIds();
    }
    if (allDocumentIds.length > 0) {
      setSelectedDocIds(allDocumentIds);
    } else {
      showPCMessage('無法獲取所有文檔ID', 'error');
    }
  };

  // 取消選中所有文檔
  const deselectAllDocuments = () => {
    setSelectedDocIds([]);
  };

  // 檢查當前頁面是否全選
  const isCurrentPageSelected = documents.length > 0 && documents.every(doc => selectedDocIds.includes(doc.id));

  // 組件掛載時加載數據
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 渲染數據庫狀態卡片
  const renderDatabaseStatus = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={8}>
        <Card className="h-full" title={<h3 className="text-lg font-semibold flex items-center"><DatabaseOutlined className="mr-2 text-blue-500" /> MongoDB 狀態</h3>} headerActions={connectionStatus?.mongodb.connected ? <CheckCircleOutlined className="text-green-500 text-xl" /> : <CloseCircleOutlined className="text-red-500 text-xl" />}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="連接狀態">
              <Tag color={connectionStatus?.mongodb.connected ? 'green' : 'red'}>
                {connectionStatus?.mongodb.connected ? '已連接' : '斷開連接'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="數據庫">
              {connectionStatus?.mongodb.database_name || 'N/A'}
            </Descriptions.Item>
            <Descriptions.Item label="最後檢查">
              {connectionStatus?.mongodb.last_ping ? 
                new Date(connectionStatus.mongodb.last_ping).toLocaleString('zh-TW') : 
                'N/A'
              }
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>

      <Col xs={24} sm={12} lg={8}>
        <Card className="h-full" title={<h3 className="text-lg font-semibold flex items-center"><ThunderboltOutlined className="mr-2 text-purple-500" /> 向量數據庫狀態</h3>} headerActions={vectorStats?.status === 'ready' ? <CheckCircleOutlined className="text-green-500 text-xl" /> : <ExclamationCircleOutlined className="text-orange-500 text-xl" />}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="狀態">
              <Tag color={vectorStats?.status === 'ready' ? 'green' : 'orange'}>
                {vectorStats?.status === 'ready' ? '就緒' : '未就緒'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="集合">
              {vectorStats?.collection_name || 'N/A'}
            </Descriptions.Item>
            <Descriptions.Item label="向量總數">
              {vectorStats?.total_vectors || 0}
            </Descriptions.Item>
            <Descriptions.Item label="向量維度">
              {vectorStats?.vector_dimension || 'N/A'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>

      <Col xs={24} sm={24} lg={8}>
        <Card className="h-full" title={<h3 className="text-lg font-semibold flex items-center"><RocketOutlined className="mr-2 text-green-500" /> Embedding 模型</h3>} headerActions={vectorStats?.embedding_model.model_loaded ? <CheckCircleOutlined className="text-green-500 text-xl" /> : <CloseCircleOutlined className="text-red-500 text-xl" />}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="模型名稱">
              <Tooltip title={vectorStats?.embedding_model.model_name}>
                <span className="text-sm">{vectorStats?.embedding_model.model_name?.slice(-20) || 'N/A'}</span>
              </Tooltip>
            </Descriptions.Item>
            <Descriptions.Item label="設備">
              <Tag color={vectorStats?.embedding_model.device === 'cuda' ? 'green' : 'blue'}>
                {vectorStats?.embedding_model.device?.toUpperCase() || 'N/A'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="模型狀態">
              <Tag color={vectorStats?.embedding_model.model_loaded ? 'green' : 'red'}>
                {vectorStats?.embedding_model.model_loaded ? '已加載' : '未加載'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="緩存狀態">
              <Tag color={vectorStats?.embedding_model.cache_available ? 'green' : 'orange'}>
                {vectorStats?.embedding_model.cache_available ? '可用' : '不可用'}
              </Tag>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>
    </Row>
  );

  // 渲染統計信息
  const renderStatistics = () => (
    <Row gutter={[16, 16]} className="mb-6">
      <Col xs={12} sm={6}>
        <Statistic
          title="向量總數"
          value={vectorStats?.total_vectors || 0}
          prefix={<DatabaseOutlined />}
        />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic
          title="向量維度"
          value={vectorStats?.vector_dimension || 0}
          prefix={<ThunderboltOutlined />}
        />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic
          title="文檔總數"
          value={totalDocuments}
          prefix={<FileTextOutlined />}
        />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic
          title="搜索調用"
          value={"N/A"} 
          prefix={<SearchOutlined />}
        />
      </Col>
    </Row>
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" tip="加載向量數據庫信息..." />
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={2}>
            <DatabaseOutlined /> 向量數據庫管理
          </Title>
          <Paragraph type="secondary">
            管理向量數據庫、監控系統狀態、處理文檔向量化和執行語義搜索
          </Paragraph>
        </div>

        <Row gutter={[16, 16]}>
          <Col span={24}>
            <ModelConfigCard onModelStateChange={refreshData} />
          </Col>
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card 
              title="數據庫統計"
              headerActions={
                <Button
                  icon={<ReloadOutlined />}
                  onClick={refreshData}
                  loading={isRefreshing}
                  size="small"
                >
                  刷新
                </Button>
              }
            >
              {vectorStats ? (
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="文檔總數">
                    <Text strong>{totalDocuments}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="向量總數">
                    <Text strong>{vectorStats.total_vectors || 0}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="集合名稱">
                    <Text code>{vectorStats.collection_name}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="向量維度">
                    <Text>{vectorStats.vector_dimension}</Text>
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Empty description="無統計數據" />
              )}
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card title="Embedding 模型狀態">
              {vectorStats?.embedding_model ? (
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="模型名稱">
                    <Text code>{vectorStats.embedding_model.model_name}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="加載狀態">
                    <Badge 
                      status={vectorStats.embedding_model.model_loaded ? "success" : "default"} 
                      text={vectorStats.embedding_model.model_loaded ? "已加載" : "未加載"} 
                    />
                  </Descriptions.Item>
                  <Descriptions.Item label="運算設備">
                    <Space>
                      {vectorStats.embedding_model.device === 'cuda' ? (
                        <ThunderboltOutlined style={{ color: '#52c41a' }} />
                      ) : (
                        <DesktopOutlined style={{ color: '#1890ff' }} />
                      )}
                      <Text>{vectorStats.embedding_model.device.toUpperCase()}</Text>
                    </Space>
                  </Descriptions.Item>
                  <Descriptions.Item label="向量維度">
                    <Text>{vectorStats.embedding_model.vector_dimension}</Text>
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Empty description="無模型信息" />
              )}
            </Card>
          </Col>
        </Row>

        <div className="flex justify-between items-center">
          <PageHeader title="向量數據庫管理" />
          <Space>
            <Button
              onClick={refreshData}
              loading={isRefreshing}
              icon={<SyncOutlined />}
            >
              刷新
            </Button>
            <Button
              onClick={() => setShowSearchModal(true)}
              icon={<SearchOutlined />}
            >
              語義搜索
            </Button>
          </Space>
        </div>

        {renderStatistics()}

        <Card title="數據庫連接狀態">
          {renderDatabaseStatus()}
        </Card>

        <Card title="快速操作">
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} lg={8}>
              <Button
                onClick={handleInitializeVectorDB}
                loading={isInitializing}
                icon={<DatabaseOutlined />}
                className="w-full"
                disabled={vectorStats?.status === 'ready'}
              >
                初始化向量數據庫
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Button
                onClick={() => setShowSearchModal(true)}
                icon={<SearchOutlined />}
                className="w-full"
              >
                開始語義搜索
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Button
                onClick={() => setShowVectorizeModal(true)}
                icon={<ThunderboltOutlined />}
                className="w-full"
              >
                管理文檔向量
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Button
                onClick={handleReindexAll}
                loading={isReindexing}
                icon={<ReloadOutlined />}
                className="w-full"
                type="default"
              >
                重新索引全部
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Button
                onClick={refreshData}
                icon={<SyncOutlined />}
                className="w-full"
              >
                刷新狀態
              </Button>
            </Col>
          </Row>
        </Card>

        {(connectionStatus?.mongodb.error || vectorStats?.error) && (
          <Alert
            message="數據庫連接問題"
            description={
              <div>
                {connectionStatus?.mongodb.error && (
                  <div>MongoDB: {connectionStatus.mongodb.error}</div>
                )}
                {vectorStats?.error && (
                  <div>向量數據庫: {vectorStats.error}</div>
                )}
              </div>
            }
            type="error"
            showIcon
            closable
            className="ai-qa-alert"
          />
        )}

        {/* 語義搜索彈出框 - 支持混合搜索 */}
        {showSearchModal && (
          <div
            className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50"
            onClick={() => setShowSearchModal(false)}
          >
            <div
              onClick={(e: React.MouseEvent) => e.stopPropagation()}
              className="w-full max-w-6xl max-h-[95vh] bg-white border-3 border-neo-black shadow-[8px_8px_0px_0px_black] flex flex-col"
            >
              {/* Header */}
              <div className="bg-neo-primary text-neo-white px-6 py-4 border-b-3 border-neo-black flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                  <SearchOutlined className="text-xl" />
                  <h2 className="font-display font-bold text-lg">智能語義搜索</h2>
                  <span className="px-3 py-1 text-xs font-black border-2 border-neo-black bg-neo-lime text-neo-black">
                    Two-Stage Hybrid Retrieval
                  </span>
                </div>
                <button
                  onClick={() => setShowSearchModal(false)}
                  className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-red-600 text-white border-2 border-neo-black shadow-neo-sm hover:bg-red-700 transition-colors font-bold text-xl"
                  aria-label="關閉"
                >
                  ✕
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-6 bg-neo-bg">
                <SemanticSearchInterface 
                  showPCMessage={showPCMessage}
                  cardTitle="智能文檔搜索"
                  extraActions={
                    <Button
                      size="small"
                      icon={<InfoCircleOutlined />}
                      type="text"
                      onClick={() => showPCMessage('支持摘要向量和文本塊的兩階段混合檢索，提供更精確的搜索結果', 'info')}
                    >
                      搜索說明
                    </Button>
                  }
                />
              </div>
            </div>
          </div>
        )}

        {/* 文檔向量化彈出框 */}
        {showVectorizeModal && (
          <div
            className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50"
            onClick={() => setShowVectorizeModal(false)}
          >
            <div
              onClick={(e: React.MouseEvent) => e.stopPropagation()}
              className="w-full max-w-6xl max-h-[95vh] bg-white border-3 border-neo-black shadow-[8px_8px_0px_0px_black] flex flex-col"
            >
              {/* Header */}
              <div className="bg-neo-primary text-neo-white px-6 py-4 border-b-3 border-neo-black flex items-center justify-between shrink-0">
                <h2 className="font-display font-bold text-lg">管理文檔向量</h2>
                <button
                  onClick={() => setShowVectorizeModal(false)}
                  className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-red-600 text-white border-2 border-neo-black shadow-neo-sm hover:bg-red-700 transition-colors font-bold text-xl"
                  aria-label="關閉"
                >
                  ✕
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-6 bg-neo-bg">
                <div className="space-y-4">
                  <Alert
                    message="管理文檔向量"
                    description="對文檔進行向量化、重新向量化或移除已生成的向量。向量化後的文檔可用於語義搜索。"
                    type="info"
                    showIcon
                    className="ai-qa-alert"
                  />

                  <div className="mb-4">
                    <Space>
                      <Button
                        size="small"
                        onClick={isCurrentPageSelected ? deselectCurrentPage : selectCurrentPage}
                        disabled={documents.length === 0}
                      >
                        {isCurrentPageSelected ? '取消選中當前頁面' : '選中當前頁面'}
                      </Button>
                      <Button
                        size="small"
                        onClick={selectedDocIds.length === totalDocuments ? deselectAllDocuments : selectAllDocuments}
                        disabled={totalDocuments === 0}
                      >
                        {selectedDocIds.length === totalDocuments ? '取消全選' : `全選 (${totalDocuments} 個文檔)`}
                      </Button>
                      <Text type="secondary">
                        已選中 {selectedDocIds.length} 個文檔
                      </Text>
                    </Space>
                  </div>

                  <Table
                    headers={[
                      { key: 'selector', label: '選擇', className: 'w-12' },
                      { key: 'filename', label: '文件名' },
                      { key: 'vector_status', label: '向量狀態' },
                      { key: 'actions', label: '操作', className: 'w-auto' }
                    ]}
                    isSelectAllChecked={isCurrentPageSelected}
                    onSelectAllChange={(e) => {
                      if (e.target.checked) {
                        selectCurrentPage();
                      } else {
                        deselectCurrentPage();
                      }
                    }}
                  >
                    {documents.map((doc) => {
                      const isCurrentDocDeleting = isDeletingFromVectorDB === doc.id;

                      return (
                        <TableRow key={doc.id}>
                          <TableCell>
                            <input
                              type="checkbox"
                              checked={selectedDocIds.includes(doc.id)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedDocIds(prev => [...prev, doc.id]);
                                } else {
                                  setSelectedDocIds(prev => prev.filter(id => id !== doc.id));
                                }
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <Tooltip title={doc.filename}>
                              <span className="truncate">{doc.filename}</span>
                            </Tooltip>
                            <div><Text type="secondary" style={{fontSize: '12px'}}>內容狀態: {doc.status}</Text></div>
                          </TableCell>
                          <TableCell>
                            {doc.vector_status === 'vectorized' && <Tag color="green">已向量化</Tag>}
                            {doc.vector_status === 'not_vectorized' && <Tag color="orange">未向量化</Tag>}
                            {doc.vector_status === 'processing' && <Tag color="blue">處理中...</Tag>}
                            {doc.vector_status === 'failed' && <Tag color="red">向量化失敗</Tag>}
                            {(!doc.vector_status) && <Tag>未知</Tag>}
                          </TableCell>
                          <TableCell>
                            <Space>
                              {(doc.vector_status === 'not_vectorized' || doc.vector_status === 'failed') && (
                                <Button
                                  size="small"
                                  onClick={() => handleSingleVectorize(doc.id)}
                                  icon={<ThunderboltOutlined />}
                                >
                                  {doc.vector_status === 'failed' ? '重試向量化' : '向量化'}
                                </Button>
                              )}
                              {doc.vector_status === 'vectorized' && (
                                <>
                                  <Button
                                    size="small"
                                    onClick={() => handleSingleVectorize(doc.id)}
                                    icon={<SyncOutlined />}
                                  >
                                    重新向量化
                                  </Button>
                                  <Button
                                    size="small"
                                    danger
                                    onClick={() => handleDeleteFromVectorDB(doc.id)}
                                    icon={<CloseCircleOutlined />}
                                    loading={isCurrentDocDeleting}
                                    disabled={isCurrentDocDeleting}
                                  >
                                    移除向量
                                  </Button>
                                </>
                              )}
                              {doc.vector_status === 'processing' && (
                                 <Spin size="small" />
                              )}
                            </Space>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </Table>

                  <div className="flex justify-between items-center mt-4">
                    <Text type="secondary">
                      顯示 {((pagination.current - 1) * pagination.pageSize) + 1}-{Math.min(pagination.current * pagination.pageSize, totalDocuments)} 項，共 {totalDocuments} 項
                    </Text>
                    <Pagination
                      current={pagination.current}
                      pageSize={pagination.pageSize}
                      total={totalDocuments}
                      showSizeChanger={true}
                      pageSizeOptions={['10', '20', '50', '100']}
                      onChange={(page, size) => {
                        const newPagination = {
                          current: page,
                          pageSize: size ?? pagination.pageSize,
                        };
                        setPagination(newPagination);
                        loadData(page, size ?? pagination.pageSize);
                      }}
                      showTotal={(total, range) => `${range[0]}-${range[1]} 共 ${total} 項`}
                    />
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="border-t-3 border-neo-black p-4 bg-white flex justify-end gap-3 shrink-0">
                <button
                  onClick={() => setShowVectorizeModal(false)}
                  className="px-6 py-2 bg-gray-100 text-gray-700 border-2 border-neo-black shadow-neo-sm hover:bg-gray-200 hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold"
                >
                  取消
                </button>
                <button
                  onClick={handleBatchVectorize}
                  disabled={selectedDocIds.length === 0 || isProcessing}
                  className="px-6 py-2 bg-neo-primary text-neo-white border-2 border-neo-black shadow-neo-sm hover:bg-neo-primaryDark hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isProcessing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                      處理中...
                    </>
                  ) : (
                    <>
                      <ThunderboltOutlined />
                      向量化選中項 ({selectedDocIds.length})
                    </>
                  )}
                </button>
                <button
                  onClick={handleBatchDeleteFromVectorDB}
                  disabled={selectedDocIds.length === 0 || isBatchDeleting}
                  className="px-6 py-2 bg-red-600 text-white border-2 border-neo-black shadow-neo-sm hover:bg-red-700 hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isBatchDeleting ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                      刪除中...
                    </>
                  ) : (
                    <>
                      <CloseCircleOutlined />
                      移除選中項向量 ({selectedDocIds.length})
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 確認刪除單個文檔對話框 */}
        <ConfirmDialog
          isOpen={deleteSingleConfirmDialog.isOpen}
          onClose={() => setDeleteSingleConfirmDialog({ isOpen: false, docId: null })}
          onConfirm={confirmDeleteSingleFromVectorDB}
          title="確認刪除"
          content="您確定要從向量數據庫中刪除此文檔的向量嗎？這不會刪除原始文檔。"
          confirmText="確認刪除"
          cancelText="取消"
          isDanger
          isLoading={isDeleting}
        />

        {/* 確認批量刪除對話框 */}
        <ConfirmDialog
          isOpen={deleteBatchConfirmDialog}
          onClose={() => setDeleteBatchConfirmDialog(false)}
          onConfirm={confirmBatchDeleteFromVectorDB}
          title={`確認批量刪除 ${selectedDocIds.length} 個文檔的向量`}
          content="您確定要從向量數據庫中刪除所選文檔的向量嗎？這不會刪除原始文檔。"
          confirmText="確認刪除"
          cancelText="取消"
          isDanger
          isLoading={isDeleting}
        />

        {/* 確認重新索引對話框 */}
        <ConfirmDialog
          isOpen={reindexConfirmDialog}
          onClose={() => setReindexConfirmDialog(false)}
          onConfirm={confirmReindexAll}
          title="重新索引所有文檔"
          content="此操作將重新向量化您的所有文檔。這可能需要較長時間，具體取決於文檔數量。確定要繼續嗎？"
          confirmText="開始重新索引"
          cancelText="取消"
          isLoading={isReindexing}
        />

      </Space>
    </div>
  );
};

export default VectorDatabasePage;