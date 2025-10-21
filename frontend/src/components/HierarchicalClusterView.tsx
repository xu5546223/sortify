/**
 * 階層聚類視圖組件
 * 以樹狀結構展示兩級聚類結果
 * 
 * 示例:
 * 📁 超商類 (35個文檔)
 *   ├─ 📄 7-11收據 (15個)
 *   ├─ 📄 全家收據 (12個)
 *   └─ 📄 萊爾富收據 (8個)
 * 📁 帳單類 (28個文檔)
 *   ├─ 📄 水費帳單 (10個)
 *   ├─ 📄 電費帳單 (10個)
 *   └─ 📄 稅費單據 (8個)
 */

import React, { useState, useEffect } from 'react';
import {
  Tree,
  Card,
  Space,
  Tag,
  Typography,
  Spin,
  Empty,
  Button,
  message,
  Tooltip,
  Badge
} from 'antd';
import {
  FolderOutlined,
  FileTextOutlined,
  ReloadOutlined,
  DownOutlined,
  TagsOutlined
} from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { ClusterSummary } from '../types/apiTypes';
import { getUserClusters, triggerHierarchicalClustering } from '../services/clusteringService';

const { Title, Text } = Typography;

interface HierarchicalClusterViewProps {
  onClusterSelect?: (clusterId: string, clusterName: string) => void;
}

const HierarchicalClusterView: React.FC<HierarchicalClusterViewProps> = ({
  onClusterSelect
}) => {
  const [loading, setLoading] = useState(false);
  const [clusters, setClusters] = useState<ClusterSummary[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [triggeringClustering, setTriggeringClustering] = useState(false);

  // 加載聚類數據
  const loadClusters = async () => {
    setLoading(true);
    try {
      // 只獲取Level 0的大類,並包含子聚類信息
      const data = await getUserClusters(0, true);
      setClusters(data);
      
      // 默認展開所有大類
      const keys = data.map(c => c.cluster_id);
      setExpandedKeys(keys);
    } catch (error: any) {
      console.error('加載聚類數據失敗:', error);
      message.error(error.response?.data?.detail || '加載聚類數據失敗');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadClusters();
  }, []);

  // 觸發階層聚類
  const handleTriggerClustering = async () => {
    setTriggeringClustering(true);
    try {
      await triggerHierarchicalClustering(false);
      message.success('階層聚類任務已觸發,請稍後刷新查看結果');
      
      // 3秒後自動刷新
      setTimeout(() => {
        loadClusters();
      }, 3000);
    } catch (error: any) {
      console.error('觸發聚類失敗:', error);
      message.error(error.response?.data?.detail || '觸發聚類失敗');
    } finally {
      setTriggeringClustering(false);
    }
  };

  // 將ClusterSummary轉換為Tree的DataNode
  const buildTreeData = (clusters: ClusterSummary[]): DataNode[] => {
    return clusters.map(cluster => {
      const node: DataNode = {
        title: (
          <Space>
            <Text strong>{cluster.cluster_name}</Text>
            <Badge count={cluster.document_count} style={{ backgroundColor: '#52c41a' }} />
            {cluster.keywords && cluster.keywords.length > 0 && (
              <Tooltip title={cluster.keywords.join(', ')}>
                <TagsOutlined style={{ color: '#1890ff', cursor: 'help' }} />
              </Tooltip>
            )}
          </Space>
        ),
        key: cluster.cluster_id,
        icon: <FolderOutlined style={{ color: '#faad14' }} />,
        children: cluster.subcluster_summaries && cluster.subcluster_summaries.length > 0
          ? cluster.subcluster_summaries.map(subcluster => ({
              title: (
                <Space>
                  <Text>{subcluster.cluster_name}</Text>
                  <Badge count={subcluster.document_count} style={{ backgroundColor: '#1890ff' }} />
                  {subcluster.keywords && subcluster.keywords.length > 0 && (
                    <div>
                      {subcluster.keywords.slice(0, 3).map(keyword => (
                        <Tag key={keyword} style={{ fontSize: '11px', marginLeft: 4 }}>
                          {keyword}
                        </Tag>
                      ))}
                    </div>
                  )}
                </Space>
              ),
              key: subcluster.cluster_id,
              icon: <FileTextOutlined style={{ color: '#1890ff' }} />,
              isLeaf: true,
            }))
          : undefined,
      };
      return node;
    });
  };

  const treeData = buildTreeData(clusters);

  // 樹節點選擇
  const handleSelect = (selectedKeys: React.Key[], info: any) => {
    setSelectedKeys(selectedKeys);
    
    if (selectedKeys.length > 0 && onClusterSelect) {
      const clusterId = selectedKeys[0] as string;
      const node = info.node;
      onClusterSelect(clusterId, node.title);
    }
  };

  // 計算統計信息
  const totalClusters = clusters.length;
  const totalSubclusters = clusters.reduce(
    (sum, c) => sum + (c.subcluster_summaries?.length || 0),
    0
  );
  const totalDocuments = clusters.reduce((sum, c) => sum + c.document_count, 0);

  return (
    <Card
      title={
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            階層分類
          </Title>
          <Tag color="blue">{totalClusters} 大類</Tag>
          <Tag color="cyan">{totalSubclusters} 子類</Tag>
          <Tag color="green">{totalDocuments} 文檔</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadClusters}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            type="primary"
            onClick={handleTriggerClustering}
            loading={triggeringClustering}
          >
            觸發階層聚類
          </Button>
        </Space>
      }
      style={{ height: '100%' }}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" tip="加載中..." />
        </div>
      )}

      {!loading && clusters.length === 0 && (
        <Empty
          description="尚無聚類數據,請先觸發階層聚類"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button type="primary" onClick={handleTriggerClustering}>
            觸發階層聚類
          </Button>
        </Empty>
      )}

      {!loading && clusters.length > 0 && (
        <div style={{ overflow: 'auto', maxHeight: 'calc(100vh - 300px)' }}>
          <Tree
            showIcon
            defaultExpandAll
            expandedKeys={expandedKeys}
            selectedKeys={selectedKeys}
            onExpand={(keys) => setExpandedKeys(keys)}
            onSelect={handleSelect}
            treeData={treeData}
            switcherIcon={<DownOutlined />}
          />
        </div>
      )}

      {!loading && clusters.length > 0 && (
        <div style={{ marginTop: 16, padding: 12, background: '#f0f2f5', borderRadius: 4 }}>
          <Text type="secondary">
            💡 點擊聚類名稱可查看該聚類下的所有文檔
          </Text>
        </div>
      )}
    </Card>
  );
};

export default HierarchicalClusterView;

