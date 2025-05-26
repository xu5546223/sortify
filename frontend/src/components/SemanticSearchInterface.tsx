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
  Space
} from 'antd';
import {
  SearchOutlined,
  EyeOutlined,
  ClockCircleOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import {
  SemanticSearchResult,
  performSemanticSearch,
  getDocumentById,
  Document
} from '../services/api';
import SearchResultDetailModal from './SearchResultDetailModal';

const { Text, Paragraph } = Typography;

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

  const handleSemanticSearch = async (query?: string) => {
    const currentQuery = query || searchQuery;
    if (!currentQuery.trim()) {
      showPCMessage('請輸入搜索內容', 'error');
      return;
    }

    try {
      setIsSearching(true);
      const results = await performSemanticSearch(currentQuery.trim(), 10, 0.3);
      setSearchResults(results);

      const historyItem: SearchHistoryItem = {
        query: currentQuery.trim(),
        timestamp: new Date(),
        resultsCount: results.length
      };
      // 避免重複添加相同的搜索歷史
      if (!searchHistory.some(item => item.query === currentQuery.trim())) {
        setSearchHistory(prev => [historyItem, ...prev.slice(0, 9)]);
      }
      showPCMessage(`找到 ${results.length} 個相關結果`, 'success');
    } catch (error) {
      console.error('語義搜索失敗:', error);
      showPCMessage('語義搜索失敗', 'error');
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

  return (
    <div className="space-y-6">
      <Card title={cardTitle} extra={extraActions}>
        <div className="space-y-4">
          <Input.Search
            placeholder="在您的知識庫中搜索相關信息..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onSearch={() => handleSemanticSearch()}
            loading={isSearching}
            enterButton="搜索"
            size="large"
          />

          {isSearching && <div className="text-center p-4"><Spin tip="正在搜索..." /></div>}
          {!isSearching && searchResults.length > 0 && (
            <div>
              <Divider orientation="left">搜索結果 ({searchResults.length})</Divider>
              <List
                dataSource={searchResults}
                renderItem={(result, index) => (
                  <List.Item
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
                        <div className="flex justify-between items-center">
                          <Tooltip title={result.document_id}>
                            <Text strong ellipsis style={{ maxWidth: 350 }}>ID: {result.document_id}</Text>
                          </Tooltip>
                          <Tag color="blue">
                            相似度: {(result.similarity_score * 100).toFixed(1)}%
                          </Tag>
                        </div>
                      )}
                      description={(
                        <Paragraph
                          ellipsis={{ rows: 2, expandable: true, symbol: '展開' }}
                          className="text-sm"
                        >
                          {result.summary_text}
                        </Paragraph>
                      )}
                    />
                  </List.Item>
                )}
              />
            </div>
          )}
          {!isSearching && searchResults.length === 0 && searchQuery && (
            <Empty description="沒有找到與您的查詢相關的文檔。" />
          )}
        </div>
      </Card>

      {searchHistory.length > 0 && (
        <Card title="搜索歷史" size="small">
          <List
            size="small"
            dataSource={searchHistory.slice(0, 5)} // 最多顯示5條
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<ClockCircleOutlined />}
                  title={(
                    <Text
                      className="cursor-pointer text-blue-600 hover:text-blue-800"
                      onClick={() => {
                        setSearchQuery(item.query);
                        // 可以選擇立即執行搜索，或僅填充輸入框
                        handleSemanticSearch(item.query);
                      }}
                    >
                      {item.query}
                    </Text>
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

      <SearchResultDetailModal
        open={showDocDetailModal}
        onClose={() => {
          setShowDocDetailModal(false);
          setSelectedDocumentForDetail(null);
        }}
        document={selectedDocumentForDetail}
        isLoading={isLoadingDetail}
        searchResults={searchResults} // 傳遞searchResults以幫助獲取摘要
        showPCMessage={showPCMessage}
      />
    </div>
  );
};

export default SemanticSearchInterface; 