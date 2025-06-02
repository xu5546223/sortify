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
  Typography
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
} from '../services/vectorDBService';
import {
  getDocuments,
  getDocumentById,
} from '../services/documentService';
import ModelConfigCard from '../components/settings/ModelConfigCard';
import SemanticSearchInterface from '../components/SemanticSearchInterface';

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
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  
  // 模態框狀態 (除了搜索模態框)
  const [showVectorizeModal, setShowVectorizeModal] = useState(false);
  const [isDeletingFromVectorDB, setIsDeletingFromVectorDB] = useState<string | null>(null);

  // 加載數據的函數
  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [stats, connStatus, docsResponse] = await Promise.allSettled([
        getVectorDatabaseStats(),
        getDatabaseConnectionStatus(),
        getDocuments('', 'all', undefined, 'created_at', 'desc', 0, 50)
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
  }, [showPCMessage]);

  // 刷新數據
  const refreshData = useCallback(async () => {
    setIsRefreshing(true);
    await loadData();
    setIsRefreshing(false);
    showPCMessage('數據已刷新', 'success');
  }, [loadData, showPCMessage]);

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
  const handleDeleteFromVectorDB = async (docId: string) => {
    Modal.confirm({
      title: '確認刪除',
      content: '您確定要從向量數據庫中刪除此文檔的向量嗎？這不會刪除原始文檔。',
      okText: '確認刪除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          setIsDeletingFromVectorDB(docId);
          await deleteDocumentFromVectorDB(docId);
          showPCMessage('已從向量數據庫刪除文檔向量', 'success');
          // 可選擇刷新數據，或者僅從UI移除（如果後端不返回更新列表）
          // 這裡我們刷新整個列表
          await refreshData(); 
        } catch (error) {
          console.error('從向量數據庫刪除失敗:', error);
          showPCMessage('從向量數據庫刪除失敗', 'error');
        } finally {
          setIsDeletingFromVectorDB(null);
        }
      },
    });
  };

  // 從向量數據庫批量刪除選中文檔的向量
  const handleBatchDeleteFromVectorDB = async () => {
    if (selectedDocIds.length === 0) {
      showPCMessage('請選擇要從向量數據庫刪除的文檔', 'info');
      return;
    }

    Modal.confirm({
      title: `確認批量刪除 ${selectedDocIds.length} 個文檔的向量`,
      content: '您確定要從向量數據庫中刪除所選文檔的向量嗎？這不會刪除原始文檔。',
      okText: '確認刪除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        setIsBatchDeleting(true);
        try {
          const response: BasicResponse = await deleteDocumentsFromVectorDB(selectedDocIds);
          if (response.success) {
            showPCMessage(`成功刪除 ${selectedDocIds.length} 個文檔的向量`, 'success');
          } else {
            showPCMessage(response.message || '批量刪除向量時發生錯誤', 'error');
          }
          setSelectedDocIds([]); // 清空選擇
          await refreshData(); // 刷新數據
        } catch (error) {
          console.error('批量刪除向量失敗:', error);
          showPCMessage('批量刪除向量操作失敗', 'error');
        } finally {
          setIsBatchDeleting(false);
        }
      },
    });
  };

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
          value={documents.length}
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
                    <Text strong>{documents.length}</Text>
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
          <Row gutter={16}>
            <Col xs={24} sm={12} lg={6}>
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
            <Col xs={24} sm={12} lg={6}>
              <Button
                onClick={() => setShowSearchModal(true)}
                icon={<SearchOutlined />}
                className="w-full"
              >
                開始語義搜索
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Button
                onClick={() => setShowVectorizeModal(true)}
                icon={<ThunderboltOutlined />}
                className="w-full"
              >
                管理文檔向量
              </Button>
            </Col>
            <Col xs={24} sm={12} lg={6}>
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

        {/* 語義搜索模態框 - 現在包裹 SemanticSearchInterface */}
        <Modal
          title="語義搜索"
          open={showSearchModal}
          onCancel={() => setShowSearchModal(false)}
          footer={null}
          width={800}
        >
          <SemanticSearchInterface 
            showPCMessage={showPCMessage} 
          />
        </Modal>

        {/* 文檔向量化模態框 - 修改標題 */}
        <Modal
          title="管理文檔向量"
          open={showVectorizeModal}
          onCancel={() => setShowVectorizeModal(false)}
          footer={[
            <Button key="cancel" onClick={() => setShowVectorizeModal(false)}>
              取消
            </Button>,
            <Button
              key="vectorizeSelected"
              loading={isProcessing}
              onClick={handleBatchVectorize}
              disabled={selectedDocIds.length === 0}
              icon={<ThunderboltOutlined />}
            >
              向量化選中項 ({selectedDocIds.length})
            </Button>,
            <Button
              key="batchDeleteSelected"
              danger
              loading={isBatchDeleting}
              onClick={handleBatchDeleteFromVectorDB}
              disabled={selectedDocIds.length === 0}
              icon={<CloseCircleOutlined />}
            >
              移除選中項向量 ({selectedDocIds.length})
            </Button>
          ]}
          width={900}
        >
          <div className="space-y-4">
            <Alert
              message="管理文檔向量"
              description="對文檔進行向量化、重新向量化或移除已生成的向量。向量化後的文檔可用於語義搜索。"
              type="info"
              showIcon
              className="ai-qa-alert"
            />

            <Table
              headers={[
                { key: 'selector', label: '選擇', className: 'w-12' },
                { key: 'filename', label: '文件名' },
                { key: 'vector_status', label: '向量狀態' },
                { key: 'actions', label: '操作', className: 'w-auto' }
              ]}
              isSelectAllChecked={selectedDocIds.length === documents.length && documents.length > 0}
              onSelectAllChange={(e) => {
                if (e.target.checked) {
                  setSelectedDocIds(documents.map(doc => doc.id));
                } else {
                  setSelectedDocIds([]);
                }
              }}
            >
              {documents.slice(0, 20).map((doc) => {
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

            {documents.length > 20 && (
              <Alert
                message={`顯示前 20 個文檔，總共 ${documents.length} 個文檔`}
                type="info"
                showIcon
                className="ai-qa-alert"
              />
            )}
          </div>
        </Modal>

      </Space>
    </div>
  );
};

export default VectorDatabasePage; 