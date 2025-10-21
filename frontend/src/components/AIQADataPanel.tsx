import React from 'react';
import { Card, Tag, List, Typography, Collapse, Empty, Statistic, Row, Col } from 'antd';
import {
  RetweetOutlined,
  SearchOutlined,
  BulbOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import type {
  QueryRewriteResult,
  SemanticContextDocument,
  LLMContextDocument
} from '../types/apiTypes';

const { Text, Paragraph } = Typography;
const { Panel } = Collapse;

interface AIQADataPanelProps {
  queryRewriteResult?: QueryRewriteResult | null;
  semanticSearchContexts?: SemanticContextDocument[] | null;
  llmContextDocuments?: LLMContextDocument[] | null;
  tokensUsed?: number;
  processingTime?: number;
  confidenceScore?: number;
  detailedDocumentDataFromAiQuery?: Record<string, any> | null;
  detailedQueryReasoning?: string | null;
}

/**
 * AI QA 數據面板組件
 * 顯示查詢重寫、向量搜索、LLM上下文等處理過程數據
 */
const AIQADataPanel: React.FC<AIQADataPanelProps> = ({
  queryRewriteResult,
  semanticSearchContexts,
  llmContextDocuments,
  tokensUsed,
  processingTime,
  confidenceScore,
  detailedDocumentDataFromAiQuery,
  detailedQueryReasoning
}) => {
  // 如果沒有任何數據,顯示空狀態
  const hasData = queryRewriteResult || 
                  (semanticSearchContexts && semanticSearchContexts.length > 0) ||
                  (llmContextDocuments && llmContextDocuments.length > 0) ||
                  detailedDocumentDataFromAiQuery;

  if (!hasData) {
    return (
      <div className="p-4">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="尚未有查詢數據"
          className="py-8"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 數據統計概覽 - 固定在頂部 */}
      <div className="flex-shrink-0 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-200">
        <Text strong className="block mb-3 text-gray-700">處理統計</Text>
        <Row gutter={[12, 12]}>
          <Col span={12}>
            <Card size="small" className="text-center shadow-sm">
              <Statistic
                title={<span className="text-xs">處理時間</span>}
                value={processingTime?.toFixed(2) || 0}
                suffix="s"
                valueStyle={{ fontSize: '16px', color: '#1890ff' }}
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" className="text-center shadow-sm">
              <Statistic
                title={<span className="text-xs">Token 使用</span>}
                value={tokensUsed || 0}
                valueStyle={{ fontSize: '16px', color: '#52c41a' }}
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          {confidenceScore !== undefined && (
            <Col span={24}>
              <Card size="small" className="text-center shadow-sm">
                <Statistic
                  title={<span className="text-xs">置信度</span>}
                  value={(confidenceScore * 100).toFixed(0)}
                  suffix="%"
                  valueStyle={{ fontSize: '16px', color: '#fa8c16' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
          )}
        </Row>
      </div>

      {/* 詳細數據折疊面板 - 可滾動區域 */}
      <div className="flex-1 overflow-y-auto">
        <Collapse
          defaultActiveKey={['query-rewrite', 'vector-search', 'llm-context', 'ai-detailed-query']}
          ghost
          className="bg-white"
        >
        {/* 查詢重寫 */}
        {queryRewriteResult && (
          <Panel
            header={
              <div className="flex items-center space-x-2">
                <RetweetOutlined className="text-purple-500" />
                <Text strong className="text-sm">查詢重寫</Text>
                <Tag color="purple" className="ml-2 text-xs">
                  {queryRewriteResult.rewritten_queries?.length || 0} 個重寫
                </Tag>
              </div>
            }
            key="query-rewrite"
          >
            <div className="space-y-3">
              {/* 查詢分析摘要 */}
              {(queryRewriteResult.reasoning ||
                queryRewriteResult.query_granularity ||
                queryRewriteResult.search_strategy_suggestion) && (
                <div className="p-3 bg-purple-50 rounded-lg border-l-4 border-purple-400">
                  <div className="space-y-2">
                    {queryRewriteResult.reasoning && (
                      <div>
                        <Text strong className="text-xs text-purple-700">分析推理:</Text>
                        <Paragraph className="text-xs text-gray-700 mb-1 mt-1">
                          {queryRewriteResult.reasoning}
                        </Paragraph>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      {queryRewriteResult.query_granularity && (
                        <Tag color="blue" className="text-xs">
                          粒度: {queryRewriteResult.query_granularity}
                        </Tag>
                      )}
                      {queryRewriteResult.search_strategy_suggestion && (
                        <Tag color="purple" className="text-xs">
                          策略: {queryRewriteResult.search_strategy_suggestion}
                        </Tag>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* 原始查詢 */}
              <div className="p-2 bg-gray-50 rounded border border-gray-200">
                <Text type="secondary" className="text-xs block mb-1">原始查詢:</Text>
                <Text className="text-sm">{queryRewriteResult.original_query}</Text>
              </div>

              {/* 重寫的查詢列表 */}
              {queryRewriteResult.rewritten_queries && queryRewriteResult.rewritten_queries.length > 0 && (
                <div>
                  <Text type="secondary" className="text-xs block mb-2">重寫查詢:</Text>
                  <div className="space-y-2">
                    {queryRewriteResult.rewritten_queries.map((query, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-blue-50 rounded border border-blue-200 hover:shadow-sm transition-shadow"
                      >
                        <div className="flex items-start space-x-2">
                          <Tag color="blue" className="text-xs flex-shrink-0 mt-0.5">#{idx + 1}</Tag>
                          <Text className="text-sm flex-1">{query}</Text>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Panel>
        )}

        {/* 向量搜索結果 */}
        {semanticSearchContexts && semanticSearchContexts.length > 0 && (
          <Panel
            header={
              <div className="flex items-center space-x-2">
                <SearchOutlined className="text-green-500" />
                <Text strong className="text-sm">向量搜索</Text>
                <Tag color="green" className="ml-2 text-xs">
                  {semanticSearchContexts.length} 個結果
                </Tag>
              </div>
            }
            key="vector-search"
          >
            <List
              size="small"
              dataSource={semanticSearchContexts}
              renderItem={(doc, index) => (
                <List.Item className="!px-0">
                  <div className="w-full p-2 hover:bg-gray-50 rounded transition-colors">
                    <div className="flex items-center justify-between mb-1">
                      <Text strong className="text-xs text-gray-700">
                        匹配 #{index + 1}
                      </Text>
                      <Tag color="green" className="text-xs">
                        {(doc.similarity_score * 100).toFixed(1)}% 相似度
                      </Tag>
                    </div>
                    <Text type="secondary" className="text-xs block mb-1">
                      文檔ID: {doc.document_id}
                    </Text>
                    <Paragraph
                      ellipsis={{ rows: 3, expandable: true, symbol: '展開' }}
                      className="text-xs text-gray-600 mb-0 bg-green-50 p-2 rounded"
                    >
                      {doc.summary_or_chunk_text}
                    </Paragraph>
                  </div>
                </List.Item>
              )}
            />
          </Panel>
        )}

        {/* LLM 使用的上下文 */}
        {llmContextDocuments && llmContextDocuments.length > 0 && (
          <Panel
            header={
              <div className="flex items-center space-x-2">
                <BulbOutlined className="text-orange-500" />
                <Text strong className="text-sm">LLM 上下文</Text>
                <Tag color="orange" className="ml-2 text-xs">
                  {llmContextDocuments.length} 個片段
                </Tag>
              </div>
            }
            key="llm-context"
          >
            <List
              size="small"
              dataSource={llmContextDocuments}
              renderItem={(doc, index) => (
                <List.Item className="!px-0">
                  <div className="w-full p-2 hover:bg-gray-50 rounded transition-colors">
                    <div className="flex items-center justify-between mb-1">
                      <Text strong className="text-xs text-gray-700">
                        片段 #{index + 1}
                      </Text>
                      <Tag color="orange" className="text-xs">
                        {doc.source_type}
                      </Tag>
                    </div>
                    <Text type="secondary" className="text-xs block mb-1">
                      文檔ID: {doc.document_id}
                    </Text>
                    <Paragraph
                      ellipsis={{ rows: 3, expandable: true, symbol: '展開' }}
                      className="text-xs text-gray-600 mb-0 bg-orange-50 p-2 rounded"
                    >
                      {doc.content_used}
                    </Paragraph>
                  </div>
                </List.Item>
              )}
            />
          </Panel>
        )}

        {/* AI 詳細查詢結果 */}
        {detailedDocumentDataFromAiQuery && (
          <Panel
            header={
              <div className="flex items-center space-x-2">
                <SearchOutlined className="text-indigo-500" />
                <Text strong className="text-sm">AI 詳細查詢</Text>
              </div>
            }
            key="ai-detailed-query"
          >
            <div className="space-y-3">
              {detailedQueryReasoning && (
                <div className="p-3 bg-indigo-50 rounded-lg border-l-4 border-indigo-400">
                  <Text strong className="text-xs text-indigo-700 block mb-2">查詢原因:</Text>
                  <Paragraph className="text-xs text-gray-700 mb-0">
                    {detailedQueryReasoning}
                  </Paragraph>
                </div>
              )}
              <div>
                <Text strong className="text-xs block mb-2 text-gray-700">查詢到的詳細資料:</Text>
                <div className="bg-indigo-50 p-3 rounded border border-indigo-200 max-h-64 overflow-y-auto">
                  <pre className="whitespace-pre-wrap font-mono text-xs text-gray-800">
                    {JSON.stringify(detailedDocumentDataFromAiQuery, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </Panel>
        )}
        </Collapse>
      </div>
    </div>
  );
};

export default AIQADataPanel;

