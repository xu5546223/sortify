import React, { useState, useEffect } from 'react';
import {
  Card,
  Collapse,
  Slider,
  InputNumber,
  Switch,
  Space,
  Typography,
  Tooltip,
  Button,
  Divider,
  Row,
  Col,
  Tag,
  Alert,
  Badge,
  Statistic
} from 'antd';
import {
  SettingOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  FileTextOutlined,
  BranchesOutlined,
  FilterOutlined,
  ClockCircleOutlined,
  ExperimentOutlined
} from '@ant-design/icons';

const { Text, Title } = Typography;
const { Panel } = Collapse;

export interface AIQASettingsConfig {
  // 基礎設定
  use_ai_detailed_query: boolean;
  use_semantic_search: boolean;
  use_structured_filter: boolean;
  
  // 檢索設定
  context_limit: number;
  similarity_threshold: number;
  max_documents_for_selection: number;
  ai_selection_limit: number;
  
  // 查詢優化
  query_rewrite_count: number;
  detailed_text_max_length: number;
  max_chars_per_doc: number; // 單文檔字符限制
  enable_query_expansion: boolean;
  context_window_overlap: number;
  
  // 輸入處理設定
  prompt_input_max_length: number; // 對應後端的 document_context 最大長度限制
}

interface AIQASettingsProps {
  settings: AIQASettingsConfig;
  onChange: (settings: AIQASettingsConfig) => void;
  onReset?: () => void;
}

// 預設配置模式
export const AIQAPresetModes = {
  low: {
    name: '輕量模式',
    description: '快速回應，適合簡單查詢',
    color: '#52c41a',
    settings: {
      use_ai_detailed_query: false,
      use_semantic_search: true,
      use_structured_filter: false,
      context_limit: 5,
      similarity_threshold: 0.4,
      max_documents_for_selection: 5,
      ai_selection_limit: 1,
      query_rewrite_count: 1,
      detailed_text_max_length: 3000,
      max_chars_per_doc: 1500,
      enable_query_expansion: false,
      context_window_overlap: 0.0,
      prompt_input_max_length: 4000
    }
  },
  medium: {
    name: '平衡模式',
    description: '兼顧速度與準確性，適合一般使用',
    color: '#1890ff',
    settings: {
      use_ai_detailed_query: true,
      use_semantic_search: true,
      use_structured_filter: false,
      context_limit: 10,
      similarity_threshold: 0.3,
      max_documents_for_selection: 8,
      ai_selection_limit: 3,
      query_rewrite_count: 3,
      detailed_text_max_length: 8000,
      max_chars_per_doc: 3000,
      enable_query_expansion: true,
      context_window_overlap: 0.1,
      prompt_input_max_length: 6000
    }
  },
  high: {
    name: '高精度模式',
    description: '最高準確性，適合複雜查詢',
    color: '#f5222d',
    settings: {
      use_ai_detailed_query: true,
      use_semantic_search: true,
      use_structured_filter: true,
      context_limit: 20,
      similarity_threshold: 0.2,
      max_documents_for_selection: 12,
      ai_selection_limit: 5,
      query_rewrite_count: 5,
      detailed_text_max_length: 15000,
      max_chars_per_doc: 5000,
      enable_query_expansion: true,
      context_window_overlap: 0.2,
      prompt_input_max_length: 8000
    }
  }
} as const;

// 預設配置（使用平衡模式）
export const defaultAIQASettings: AIQASettingsConfig = AIQAPresetModes.medium.settings;

