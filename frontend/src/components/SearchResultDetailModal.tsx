import React from 'react';
import { Modal, Tabs, Typography, Spin, Empty, Tag, Button, Descriptions, Alert, Space, Divider, Card } from 'antd';
import { InfoCircleOutlined, ThunderboltOutlined, FileTextOutlined, BulbOutlined } from '@ant-design/icons';
import type { Document, SemanticSearchResult } from '../types/apiTypes';

const { Title, Paragraph, Text } = Typography;
const { TabPane } = Tabs;

interface SearchResultDetailModalProps {
  open: boolean;
  onClose: () => void;
  document: Document | null;
  isLoading: boolean;
  searchResults?: SemanticSearchResult[];
  showPCMessage?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const SearchResultDetailModal: React.FC<SearchResultDetailModalProps> = ({
  open,
  onClose,
  document,
  isLoading,
  searchResults = [],
  showPCMessage,
}) => {
  // 獲取與當前文檔相關的搜索結果
  const getDocumentSearchResults = () => {
    return searchResults.filter(result => result.document_id === document?.id);
  };

  const getSummaryText = () => {
    if (!document) return '摘要信息不可用';
    const searchResultSummary = searchResults.find(sr => sr.document_id === document.id)?.summary_text;
    if (searchResultSummary) return searchResultSummary;
    const aiAnalysisOutput = document.analysis?.ai_analysis_output;
    if (aiAnalysisOutput) {
      if (aiAnalysisOutput.initial_description) return aiAnalysisOutput.initial_description;
      if (aiAnalysisOutput.initial_summary) return aiAnalysisOutput.initial_summary;
      if (aiAnalysisOutput.key_information?.content_summary) return aiAnalysisOutput.key_information.content_summary;
    }
    return document.id || '摘要信息不可用';
  };

  const renderSearchContextTab = () => {
    const docSearchResults = getDocumentSearchResults();
    
    if (docSearchResults.length === 0) {
      return <Empty description="此文檔沒有搜索上下文信息" />;
    }

    return (
      <div className="space-y-4">
        <Alert
          message="搜索匹配信息"
          description="顯示此文檔在當前搜索中的匹配情況和相關信息"
          type="info"
          showIcon
          icon={<ThunderboltOutlined />}
        />
        
        {docSearchResults.map((result, index) => (
          <Card key={index} size="small" className="mb-3 search-match-card">
            <div className="space-y-3">
              {/* 匹配信息頭部 */}
              <div className="flex justify-between items-start">
                <Space>
                  <Tag color={result.vector_type === 'summary' ? 'blue' : 'green'}>
                    {result.vector_type === 'summary' ? '摘要向量' : '文本塊向量'}
                  </Tag>
                  {result.chunk_index !== undefined && (
                    <Tag color="cyan">第 {result.chunk_index + 1} 塊</Tag>
                  )}
                  {result.search_stage && (
                    <Tag color="purple">
                      {result.search_stage === 'stage1' ? '第一階段匹配' : 
                       result.search_stage === 'stage2' ? '第二階段匹配' : '單階段匹配'}
                    </Tag>
                  )}
                </Space>
                <Space>
                  <Text strong>相似度: {(result.similarity_score * 100).toFixed(1)}%</Text>
                  {result.ranking_score && result.ranking_score !== result.similarity_score && (
                    <Text type="secondary">排序分: {(result.ranking_score * 100).toFixed(1)}%</Text>
                  )}
                </Space>
              </div>

              {/* 匹配內容 */}
              <div>
                <Text strong className="block mb-2">匹配內容:</Text>
                <div className="search-match-content p-3">
                  <Paragraph className="mb-0">
                    {result.vector_type === 'chunk' && result.chunk_text ? 
                      result.chunk_text : result.summary_text}
                  </Paragraph>
                </div>
              </div>

              {/* 關鍵信息 */}
              {(result.key_terms || result.knowledge_domains || result.searchable_keywords) && (
                <div>
                  <Text strong className="block mb-2">相關標籤:</Text>
                  <Space wrap>
                    {result.key_terms?.map((term, idx) => (
                      <Tag key={`term-${idx}`} color="cyan">{term}</Tag>
                    ))}
                    {result.knowledge_domains?.map((domain, idx) => (
                      <Tag key={`domain-${idx}`} color="purple">{domain}</Tag>
                    ))}
                    {result.searchable_keywords?.map((keyword, idx) => (
                      <Tag key={`keyword-${idx}`} color="green">{keyword}</Tag>
                    ))}
                  </Space>
                </div>
              )}

              {/* 文檔元數據 */}
              {result.metadata && Object.keys(result.metadata).length > 0 && (
                <div>
                  <Text strong className="block mb-2">元數據:</Text>
                  <div className="bg-gray-50 p-2 rounded text-xs">
                    <pre>{JSON.stringify(result.metadata, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    );
  };

  const renderKeyInformation = () => {
    if (!document?.analysis?.ai_analysis_output?.key_information) {
      return <Empty description="無關鍵信息" />;
    }
    const keyInfo = document.analysis.ai_analysis_output.key_information;
    return (
      <Descriptions column={1} bordered size="small">
        {document.analysis.ai_analysis_output.content_type && (
            <Descriptions.Item label="文檔類型">
              {document.analysis.ai_analysis_output.content_type}
            </Descriptions.Item>
        )}
        {keyInfo.semantic_tags && (
          <Descriptions.Item label="語義標籤">
            {Array.isArray(keyInfo.semantic_tags)
              ? keyInfo.semantic_tags.map((tag: string, idx: number) => (
                  <Tag key={idx} color="blue">{tag}</Tag>
                ))
              : <Tag color="blue">{keyInfo.semantic_tags.toString()}</Tag>}
          </Descriptions.Item>
        )}
        {keyInfo.searchable_keywords && (
          <Descriptions.Item label="可搜索關鍵詞">
            {Array.isArray(keyInfo.searchable_keywords)
              ? keyInfo.searchable_keywords.map((keyword: string, idx: number) => (
                  <Tag key={idx} color="green">{keyword}</Tag>
                ))
              : <Tag color="green">{keyInfo.searchable_keywords.toString()}</Tag>}
          </Descriptions.Item>
        )}
        {keyInfo.knowledge_domains && (
          <Descriptions.Item label="知識領域">
            {Array.isArray(keyInfo.knowledge_domains)
              ? keyInfo.knowledge_domains.map((domain: string, idx: number) => (
                  <Tag key={idx} color="purple">{domain}</Tag>
                ))
              : <Tag color="purple">{keyInfo.knowledge_domains.toString()}</Tag>}
          </Descriptions.Item>
        )}
        {keyInfo.extracted_entities && (
          <Descriptions.Item label="提取實體">
            <pre className="text-xs whitespace-pre-wrap break-all">
              {JSON.stringify(keyInfo.extracted_entities, null, 2)}
            </pre>
          </Descriptions.Item>
        )}
      </Descriptions>
    );
  };

  return (
    <Modal
      title={
        <div className="flex items-center space-x-2">
          <FileTextOutlined />
          <span>文檔詳情: {document?.filename || document?.id || '加載中...'}</span>
          {getDocumentSearchResults().length > 0 && (
            <Tag color="blue">
              {getDocumentSearchResults().length} 個搜索匹配
            </Tag>
          )}
        </div>
      }
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          關閉
        </Button>
      ]}
      width={1200}
      className="document-detail-modal"
      styles={{ body: { maxHeight: '75vh', overflowY: 'auto' } }}
    >
      {isLoading && !document ? (
        <div className="text-center p-8"><Spin size="large" tip="正在加載詳細信息..." /></div>
      ) : document ? (
        <Tabs defaultActiveKey="summaryDetails">
          {/* 搜索匹配上下文標籤頁 - 如果有搜索結果就顯示 */}
          {getDocumentSearchResults().length > 0 && (
            <TabPane 
              tab={
                <Space>
                  <BulbOutlined />
                  搜索匹配上下文
                  <Tag color="blue">{getDocumentSearchResults().length}</Tag>
                </Space>
              } 
              key="searchContext"
            >
              {renderSearchContextTab()}
            </TabPane>
          )}
          
          <TabPane tab="向量化內容" key="summaryDetails">
            <Title level={5}>用於向量化的摘要文本</Title>
            <div className="bg-yellow-50 p-2 mb-3 rounded text-xs">
              <InfoCircleOutlined className="mr-1" /> 文檔ID: {document.id}
            </div>
            <Paragraph copyable className="bg-gray-100 p-3 rounded">
              {getSummaryText()}
            </Paragraph>
            {document.analysis?.ai_analysis_output && (
              <div className="mt-4">
                <Title level={5}>向量化詳細內容</Title>
                <div className="bg-gray-50 p-3 rounded border border-gray-200">
                  <Tabs type="card" size="small">
                    <TabPane tab="文本摘要" key="textSummary">
                      {document.analysis.ai_analysis_output.initial_summary ||
                       document.analysis.ai_analysis_output.key_information?.content_summary ? (
                        <Paragraph copyable className="whitespace-pre-wrap">
                          {document.analysis.ai_analysis_output.initial_summary ||
                           document.analysis.ai_analysis_output.key_information?.content_summary}
                        </Paragraph>
                      ) : (
                        <Empty description="無文本摘要信息" />
                      )}
                    </TabPane>
                    <TabPane tab="關鍵信息" key="fullData">
                      <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                        {renderKeyInformation()}
                      </div>
                    </TabPane>
                  </Tabs>
                </div>
              </div>
            )}
            {document.analysis?.ai_analysis_output?.key_information?.semantic_tags && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>相關關鍵詞</Title>
                <div>
                  {Array.isArray(document.analysis.ai_analysis_output.key_information.semantic_tags)
                    ? document.analysis.ai_analysis_output.key_information.semantic_tags.map((term: string, index: number) => (
                        <Tag key={index} color="cyan">{term}</Tag>
                      ))
                    : <Tag color="cyan">{document.analysis.ai_analysis_output.key_information.semantic_tags.toString()}</Tag>}
                </div>
              </>
            )}
          </TabPane>
          
          <TabPane tab="原始提取文本" key="extractedText">
            <Title level={5}>原始提取文本</Title>
            {document.extracted_text ? (
              <Paragraph
                className="bg-gray-100 p-3 rounded whitespace-pre-wrap max-h-96 overflow-y-auto"
                copyable
              >
                {document.extracted_text}
              </Paragraph>
            ) : (
              document.file_type?.startsWith('image/') ? (
                <Empty
                  description={(
                    <div>
                      <p>此為圖片文件，通常不直接包含長篇提取文本。</p>
                      {document.analysis?.ai_analysis_output?.extracted_text ? (
                        <p>AI分析結果中提取的文本如下：</p>
                      ) : (
                        <p>如需查看可能的OCR文本，請檢查 "AI 完整分析 (JSON)" 標籤頁中的 `extracted_text` (如果存在)。</p>
                      )}
                    </div>
                  )}
                />
              ) : (
                <Empty description="沒有可用的原始提取文本" />
              )
            )}
            {!document.extracted_text && document.analysis?.ai_analysis_output?.extracted_text && (
              <div className='mt-4'>
                <Title level={5}>AI分析提取的文本 (OCR)</Title>
                <Paragraph
                  className="bg-gray-100 p-3 rounded whitespace-pre-wrap max-h-96 overflow-y-auto"
                  copyable
                >
                  {document.analysis.ai_analysis_output.extracted_text}
                </Paragraph>
              </div>
            )}
          </TabPane>
          
          <TabPane tab="AI 完整分析 (JSON)" key="aiAnalysis">
            <Title level={5}>AI 完整分析結果</Title>
            {document.analysis?.ai_analysis_output ? (
              <div className="bg-gray-100 p-3 rounded max-h-[50vh] overflow-y-auto">
                <pre className="whitespace-pre-wrap break-all">
                  {JSON.stringify(document.analysis.ai_analysis_output, null, 2)}
                </pre>
              </div>
            ) : (
              <Empty description="沒有可用的 AI 分析結果" />
            )}
          </TabPane>
        </Tabs>
      ) : (
        <Empty description="無法加載文檔詳細信息。" />
      )}
    </Modal>
  );
};

export default SearchResultDetailModal; 