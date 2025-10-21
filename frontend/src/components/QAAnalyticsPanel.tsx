/**
 * QA問答統計分析面板
 * 
 * 顯示問答系統的性能指標、意圖分佈、成本節省等統計數據
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Progress,
  Table,
  Tag,
  Space,
  Select,
  Button,
  Alert,
  Spin,
  Divider,
  Typography
} from 'antd';
import {
  ThunderboltOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  CheckCircleOutlined,
  QuestionCircleOutlined,
  LineChartOutlined,
  ReloadOutlined,
  TrophyOutlined
} from '@ant-design/icons';
import { qaAnalyticsService, QAStatistics } from '../services/qaAnalyticsService';
import { INTENT_LABELS, getIntentColor } from '../types/qaWorkflow';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const QAAnalyticsPanel: React.FC = () => {
  const [statistics, setStatistics] = useState<QAStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<string>('24h');
  const [error, setError] = useState<string | null>(null);

  // 載入統計數據
  const loadStatistics = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await qaAnalyticsService.getStatistics(timeRange);
      setStatistics(data);
    } catch (err: any) {
      console.error('載入統計數據失敗:', err);
      setError(err.message || '載入統計數據失敗');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatistics();
  }, [timeRange]);

  // 渲染關鍵指標卡片
  const renderKeyMetrics = () => {
    if (!statistics) return null;

    return (
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="總問題數"
              value={statistics.total_questions}
              prefix={<QuestionCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均API調用"
              value={statistics.avg_api_calls}
              suffix="次"
              precision={1}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
            <Text type="secondary" style={{ fontSize: '12px' }}>
              vs 舊系統 {statistics.cost_metrics.baseline_comparison.old_avg_api_calls} 次
            </Text>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="平均響應時間"
              value={statistics.avg_response_time}
              suffix="秒"
              precision={1}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="成本節省"
              value={statistics.cost_metrics.cost_saved_percentage}
              suffix="%"
              precision={1}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#f5222d' }}
            />
            {statistics.cost_metrics.cost_saved_percentage > 0 && (
              <Tag color="success" style={{ marginTop: 8 }}>
                <TrophyOutlined /> 優化成功
              </Tag>
            )}
          </Card>
        </Col>
      </Row>
    );
  };

  // 渲染意圖分佈
  const renderIntentDistribution = () => {
    if (!statistics || !statistics.by_intent) return null;

    const intentData = Object.entries(statistics.by_intent).map(([intent, data]) => ({
      intent,
      label: INTENT_LABELS[intent as keyof typeof INTENT_LABELS] || intent,
      count: data.count,
      percentage: ((data.count / statistics.total_questions) * 100).toFixed(1),
      avg_api_calls: data.avg_api_calls.toFixed(1),
      avg_time: data.avg_time.toFixed(2),
      avg_confidence: (data.avg_confidence * 100).toFixed(0)
    }));

    const columns = [
      {
        title: '問題類型',
        dataIndex: 'label',
        key: 'label',
        render: (text: string, record: any) => (
          <Space>
            <Tag color={getIntentColor(record.intent)}>{text}</Tag>
          </Space>
        )
      },
      {
        title: '數量',
        dataIndex: 'count',
        key: 'count',
        sorter: (a: any, b: any) => a.count - b.count,
        render: (count: number) => <Text strong>{count}</Text>
      },
      {
        title: '佔比',
        dataIndex: 'percentage',
        key: 'percentage',
        render: (percentage: string, record: any) => (
          <div style={{ width: '100%' }}>
            <Progress 
              percent={parseFloat(percentage)} 
              size="small" 
              format={p => `${p}%`}
            />
          </div>
        )
      },
      {
        title: '平均API調用',
        dataIndex: 'avg_api_calls',
        key: 'avg_api_calls',
        sorter: (a: any, b: any) => parseFloat(a.avg_api_calls) - parseFloat(b.avg_api_calls),
        render: (calls: string) => (
          <Tag color={parseFloat(calls) < 2 ? 'success' : parseFloat(calls) < 3 ? 'warning' : 'default'}>
            {calls} 次
          </Tag>
        )
      },
      {
        title: '平均時間',
        dataIndex: 'avg_time',
        key: 'avg_time',
        sorter: (a: any, b: any) => parseFloat(a.avg_time) - parseFloat(b.avg_time),
        render: (time: string) => `${time}秒`
      },
      {
        title: '置信度',
        dataIndex: 'avg_confidence',
        key: 'avg_confidence',
        render: (confidence: string) => `${confidence}%`
      }
    ];

    return (
      <Card 
        title={
          <Space>
            <LineChartOutlined />
            <span>問題類型分佈</span>
          </Space>
        }
      >
        <Table
          dataSource={intentData}
          columns={columns}
          pagination={false}
          size="small"
          rowKey="intent"
        />
      </Card>
    );
  };

  // 渲染性能改善卡片
  const renderPerformanceImprovement = () => {
    if (!statistics) return null;

    const baseline = statistics.cost_metrics.baseline_comparison;
    const apiReduction = ((baseline.old_avg_api_calls - baseline.new_avg_api_calls) / baseline.old_avg_api_calls * 100).toFixed(1);

    return (
      <Card
        title={
          <Space>
            <TrophyOutlined />
            <span>性能改善對比</span>
          </Space>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div style={{ textAlign: 'center', padding: '16px' }}>
              <Title level={4}>API調用次數</Title>
              <Space size="large">
                <div>
                  <Paragraph type="secondary">舊系統</Paragraph>
                  <Statistic 
                    value={baseline.old_avg_api_calls} 
                    suffix="次"
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </div>
                <div style={{ fontSize: '24px', color: '#52c41a' }}>→</div>
                <div>
                  <Paragraph type="secondary">新系統</Paragraph>
                  <Statistic 
                    value={baseline.new_avg_api_calls} 
                    suffix="次"
                    valueStyle={{ color: '#52c41a' }}
                  />
                </div>
              </Space>
              <Tag color="success" style={{ marginTop: 16, fontSize: '14px' }}>
                減少 {apiReduction}%
              </Tag>
            </div>
          </Col>

          <Col xs={24} md={12}>
            <div style={{ textAlign: 'center', padding: '16px' }}>
              <Title level={4}>成本節省</Title>
              <Progress
                type="circle"
                percent={statistics.cost_metrics.cost_saved_percentage}
                format={percent => (
                  <div>
                    <div style={{ fontSize: '28px', fontWeight: 'bold' }}>{percent}%</div>
                    <div style={{ fontSize: '12px', color: '#8c8c8c' }}>節省</div>
                  </div>
                )}
                strokeColor={{
                  '0%': '#108ee9',
                  '100%': '#87d068',
                }}
                width={150}
              />
            </div>
          </Col>
        </Row>

        <Divider />

        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Statistic
              title="總Token使用"
              value={statistics.cost_metrics.total_tokens}
              suffix="tokens"
              prefix={<ThunderboltOutlined />}
            />
          </Col>
          <Col span={12}>
            <Statistic
              title="成功率"
              value={statistics.success_rate}
              suffix="%"
              precision={1}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: statistics.success_rate > 95 ? '#52c41a' : '#faad14' }}
            />
          </Col>
        </Row>
      </Card>
    );
  };

  // 渲染頂部控制欄
  const renderControls = () => {
    return (
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Text strong>時間範圍:</Text>
          <Select
            value={timeRange}
            onChange={setTimeRange}
            style={{ width: 120 }}
          >
            <Option value="24h">過去24小時</Option>
            <Option value="7d">過去7天</Option>
            <Option value="30d">過去30天</Option>
            <Option value="all">全部</Option>
          </Select>
        </Space>

        <Button
          icon={<ReloadOutlined />}
          onClick={loadStatistics}
          loading={loading}
        >
          刷新數據
        </Button>
      </div>
    );
  };

  if (loading && !statistics) {
    return (
      <div style={{ textAlign: 'center', padding: '60px' }}>
        <Spin size="large" />
        <Paragraph style={{ marginTop: 16 }}>載入統計數據中...</Paragraph>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="載入統計失敗"
        description={error}
        showIcon
        action={
          <Button size="small" onClick={loadStatistics}>
            重試
          </Button>
        }
      />
    );
  }

  if (!statistics || statistics.total_questions === 0) {
    return (
      <Alert
        type="info"
        message="暫無統計數據"
        description="開始使用AI問答功能後,這裡將顯示詳細的性能統計。"
        showIcon
      />
    );
  }

  return (
    <div className="qa-analytics-panel">
      {renderControls()}
      
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 關鍵指標 */}
        {renderKeyMetrics()}

        {/* 性能改善對比 */}
        {renderPerformanceImprovement()}

        {/* 意圖分佈 */}
        {renderIntentDistribution()}

        {/* 說明 */}
        <Alert
          type="success"
          message="智能分層優化已啟用"
          description={
            <div>
              <Paragraph style={{ marginBottom: 8 }}>
                系統已啟用智能問題分類和動態路由,根據問題類型自動選擇最優處理策略。
              </Paragraph>
              <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
                <li>寒暄問候: 直接回答,不查文檔</li>
                <li>簡單查詢: 輕量級搜索,快速回答</li>
                <li>文檔搜索: 標準兩階段檢索</li>
                <li>複雜分析: 完整RAG流程,保持高質量</li>
              </ul>
            </div>
          }
          showIcon
        />
      </Space>
    </div>
  );
};

export default QAAnalyticsPanel;