const AIQASettings: React.FC<AIQASettingsProps> = ({ settings, onChange, onReset }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // 更新設定的輔助函數
  const updateSetting = <K extends keyof AIQASettingsConfig>(
    key: K,
    value: AIQASettingsConfig[K]
  ) => {
    onChange({
      ...settings,
      [key]: value
    });
  };

  // 應用預設模式
  const applyPresetMode = (mode: keyof typeof AIQAPresetModes) => {
    onChange(AIQAPresetModes[mode].settings);
  };

  // 重置為預設值
  const handleReset = () => {
    onChange(defaultAIQASettings);
    if (onReset) onReset();
  };

  // 修正性能影響分數計算
  const calculatePerformanceImpact = () => {
    let score = 0;
    
    // AI詳細查詢 (0-3分)
    score += settings.use_ai_detailed_query ? 3 : 0;
    
    // 上下文數量 (0-3分)
    score += Math.min(settings.context_limit / 10, 3);
    
    // 查詢重寫數量 (0-2分)
    score += Math.min(settings.query_rewrite_count / 2, 2);
    
    // 候選文件數量 (0-2分)
    score += Math.min(settings.max_documents_for_selection / 6, 2);
    
    // AI選擇數量 (0-2分)
    score += Math.min(settings.ai_selection_limit / 2, 2);
    
    // 詳細文本長度 (0-3分)
    score += Math.min(settings.detailed_text_max_length / 5000, 3);
    
    // 單文檔字符限制 (0-2分)
    score += Math.min(settings.max_chars_per_doc / 2500, 2);
    
    // 查詢擴展 (0-1分)
    score += settings.enable_query_expansion ? 1 : 0;
    
    // 結構化過濾 (0-1分)
    score += settings.use_structured_filter ? 1 : 0;
    
    return Math.min(score, 17); // 最高17分
  };

  // 預估Token使用量（更準確的計算）
  const estimateTokenUsage = () => {
    let baseTokens = 500; // 基礎Token
    
    // 上下文貢獻
    baseTokens += settings.context_limit * 200;
    
    // 詳細查詢貢獻
    if (settings.use_ai_detailed_query) {
      baseTokens += settings.ai_selection_limit * (settings.detailed_text_max_length / 4); // 大約4字符=1token
    }
    
    // 查詢重寫貢獻
    baseTokens += settings.query_rewrite_count * 100;
    
    return Math.round(baseTokens);
  };

  // 預估處理時間（秒）
  const estimateProcessingTime = () => {
    let baseTime = 2; // 基礎時間
    
    // AI詳細查詢增加時間
    if (settings.use_ai_detailed_query) {
      baseTime += settings.ai_selection_limit * 3;
    }
    
    // 查詢重寫增加時間
    baseTime += settings.query_rewrite_count * 0.5;
    
    // 大文件處理增加時間
    if (settings.detailed_text_max_length > 10000) {
      baseTime += 2;
    }
    
    return Math.round(baseTime * 10) / 10; // 保留一位小數
  };

  const performanceScore = calculatePerformanceImpact();
  const getPerformanceLevel = (score: number) => {
    if (score <= 6) return { level: '輕量', color: '#52c41a' };
    if (score <= 11) return { level: '平衡', color: '#1890ff' };
    if (score <= 14) return { level: '高性能', color: '#faad14' };
    return { level: '最大化', color: '#f5222d' };
  };

  const performanceInfo = getPerformanceLevel(performanceScore);

  return (
    <Card 
      size="small"
      className="aiqa-settings-card"
      title={
        <div className="flex items-center justify-between">
          <Space>
            <SettingOutlined />
            <Text strong>AI 問答參數設定</Text>
            <Badge 
              count={performanceInfo.level} 
              style={{ backgroundColor: performanceInfo.color }}
            />
          </Space>
          <Button 
            size="small" 
            icon={<ReloadOutlined />} 
            onClick={handleReset}
            type="text"
          >
            重置
          </Button>
        </div>
      }
    >
      {/* 預設模式快速選擇 */}
      <div className="mb-4">
        <Text strong className="block mb-2">快速模式選擇：</Text>
        <Space wrap>
          {Object.entries(AIQAPresetModes).map(([key, mode]) => (
            <Button
              key={key}
              size="small"
              onClick={() => applyPresetMode(key as keyof typeof AIQAPresetModes)}
              style={{ 
                borderColor: mode.color,
                color: mode.color
              }}
              icon={
                key === 'low' ? <ThunderboltOutlined /> :
                key === 'medium' ? <SearchOutlined /> :
                <ExperimentOutlined />
              }
            >
              {mode.name}
            </Button>
          ))}
        </Space>
        <Text type="secondary" className="text-xs block mt-1">
          點擊快速應用預設配置，也可展開下方進行詳細調整
        </Text>
      </div>

      <Collapse 
        ghost 
        activeKey={isExpanded ? '1' : []}
        onChange={(keys) => setIsExpanded(keys.includes('1'))}
      >
        <Panel
          header={
            <Space>
              <ExperimentOutlined />
              <Text>詳細參數配置</Text>
              <Tag color={performanceInfo.color} className="ml-2">
                {performanceInfo.level}模式
              </Tag>
            </Space>
          }
          key="1"
        >
          <div className="space-y-6">
            {/* 基礎設定 */}
            <div>
              <Title level={5} className="mb-3">
                <ThunderboltOutlined className="mr-2" />
                基礎設定
              </Title>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={8}>
                  <div className="flex items-center justify-between">
                    <Space>
                      <Text>AI 詳細查詢</Text>
                      <Tooltip title="啟用後，AI 會對選中的文件進行深度查詢，獲取更精確的資訊">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Switch
                      checked={settings.use_ai_detailed_query}
                      onChange={(value) => updateSetting('use_ai_detailed_query', value)}
                    />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div className="flex items-center justify-between">
                    <Space>
                      <Text>語義搜索</Text>
                      <Tooltip title="使用向量搜索找到語義相關的文件">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Switch
                      checked={settings.use_semantic_search}
                      onChange={(value) => updateSetting('use_semantic_search', value)}
                    />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div className="flex items-center justify-between">
                    <Space>
                      <Text>查詢擴展</Text>
                      <Tooltip title="啟用智慧查詢擴展和同義詞匹配">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Switch
                      checked={settings.enable_query_expansion}
                      onChange={(value) => updateSetting('enable_query_expansion', value)}
                    />
                  </div>
                </Col>
              </Row>
            </div>

            <Divider />

            {/* 檢索設定 */}
            <div>
              <Title level={5} className="mb-3">
                <SearchOutlined className="mr-2" />
                檢索設定
              </Title>
              <Row gutter={[16, 24]}>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>上下文文件數量</Text>
                      <Tag color="blue">{settings.context_limit}</Tag>
                    </Space>
                    <Slider
                      min={1}
                      max={50}
                      value={settings.context_limit}
                      onChange={(value) => updateSetting('context_limit', value)}
                      marks={{
                        1: '1',
                        10: '10',
                        20: '20',
                        50: '50'
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      影響檢索的文件數量，更多文件提供更豐富的上下文
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>相似度閾值</Text>
                      <Tag color="green">{(settings.similarity_threshold * 100).toFixed(0)}%</Tag>
                    </Space>
                    <Slider
                      min={0.1}
                      max={0.8}
                      step={0.05}
                      value={settings.similarity_threshold}
                      onChange={(value) => updateSetting('similarity_threshold', value)}
                      marks={{
                        0.1: '10%',
                        0.3: '30%',
                        0.5: '50%',
                        0.8: '80%'
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      過濾相似度過低的文件，提高檢索精度
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>候選文件數量</Text>
                      <Tag color="purple">{settings.max_documents_for_selection}</Tag>
                    </Space>
                    <Slider
                      min={3}
                      max={15}
                      value={settings.max_documents_for_selection}
                      onChange={(value) => updateSetting('max_documents_for_selection', value)}
                      marks={{
                        3: '3',
                        8: '8',
                        15: '15'
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      提供給 AI 選擇的候選文件數量
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>AI 選擇限制</Text>
                      <Tag color="orange">{settings.ai_selection_limit}</Tag>
                    </Space>
                    <Slider
                      min={1}
                      max={8}
                      value={settings.ai_selection_limit}
                      onChange={(value) => updateSetting('ai_selection_limit', value)}
                      marks={{
                        1: '1',
                        3: '3',
                        5: '5',
                        8: '8'
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      AI 最多可以選擇多少個文件進行詳細查詢
                    </Text>
                  </div>
                </Col>
              </Row>
            </div>

            <Divider />

            {/* 查詢優化 */}
            <div>
              <Title level={5} className="mb-3">
                <BranchesOutlined className="mr-2" />
                查詢優化
              </Title>
              <Row gutter={[16, 24]}>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>查詢重寫數量</Text>
                      <Tag color="cyan">{settings.query_rewrite_count}</Tag>
                    </Space>
                    <Slider
                      min={1}
                      max={8}
                      value={settings.query_rewrite_count}
                      onChange={(value) => updateSetting('query_rewrite_count', value)}
                      marks={{
                        1: '1',
                        3: '3',
                        5: '5',
                        8: '8'
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      生成多少種不同角度的查詢重寫，增加搜索覆蓋面
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>詳細文本長度</Text>
                      <Tag color="magenta">{(settings.detailed_text_max_length / 1000).toFixed(1)}K</Tag>
                      <Tooltip title="控制AI問答時文檔內容的最大處理長度。較低的值會截斷長文檔但響應更快；較高的值保留更多文檔細節但消耗更多Token和時間。這個設定會直接影響文檔截斷邏輯。">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Slider
                      min={1000}
                      max={20000}
                      step={500}
                      value={settings.detailed_text_max_length}
                      onChange={(value) => updateSetting('detailed_text_max_length', value)}
                      marks={{
                        1000: { label: '1K', style: { fontSize: '10px' }},
                        3000: { label: '3K (輕量)', style: { fontSize: '10px', color: '#52c41a' }},
                        8000: { label: '8K (平衡)', style: { fontSize: '10px', color: '#1890ff' }},
                        15000: { label: '15K (高精度)', style: { fontSize: '10px', color: '#f5222d' }},
                        20000: { label: '20K', style: { fontSize: '10px' }}
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      控制文檔內容的處理長度，較高的值保留更多文檔細節但消耗更多資源
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>單文檔字符限制</Text>
                      <Tag color="volcano">{(settings.max_chars_per_doc / 1000).toFixed(1)}K</Tag>
                      <Tooltip title="控制每個單獨文檔在處理前的最大字符數。超過此限制的文檔會被截斷（保留前後部分）。這是對每個文檔獨立的限制，與總文本長度限制配合使用。">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Slider
                      min={500}
                      max={8000}
                      step={250}
                      value={settings.max_chars_per_doc}
                      onChange={(value) => updateSetting('max_chars_per_doc', value)}
                      marks={{
                        500: { label: '0.5K', style: { fontSize: '10px' }},
                        1500: { label: '1.5K (輕量)', style: { fontSize: '10px', color: '#52c41a' }},
                        3000: { label: '3K (平衡)', style: { fontSize: '10px', color: '#1890ff' }},
                        5000: { label: '5K (高精度)', style: { fontSize: '10px', color: '#f5222d' }},
                        8000: { label: '8K', style: { fontSize: '10px' }}
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      控制單個文檔的最大字符數，超過限制會被截斷處理
                    </Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div>
                    <Space className="mb-2">
                      <Text strong>提示詞輸入長度限制</Text>
                      <Tag color="gold">{(settings.prompt_input_max_length / 1000).toFixed(1)}K</Tag>
                      <Tooltip title="控制發送給AI的提示詞中文檔上下文的最大長度。較低的值避免輸入過長導致處理錯誤，較高的值保留更完整的上下文。建議與詳細文本長度協調設定。">
                        <InfoCircleOutlined style={{ color: '#1890ff' }} />
                      </Tooltip>
                    </Space>
                    <Slider
                      min={2000}
                      max={10000}
                      step={500}
                      value={settings.prompt_input_max_length}
                      onChange={(value) => updateSetting('prompt_input_max_length', value)}
                      marks={{
                        2000: { label: '2K', style: { fontSize: '10px' }},
                        4000: { label: '4K (輕量)', style: { fontSize: '10px', color: '#52c41a' }},
                        6000: { label: '6K (平衡)', style: { fontSize: '10px', color: '#1890ff' }},
                        8000: { label: '8K (高精度)', style: { fontSize: '10px', color: '#f5222d' }},
                        10000: { label: '10K', style: { fontSize: '10px' }}
                      }}
                    />
                    <Text type="secondary" className="text-xs">
                      控制提示詞輸入的最大長度，避免因輸入過長導致處理失敗
                    </Text>
                  </div>
                </Col>
              </Row>
            </div>

            <Divider />

            {/* 性能統計 */}
            <div>
              <Title level={5} className="mb-3">
                <ClockCircleOutlined className="mr-2" />
                性能預估
              </Title>
              <Row gutter={16}>
                <Col xs={8}>
                  <Statistic
                    title="性能等級"
                    value={performanceInfo.level}
                    valueStyle={{ color: performanceInfo.color }}
                  />
                </Col>
                <Col xs={8}>
                  <Statistic
                    title="預估 Token"
                    value={estimateTokenUsage()}
                    suffix="個"
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Col>
                <Col xs={8}>
                  <Statistic
                    title="處理時間"
                    value={estimateProcessingTime()}
                    suffix="秒"
                    valueStyle={{ color: '#722ed1' }}
                  />
                </Col>
              </Row>
              <Alert
                message="參數調整建議"
                description={
                  <div>
                    {performanceScore <= 5 
                      ? "當前配置較為輕量，適合快速查詢和簡單問題。文檔會適度截斷以確保回應速度。" 
                      : performanceScore <= 10 
                      ? "當前配置平衡了性能和準確性，適合大多數使用場景。文檔內容保留適中。"
                      : "當前配置追求最高準確性，適合複雜查詢，文檔內容保留較完整，但會消耗較多資源和時間。"}
                    <br />
                    <Text type="secondary" className="text-xs">
                      💡 詳細文本長度設定會直接影響AI分析時的文檔處理範圍
                    </Text>
                  </div>
                }
                type={performanceScore <= 10 ? "info" : "warning"}
                className="mt-4"
                showIcon
              />
            </div>
          </div>
        </Panel>
      </Collapse>
    </Card>
  );
};

export default AIQASettings; 