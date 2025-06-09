import React, { useState, useCallback } from 'react';
import {
  Input,
  List,
  Button,
  Spin,
  Empty,
  Tag,
  Tooltip,
  Typography,
  Card,
  Divider,
  Badge,
  Space,
  Select,
  Switch,
  Slider,
  Form,
  Collapse,
  Alert
} from 'antd';
import {
  SearchOutlined,
  EyeOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  SettingOutlined,
  InfoCircleOutlined,
  RocketOutlined
} from '@ant-design/icons';
import type { SemanticSearchResult, Document } from '../types/apiTypes';
import { performSemanticSearch, performHybridSearch } from '../services/vectorDBService';
import { getDocumentById } from '../services/documentService';
import SearchResultDetailModal from './SearchResultDetailModal';

const { Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

interface SemanticSearchInterfaceProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
  // 允許外部傳入初始搜索結果和歷史，以便在不同頁面中保持狀態或共享
  initialSearchResults?: SemanticSearchResult[];
  initialSearchHistory?: SearchHistoryItem[];
  // 允許外部控制是否顯示高級搜索按鈕或自定義額外操作
  extraActions?: React.ReactNode;
  cardTitle?: string;
}

interface SearchHistoryItem {
  query: string;
  timestamp: Date;
  resultsCount: number;
  searchType: string;
  similarity_threshold: number;
}

interface SearchConfig {
  searchType: 'hybrid' | 'summary_only' | 'chunks_only' | 'legacy' | 'rrf_fusion';
  enableHybridSearch: boolean;
  topK: number;
  similarityThreshold: number;
  enableDiversityOptimization: boolean;
  rrfSummaryWeight: number;
  rrfChunksWeight: number;
  rrfKConstant: number;
  queryExpansionFactor: number;
}

