import React, { useState, useEffect } from 'react';
import { Card, Button, Alert, Descriptions, Badge, Radio, Space, Divider, Typography, Row, Col } from 'antd';
import { 
  ThunderboltOutlined, 
  DesktopOutlined, 
  PlayCircleOutlined,
  SettingOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import type { EmbeddingModelConfig } from '../types/apiTypes';
import {
  getEmbeddingModelConfig,
  loadEmbeddingModel,
  configureEmbeddingModel
} from '../services/embeddingService';

const { Title, Text, Paragraph } = Typography;

interface ModelConfigCardProps {
  onModelStateChange?: () => void;
}

const ModelConfigCard: React.FC<ModelConfigCardProps> = ({ onModelStateChange }) => {
  const [config, setConfig] = useState<EmbeddingModelConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [modelLoading, setModelLoading] = useState(false);
  const [configuring, setConfiguring] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<string>('auto');

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const configData = await getEmbeddingModelConfig();
      setConfig(configData);
      setSelectedDevice(configData.current_device || 'auto');
    } catch (error) {
      console.error('獲取模型配置失敗:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleLoadModel = async () => {
    try {
      setModelLoading(true);
      await loadEmbeddingModel();
      await fetchConfig();
      onModelStateChange?.();
    } catch (error) {
      console.error('加載模型失敗:', error);
    } finally {
      setModelLoading(false);
    }
  };

  const handleConfigureDevice = async () => {
    try {
      setConfiguring(true);
      await configureEmbeddingModel(selectedDevice as 'cpu' | 'cuda' | 'auto');
      await fetchConfig();
    } catch (error) {
      console.error('配置設備失敗:', error);
    } finally {
      setConfiguring(false);
    }
  };

  if (loading) {
    return (
      <Card title="模型配置" loading={true}>
        <div style={{ height: 200 }} />
      </Card>
    );
  }

  if (!config) {
    return (
      <Card title="模型配置">
        <Alert message="無法加載模型配置信息" type="error" className="ai-qa-alert" />
      </Card>
    );
  }

  const getDeviceIcon = (device: string) => {
    switch (device) {
      case 'cuda':
        return <ThunderboltOutlined style={{ color: '#52c41a' }} />;
      case 'cpu':
        return <DesktopOutlined style={{ color: '#1890ff' }} />;
      default:
        return <SettingOutlined />;
    }
  };

  const getDeviceLabel = (device: string) => {
    switch (device) {
      case 'cuda':
        return 'GPU 加速';
      case 'cpu':
        return 'CPU 運算';
      default:
        return '自動選擇';
    }
  };

  return (
    <Card
      title={
        <Space>
          <SettingOutlined />
          Embedding 模型配置
        </Space>
      }
      extra={
        config.model_loaded ? (
          <Badge status="success" text="已就緒" />
        ) : (
          <Badge status="warning" text="未加載" />
        )
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        {/* 當前狀態 */}
        <div>
          <Title level={5}>
            <InfoCircleOutlined /> 當前狀態
          </Title>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="模型">
              <Text code>{config.current_model}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="加載狀態">
              {config.model_loaded ? (
                <Badge status="success" text="已加載" />
              ) : (
                <Badge status="default" text="未加載" />
              )}
            </Descriptions.Item>
            <Descriptions.Item label="當前設備">
              <Space>
                {getDeviceIcon(config.current_device)}
                {getDeviceLabel(config.current_device)}
                <Text type="secondary">({config.current_device})</Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        </div>

        <Divider />

        {/* 硬體信息 */}
        {config.gpu_info && (
          <div>
            <Title level={5}>
              <ThunderboltOutlined /> GPU 信息
            </Title>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="顯卡型號">
                {config.gpu_info.device_name}
              </Descriptions.Item>
              <Descriptions.Item label="顯存容量">
                {config.gpu_info.memory_total}
              </Descriptions.Item>
              <Descriptions.Item label="PyTorch 版本">
                {config.gpu_info.pytorch_version}
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}

        <Divider />

        {/* 設備選擇 */}
        <div>
          <Title level={5}>設備偏好設置</Title>
          <Paragraph type="secondary" style={{ fontSize: 12 }}>
            選擇 Embedding 模型運行的計算設備。GPU 加速性能更好，CPU 兼容性更強。
          </Paragraph>
          <Radio.Group
            value={selectedDevice}
            onChange={(e) => setSelectedDevice(e.target.value)}
            style={{ width: '100%' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Radio value="auto" disabled={configuring}>
                <Space>
                  <SettingOutlined />
                  自動選擇
                  <Text type="secondary">(系統自動選擇最佳設備)</Text>
                </Space>
              </Radio>
              {config.available_devices.includes('cuda') && (
                <Radio value="cuda" disabled={configuring}>
                  <Space>
                    <ThunderboltOutlined style={{ color: '#52c41a' }} />
                    GPU 加速 (CUDA)
                    <Text type="secondary">(推薦，性能最佳)</Text>
                  </Space>
                </Radio>
              )}
              <Radio value="cpu" disabled={configuring}>
                <Space>
                  <DesktopOutlined style={{ color: '#1890ff' }} />
                  CPU 運算
                  <Text type="secondary">(兼容性最佳，速度較慢)</Text>
                </Space>
              </Radio>
            </Space>
          </Radio.Group>
        </div>

        <Divider />

        {/* 操作按鈕 */}
        <Row gutter={16}>
          <Col span={12}>
            <Button
              type="primary"
              icon={modelLoading ? <LoadingOutlined /> : <PlayCircleOutlined />}
              onClick={handleLoadModel}
              loading={modelLoading}
              disabled={config.model_loaded}
              block
            >
              {config.model_loaded ? '模型已加載' : '加載模型'}
            </Button>
          </Col>
          <Col span={12}>
            <Button
              icon={configuring ? <LoadingOutlined /> : <CheckCircleOutlined />}
              onClick={handleConfigureDevice}
              loading={configuring}
              disabled={selectedDevice === config.current_device}
              block
            >
              應用設備配置
            </Button>
          </Col>
        </Row>

        {/* 建議提示 */}
        {!config.model_loaded && (
          <Alert
            message="建議預先加載模型"
            description="首次使用向量搜索或 AI 問答功能時，模型加載可能需要幾秒鐘時間。建議預先加載模型以獲得最佳用戶體驗。"
            type="info"
            showIcon
            className="ai-qa-alert"
          />
        )}

        {config.gpu_info && config.current_device === 'cpu' && (
          <Alert
            message="GPU 加速可用"
            description={`檢測到 ${config.gpu_info.device_name}，切換到 GPU 模式可以顯著提升性能。`}
            type="warning"
            showIcon
            className="ai-qa-alert"
          />
        )}
      </Space>
    </Card>
  );
};

export default ModelConfigCard; 