const SemanticSearchInterface: React.FC<SemanticSearchInterfaceProps> = ({
  showPCMessage,
  initialSearchResults = [],
  initialSearchHistory = [],
  extraActions,
  cardTitle = "文檔語義搜索",
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>(initialSearchResults);
  const [isSearching, setIsSearching] = useState(false);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>(initialSearchHistory);

  const [showDocDetailModal, setShowDocDetailModal] = useState(false);
  const [selectedDocumentForDetail, setSelectedDocumentForDetail] = useState<Document | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // 搜索配置狀態
  const [searchConfig, setSearchConfig] = useState<SearchConfig>({
    searchType: 'hybrid',
    enableHybridSearch: true,
    topK: 10,
    similarityThreshold: 0.4,
    enableDiversityOptimization: true,
    // RRF 融合檢索權重配置
    rrfSummaryWeight: 0.4,
    rrfChunksWeight: 0.6,
    rrfKConstant: 60,
    // 混合檢索配置
    queryExpansionFactor: 1.5,
  });

  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);

  const handleSemanticSearch = async (query?: string) => {
    const currentQuery = query || searchQuery;
    if (!currentQuery.trim()) {
      showPCMessage('請輸入搜索內容', 'error');
      return;
    }

    try {
      setIsSearching(true);
      
      // 添加調試信息
      console.log('🔍 開始搜索:', {
        query: currentQuery.trim(),
        config: {
          searchType: searchConfig.searchType,
          enableHybridSearch: searchConfig.enableHybridSearch,
          topK: searchConfig.topK,
          similarityThreshold: searchConfig.similarityThreshold,
          enableDiversityOptimization: searchConfig.enableDiversityOptimization
        }
      });
      
      let results: SemanticSearchResult[];
      
      if (searchConfig.enableHybridSearch) {
        // 使用混合搜索 - 支持完整的配置選項
        const searchOptions = {
          enableHybridSearch: true,
          enableDiversityOptimization: searchConfig.enableDiversityOptimization,
          searchType: searchConfig.searchType === 'legacy' ? 'hybrid' : searchConfig.searchType,
          queryExpansionFactor: searchConfig.queryExpansionFactor,
          rerankTopK: searchConfig.topK * 2,
          // RRF 權重配置（僅當使用 RRF 融合時）
          ...(searchConfig.searchType === 'rrf_fusion' && {
            rrfWeights: { 
              summary: searchConfig.rrfSummaryWeight, 
              chunks: searchConfig.rrfChunksWeight 
            },
            rrfKConstant: searchConfig.rrfKConstant
          })
        };

        console.log('🔧 搜索選項:', searchOptions);

        results = await performSemanticSearch(
          currentQuery.trim(),
          searchConfig.topK,
          searchConfig.similarityThreshold,
          undefined,
          searchOptions
        );
      } else {
        // 使用傳統搜索
        results = await performSemanticSearch(
          currentQuery.trim(), 
          searchConfig.topK, 
          searchConfig.similarityThreshold,
          undefined,
          {
            enableHybridSearch: false,
            enableDiversityOptimization: searchConfig.enableDiversityOptimization,
            searchType: 'legacy'
          }
        );
      }
      
      console.log('✅ 搜索結果:', {
        resultCount: results.length,
        results: results.slice(0, 3).map(r => ({
          document_id: r.document_id,
          similarity_score: r.similarity_score,
          vector_type: r.vector_type
        }))
      });
      
      setSearchResults(results);

      const historyItem: SearchHistoryItem = {
        query: currentQuery.trim(),
        timestamp: new Date(),
        resultsCount: results.length,
        searchType: searchConfig.enableHybridSearch ? searchConfig.searchType : 'legacy',
        similarity_threshold: searchConfig.similarityThreshold
      };
      
      if (!searchHistory.some(item => item.query === currentQuery.trim())) {
        setSearchHistory(prev => [historyItem, ...prev.slice(0, 9)]);
      }
      
      if (results.length === 0) {
        showPCMessage('沒有找到相關結果，嘗試降低相似度閾值或使用不同的搜索策略', 'info');
      } else {
        showPCMessage(`找到 ${results.length} 個相關結果 (${historyItem.searchType} 搜索)`, 'success');
      }
      
    } catch (error) {
      console.error('❌ 語義搜索失敗:', error);
      
      // 提供更詳細的錯誤信息
      let errorMessage = '語義搜索失敗';
      if (error instanceof Error) {
        if (error.message.includes('network') || error.message.includes('fetch')) {
          errorMessage = '網絡連接錯誤，請檢查後端服務是否運行正常';
        } else if (error.message.includes('embedding')) {
          errorMessage = 'Embedding模型未準備就緒，請稍後再試';
        } else {
          errorMessage = `搜索錯誤: ${error.message}`;
        }
      }
      
      showPCMessage(errorMessage, 'error');
    } finally {
      setIsSearching(false);
    }
  };

  const handleShowDocumentDetails = async (docId: string) => {
    try {
      setIsLoadingDetail(true);
      setSelectedDocumentForDetail(null);
      const docDetails = await getDocumentById(docId);
      setSelectedDocumentForDetail(docDetails);
      setShowDocDetailModal(true);
    } catch (error) {
      console.error('獲取文檔詳細信息失敗:', error);
      showPCMessage('無法加載文檔詳情', 'error');
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // 渲染搜索結果項目
  const renderSearchResultItem = (result: SemanticSearchResult, index: number) => {
    const isChunkResult = result.vector_type === 'chunk';
    const isSummaryResult = result.vector_type === 'summary';
    
          return (
        <List.Item
          key={`${result.document_id}-${result.chunk_index || index}`}
          className="semantic-search-result-item"
          actions={[
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleShowDocumentDetails(result.document_id)}
            loading={isLoadingDetail && selectedDocumentForDetail?.id === result.document_id && !selectedDocumentForDetail}
          >
            查看詳情
          </Button>
        ]}
      >
        <List.Item.Meta
          avatar={
            <Badge count={index + 1} showZero color="blue">
              <FileTextOutlined className="text-lg" />
            </Badge>
          }
          title={(
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <Tooltip title={`文檔ID: ${result.document_id}`}>
                  <Text strong ellipsis style={{ maxWidth: 300 }}>
                    {result.document_filename || `文檔 ${result.document_id.slice(0, 8)}...`}
                  </Text>
                </Tooltip>
                <div className="mt-1">
                  <Space size="small">
                    <Tag color={isSummaryResult ? 'blue' : isChunkResult ? 'green' : 'gray'}>
                      {isSummaryResult ? '摘要向量' : isChunkResult ? '文本塊' : '向量'}
                    </Tag>
                    {isChunkResult && result.chunk_index !== undefined && (
                      <Tag color="cyan">第{result.chunk_index + 1}塊</Tag>
                    )}
                    {result.search_stage && (
                      <Tag color="purple">
                        {result.search_stage === 'stage1' ? '階段1' : 
                         result.search_stage === 'stage2' ? '階段2' : '單階段'}
                      </Tag>
                    )}
                    {result.content_type && (
                      <Tag color="orange">{result.content_type}</Tag>
                    )}
                  </Space>
                </div>
              </div>
              <div className="text-right">
                <Tag color="blue">
                  相似度: {(result.similarity_score * 100).toFixed(1)}%
                </Tag>
                {result.ranking_score && result.ranking_score !== result.similarity_score && (
                  <Tag color="purple">
                    排序分: {(result.ranking_score * 100).toFixed(1)}%
                  </Tag>
                )}
              </div>
            </div>
          )}
          description={(
            <div className="space-y-2">
              {/* 主要內容 */}
              <Paragraph
                ellipsis={{ rows: isChunkResult ? 3 : 2, expandable: true, symbol: '展開' }}
                className="text-sm"
              >
                {isChunkResult && result.chunk_text ? result.chunk_text : result.summary_text}
              </Paragraph>
              
              {/* 關鍵詞標籤 */}
              {(result.key_terms || result.searchable_keywords || result.knowledge_domains) && (
                <div className="space-y-1">
                  {result.key_terms && result.key_terms.length > 0 && (
                    <div>
                      <Text type="secondary" style={{fontSize: '12px'}}>關鍵詞: </Text>
                                             {result.key_terms.slice(0, 3).map((term, idx) => (
                         <Tag key={idx} color="cyan">{term}</Tag>
                       ))}
                      {result.key_terms.length > 3 && (
                        <Text type="secondary" style={{fontSize: '11px'}}>
                          +{result.key_terms.length - 3}個
                        </Text>
                      )}
                    </div>
                  )}
                  
                  {result.knowledge_domains && result.knowledge_domains.length > 0 && (
                    <div>
                      <Text type="secondary" style={{fontSize: '12px'}}>領域: </Text>
                                             {result.knowledge_domains.slice(0, 2).map((domain, idx) => (
                         <Tag key={idx} color="purple">{domain}</Tag>
                       ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        />
      </List.Item>
    );
  };

  return (
    <div className="space-y-6">
      <Card 
        title={cardTitle} 
        extra={
          <Space>
            {extraActions}
            <Button
              icon={<SettingOutlined />}
              type="text"
              onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
            >
              搜索設定
            </Button>
          </Space>
        }
      >
        <div className="space-y-4">
          {/* 高級搜索設定 */}
          {showAdvancedSettings && (
            <Collapse ghost>
              <Panel 
                header="高級搜索設定" 
                key="advanced"
                extra={<SettingOutlined />}
              >
                <Form layout="vertical" size="small">
                  <div className="grid grid-cols-2 gap-4">
                    <Form.Item label="搜索策略">
                      <Select
                        value={searchConfig.searchType}
                        onChange={(value) => setSearchConfig(prev => ({ 
                          ...prev, 
                          searchType: value,
                          enableHybridSearch: value !== 'legacy'
                        }))}
                      >
                        <Option value="hybrid">
                          <Space>
                            <ThunderboltOutlined />
                            兩階段混合檢索
                          </Space>
                        </Option>
                        <Option value="rrf_fusion">
                          <Space>
                            <RocketOutlined />
                            🚀 RRF 融合檢索
                          </Space>
                        </Option>
                        <Option value="summary_only">摘要向量搜索</Option>
                        <Option value="chunks_only">文本塊搜索</Option>
                        <Option value="legacy">傳統搜索</Option>
                      </Select>
                    </Form.Item>
                    
                    <Form.Item label="結果數量">
                      <Slider
                        min={5}
                        max={20}
                        value={searchConfig.topK}
                        onChange={(value) => setSearchConfig(prev => ({ ...prev, topK: value }))}
                        marks={{ 5: '5', 10: '10', 15: '15', 20: '20' }}
                      />
                    </Form.Item>
                    
                    <Form.Item label="相似度閾值">
                      <Slider
                        min={0.1}
                        max={0.9}
                        step={0.1}
                        value={searchConfig.similarityThreshold}
                        onChange={(value) => setSearchConfig(prev => ({ ...prev, similarityThreshold: value }))}
                        marks={{ 0.1: '0.1', 0.4: '0.4', 0.7: '0.7', 0.9: '0.9' }}
                      />
                    </Form.Item>
                    
                    <Form.Item label="多樣性優化">
                      <Switch
                        checked={searchConfig.enableDiversityOptimization}
                        onChange={(checked) => setSearchConfig(prev => ({ ...prev, enableDiversityOptimization: checked }))}
                        checkedChildren="開啟"
                        unCheckedChildren="關閉"
                      />
                    </Form.Item>

                    <Form.Item label="查詢擴展因子">
                      <Slider
                        min={1.0}
                        max={3.0}
                        step={0.1}
                        value={searchConfig.queryExpansionFactor}
                        onChange={(value) => setSearchConfig(prev => ({ ...prev, queryExpansionFactor: value }))}
                        marks={{ 1.0: '1.0', 1.5: '1.5', 2.0: '2.0', 3.0: '3.0' }}
                      />
                    </Form.Item>
                  </div>

                  {/* RRF 融合檢索專用配置 */}
                  {searchConfig.searchType === 'rrf_fusion' && (
                    <div className="mt-4 p-4 border border-blue-200 rounded-lg bg-blue-50">
                      <div className="mb-3">
                        <Text strong className="text-blue-700">🚀 RRF 融合檢索權重配置</Text>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <Form.Item label={`摘要權重 (${searchConfig.rrfSummaryWeight.toFixed(1)})`}>
                          <Slider
                            min={0.1}
                            max={0.9}
                            step={0.1}
                            value={searchConfig.rrfSummaryWeight}
                            onChange={(value) => setSearchConfig(prev => ({ 
                              ...prev, 
                              rrfSummaryWeight: value,
                              rrfChunksWeight: Math.round((1 - value) * 10) / 10 // 自動調整另一個權重
                            }))}
                            marks={{ 0.1: '0.1', 0.4: '0.4', 0.6: '0.6', 0.9: '0.9' }}
                          />
                        </Form.Item>
                        
                        <Form.Item label={`內容塊權重 (${searchConfig.rrfChunksWeight.toFixed(1)})`}>
                          <Slider
                            min={0.1}
                            max={0.9}
                            step={0.1}
                            value={searchConfig.rrfChunksWeight}
                            onChange={(value) => setSearchConfig(prev => ({ 
                              ...prev, 
                              rrfChunksWeight: value,
                              rrfSummaryWeight: Math.round((1 - value) * 10) / 10 // 自動調整另一個權重
                            }))}
                            marks={{ 0.1: '0.1', 0.4: '0.4', 0.6: '0.6', 0.9: '0.9' }}
                          />
                        </Form.Item>
                        
                        <Form.Item label="RRF K 常數" className="col-span-2">
                          <Slider
                            min={10}
                            max={200}
                            step={10}
                            value={searchConfig.rrfKConstant}
                            onChange={(value) => setSearchConfig(prev => ({ ...prev, rrfKConstant: value }))}
                            marks={{ 10: '10', 60: '60', 100: '100', 200: '200' }}
                          />
                          <Text type="secondary" style={{fontSize: '12px'}}>
                            K 值越小，高排名文檔的優勢越明顯；K 值越大，排名分佈越平均
                          </Text>
                        </Form.Item>
                      </div>
                      
                      <Alert
                        message="權重配置說明"
                        description={`摘要權重: ${searchConfig.rrfSummaryWeight.toFixed(1)} | 內容塊權重: ${searchConfig.rrfChunksWeight.toFixed(1)} | 總和: ${(searchConfig.rrfSummaryWeight + searchConfig.rrfChunksWeight).toFixed(1)}`}
                        type="info"
                        showIcon
                        className="mt-3"
                      />
                    </div>
                  )}
                </Form>
                
                <Alert
                  message="搜索策略說明"
                  description={
                    <div>
                      <strong>🚀 RRF 融合檢索：</strong>終極搜索策略！並行執行摘要和內容塊搜索，使用倒數排名融合算法(RRF)智能合併結果<br/>
                      <strong>兩階段混合檢索：</strong>先用摘要向量快速篩選候選文檔，再用文本塊精確匹配<br/>
                      <strong>摘要向量搜索：</strong>僅搜索文檔摘要，適合快速瀏覽<br/>
                      <strong>文本塊搜索：</strong>僅搜索具體內容片段，適合精確查找<br/>
                      <strong>傳統搜索：</strong>單階段向量搜索，向後兼容
                    </div>
                  }
                  type="info"
                  showIcon
                  icon={<InfoCircleOutlined />}
                  className="mt-4"
                />
              </Panel>
            </Collapse>
          )}

          {/* 搜索輸入框 */}
          <Input.Search
            placeholder="在您的知識庫中搜索相關信息..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onSearch={() => handleSemanticSearch()}
            loading={isSearching}
            enterButton={
              <Button type="primary" icon={<SearchOutlined />}>
                {searchConfig.enableHybridSearch ? '混合搜索' : '搜索'}
              </Button>
            }
            size="large"
            suffix={
              searchConfig.enableHybridSearch && (
                <Tooltip title="使用兩階段混合檢索">
                  <ThunderboltOutlined style={{ color: '#1890ff' }} />
                </Tooltip>
              )
            }
          />

          {/* 當前搜索配置顯示 */}
          <div className="flex justify-between items-center text-sm text-gray-500">
            <Space size="small">
              <Text type="secondary">搜索模式:</Text>
              <Tag color={searchConfig.enableHybridSearch ? 'blue' : 'default'}>
                {searchConfig.searchType === 'rrf_fusion' ? '🚀 RRF融合' :
                 searchConfig.searchType === 'hybrid' ? '混合檢索' :
                 searchConfig.searchType === 'summary_only' ? '摘要搜索' :
                 searchConfig.searchType === 'chunks_only' ? '文本塊搜索' : '傳統搜索'}
              </Tag>
              <Text type="secondary">閾值: {searchConfig.similarityThreshold}</Text>
              <Text type="secondary">數量: {searchConfig.topK}</Text>
              {searchConfig.searchType === 'rrf_fusion' && (
                <Tag color="purple" title="RRF權重配置">
                  摘要:{searchConfig.rrfSummaryWeight.toFixed(1)} | 內容:{searchConfig.rrfChunksWeight.toFixed(1)}
                </Tag>
              )}
            </Space>
          </div>

          {/* 搜索中指示器 */}
          {isSearching && (
            <div className="text-center p-4">
              <Spin tip={`正在執行${searchConfig.enableHybridSearch ? '混合' : ''}搜索...`} />
            </div>
          )}

          {/* 搜索結果 */}
          {!isSearching && searchResults.length > 0 && (
            <div>
              <Divider orientation="left">
                搜索結果 ({searchResults.length})
                {searchConfig.enableHybridSearch && (
                  <Tag color="blue" className="ml-2">混合檢索</Tag>
                )}
              </Divider>
              <List
                dataSource={searchResults}
                renderItem={renderSearchResultItem}
                pagination={{
                  pageSize: 5,
                  size: 'small',
                  showSizeChanger: false,
                  showQuickJumper: true,
                  showTotal: (total) => `共 ${total} 個結果`
                }}
              />
            </div>
          )}
          
          {/* 無結果提示 */}
          {!isSearching && searchResults.length === 0 && searchQuery && (
            <Empty 
              description={
                <div>
                  <p>沒有找到與您的查詢相關的文檔。</p>
                  <p className="text-sm text-gray-500">
                    嘗試調整搜索策略或降低相似度閾值
                  </p>
                </div>
              } 
            />
          )}
        </div>
      </Card>

      {/* 搜索歷史 */}
      {searchHistory.length > 0 && (
        <Card title="搜索歷史" size="small">
          <List
            size="small"
            dataSource={searchHistory.slice(0, 5)}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<ClockCircleOutlined />}
                  title={(
                    <div className="flex justify-between items-center">
                      <Text
                        className="cursor-pointer text-blue-600 hover:text-blue-800"
                        onClick={() => {
                          setSearchQuery(item.query);
                          handleSemanticSearch(item.query);
                        }}
                      >
                        {item.query}
                      </Text>
                      <Space size="small">
                                                 <Tag color="blue">{item.searchType}</Tag>
                        <Text type="secondary" style={{fontSize: '11px'}}>
                          閾值:{item.similarity_threshold}
                        </Text>
                      </Space>
                    </div>
                  )}
                  description={(
                    <div className="flex justify-between text-xs">
                      <span>{item.resultsCount} 個結果</span>
                      <span>{item.timestamp.toLocaleString('zh-TW')}</span>
                    </div>
                  )}
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* 文檔詳情模態框 */}
      <SearchResultDetailModal
        open={showDocDetailModal}
        onClose={() => {
          setShowDocDetailModal(false);
          setSelectedDocumentForDetail(null);
        }}
        document={selectedDocumentForDetail}
        isLoading={isLoadingDetail}
        searchResults={searchResults}
        showPCMessage={showPCMessage}
      />
    </div>
  );
};

export default SemanticSearchInterface; 