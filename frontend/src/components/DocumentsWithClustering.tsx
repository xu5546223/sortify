/**
 * 統計與資料夾面板組件（左側第二欄）
 * 顯示文件統計、AI 分類資料夾樹
 * 
 * 注意：此組件需要安裝以下依賴：
 * npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
 */

import React, { useState, useEffect, useMemo } from 'react';
import { 
  getClustersTree, 
  getFolderDisplayOrder, 
  saveFolderDisplayOrder 
} from '../services/clusteringService';
import { ClusterSummary } from '../types/apiTypes';

// @dnd-kit imports
import { 
  DndContext, 
  closestCenter, 
  KeyboardSensor, 
  PointerSensor, 
  useSensor, 
  useSensors,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  useDroppable,
  DragOverEvent
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface ClusterTreeData {
  main_clusters: ClusterSummary[];
  small_clusters: ClusterSummary[];
  unclustered_count: number;
  total_clusters: number;
}

interface DocumentsWithClusteringProps {
  // 從父組件傳遞的過濾函數
  onClusterFilterChange: (clusterId: string | null, folderName?: string) => void;
  currentClusterId: string | null | undefined;
  // 刷新文檔列表的回調
  onRefreshDocuments: () => void;
}

// 分頁按鈕組件（可作為拖拽目標）
interface PaginationButtonsProps {
  currentPage: number;
  totalPages: number;
  isDraggingOverPrev: boolean;
  isDraggingOverNext: boolean;
  onPrevClick: () => void;
  onNextClick: () => void;
}

const PaginationButtons: React.FC<PaginationButtonsProps> = ({
  currentPage,
  totalPages,
  isDraggingOverPrev,
  isDraggingOverNext,
  onPrevClick,
  onNextClick
}) => {
  const { setNodeRef: setPrevRef } = useDroppable({
    id: 'prev-page-button',
  });

  const { setNodeRef: setNextRef } = useDroppable({
    id: 'next-page-button',
  });

  return (
    <div className="flex gap-1 mt-3">
      <button
        ref={setPrevRef}
        onClick={onPrevClick}
        disabled={currentPage === 1}
        className={`flex-1 py-1.5 text-xs font-bold border-2 border-neo-black transition-all disabled:opacity-30 disabled:cursor-not-allowed ${
          isDraggingOverPrev 
            ? 'bg-neo-primary text-white scale-105 shadow-lg' 
            : 'hover:bg-gray-100'
        }`}
      >
        {isDraggingOverPrev ? '↑ 翻頁...' : '←'}
      </button>
      <button
        ref={setNextRef}
        onClick={onNextClick}
        disabled={currentPage === totalPages}
        className={`flex-1 py-1.5 text-xs font-bold border-2 border-neo-black transition-all disabled:opacity-30 disabled:cursor-not-allowed ${
          isDraggingOverNext 
            ? 'bg-neo-primary text-white scale-105 shadow-lg' 
            : 'hover:bg-gray-100'
        }`}
      >
        {isDraggingOverNext ? '↓ 翻頁...' : '→'}
      </button>
    </div>
  );
};

// 可拖拽的資料夾項目組件
interface SortableFolderItemProps {
  cluster: ClusterSummary;
  isSelected: boolean;
  isMainCluster: boolean;
  onClick: () => void;
}

const SortableFolderItem: React.FC<SortableFolderItemProps> = ({
  cluster,
  isSelected,
  isMainCluster,
  onClick
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: cluster.cluster_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <button
      ref={setNodeRef}
      style={style}
      onClick={onClick}
      className={`w-full flex items-center justify-between p-2 hover:bg-gray-100 rounded cursor-move text-sm border-2 transition-all ${
        isSelected
          ? 'border-neo-black bg-neo-hover bg-opacity-20 text-neo-black font-bold'
          : 'border-transparent hover:border-neo-black text-neo-black'
      } ${isMainCluster ? 'font-bold' : ''} ${isDragging ? 'z-50' : ''}`}
    >
      <div className="flex items-center gap-2 flex-1">
        <span 
          {...attributes} 
          {...listeners}
          className="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 flex-shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          ⋮⋮
        </span>
        <span className="text-neo-active text-base flex-shrink-0">■</span>
        <span className="truncate">{cluster.cluster_name}</span>
      </div>
      <span className="text-xs bg-gray-200 px-1.5 rounded flex-shrink-0">
        {cluster.document_count}
      </span>
    </button>
  );
};

const DocumentsWithClustering: React.FC<DocumentsWithClusteringProps> = ({
  onClusterFilterChange,
  currentClusterId,
  onRefreshDocuments
}) => {
  const [treeData, setTreeData] = useState<ClusterTreeData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [customOrder, setCustomOrder] = useState<string[]>([]);
  const [isSavingOrder, setIsSavingOrder] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isDraggingOverPrev, setIsDraggingOverPrev] = useState(false);
  const [isDraggingOverNext, setIsDraggingOverNext] = useState(false);
  const itemsPerPage = 18;

  // 配置拖拽傳感器
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 拖動 8px 後才觸發
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // 獲取聚類樹
  const fetchClustersTree = async () => {
    setIsLoading(true);
    try {
      const data = await getClustersTree();
      setTreeData(data);
    } catch (err) {
      console.error('獲取聚類樹失敗:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // 獲取自定義排序
  const fetchCustomOrder = async () => {
    try {
      const order = await getFolderDisplayOrder();
      setCustomOrder(order);
      console.log('已載入自定義資料夾排序:', order.length, '個資料夾');
    } catch (err) {
      console.error('獲取資料夾排序失敗:', err);
    }
  };

  useEffect(() => {
    fetchClustersTree();
    fetchCustomOrder();
  }, []);

  // 應用自定義排序的資料夾列表
  const sortedClusters = useMemo(() => {
    if (!treeData) return [];
    
    const allClusters = [...treeData.main_clusters, ...treeData.small_clusters];
    
    if (customOrder.length === 0) {
      // 沒有自定義排序，使用原始順序
      return allClusters;
    }
    
    // 根據自定義排序重新排列
    const ordered: ClusterSummary[] = [];
    const unordered: ClusterSummary[] = [];
    
    customOrder.forEach(id => {
      const cluster = allClusters.find(c => c.cluster_id === id);
      if (cluster) ordered.push(cluster);
    });
    
    // 添加不在自定義排序中的新資料夾
    allClusters.forEach(cluster => {
      if (!customOrder.includes(cluster.cluster_id)) {
        unordered.push(cluster);
      }
    });
    
    return [...ordered, ...unordered];
  }, [treeData, customOrder]);

  // 處理拖拽開始
  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  // 處理拖拽經過
  const handleDragOver = (event: DragOverEvent) => {
    const overId = event.over?.id;
    
    if (overId === 'prev-page-button') {
      setIsDraggingOverPrev(true);
      setIsDraggingOverNext(false);
    } else if (overId === 'next-page-button') {
      setIsDraggingOverNext(true);
      setIsDraggingOverPrev(false);
    } else {
      setIsDraggingOverPrev(false);
      setIsDraggingOverNext(false);
    }
  };

  // 處理拖拽結束
  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    
    setActiveId(null);
    setIsDraggingOverPrev(false);
    setIsDraggingOverNext(false);
    
    if (!over || active.id === over.id) return;
    
    const oldIndex = sortedClusters.findIndex(c => c.cluster_id === active.id);
    const newIndex = sortedClusters.findIndex(c => c.cluster_id === over.id);
    
    if (oldIndex === -1 || newIndex === -1) return;
    
    // 更新本地順序
    const newOrder = arrayMove(sortedClusters, oldIndex, newIndex);
    const newOrderIds = newOrder.map(c => c.cluster_id);
    setCustomOrder(newOrderIds);
    
    // 保存到後端
    try {
      setIsSavingOrder(true);
      await saveFolderDisplayOrder(newOrderIds);
      console.log('✅ 資料夾排序已保存');
    } catch (err) {
      console.error('❌ 保存資料夾排序失敗:', err);
      // 恢復原始順序
      fetchCustomOrder();
    } finally {
      setIsSavingOrder(false);
    }
  };

  // 拖拽到上一頁按鈕時翻頁
  useEffect(() => {
    if (!isDraggingOverPrev || currentPage <= 1) return;
    
    const timer = setTimeout(() => {
      setCurrentPage(p => Math.max(1, p - 1));
      setIsDraggingOverPrev(false);
    }, 500); // 500ms 延遲
    
    return () => clearTimeout(timer);
  }, [isDraggingOverPrev, currentPage]);

  // 拖拽到下一頁按鈕時翻頁
  useEffect(() => {
    if (!isDraggingOverNext) return;
    
    const totalPages = Math.ceil(sortedClusters.length / itemsPerPage);
    if (currentPage >= totalPages) return;
    
    const timer = setTimeout(() => {
      setCurrentPage(p => Math.min(totalPages, p + 1));
      setIsDraggingOverNext(false);
    }, 500); // 500ms 延遲
    
    return () => clearTimeout(timer);
  }, [isDraggingOverNext, currentPage, sortedClusters.length, itemsPerPage]);

  // 計算統計數據
  const totalFiles = treeData
    ? treeData.main_clusters.reduce((sum, c) => sum + c.document_count, 0) +
      treeData.small_clusters.reduce((sum, c) => sum + c.document_count, 0) +
      treeData.unclustered_count
    : 0;

  const categorizedCount = treeData
    ? treeData.main_clusters.reduce((sum, c) => sum + c.document_count, 0) +
      treeData.small_clusters.reduce((sum, c) => sum + c.document_count, 0)
    : 0;

  const categorizedPercentage = totalFiles > 0 ? Math.round((categorizedCount / totalFiles) * 100) : 0;

  return (
    <aside className="w-[280px] bg-neo-white border-r-3 border-neo-black flex flex-col shrink-0 z-20 relative">
      {/* 統計概覽 */}
      <div className="p-5 border-b-3 border-neo-black bg-gray-50">
        <h2 className="font-display font-bold text-lg uppercase mb-3 tracking-tight">Statistics</h2>
        <div className="flex justify-between items-end mb-2">
          <span className="text-xs font-bold text-gray-500 uppercase">Total Files</span>
          <span className="font-display font-bold text-xl text-neo-black">{totalFiles}</span>
        </div>
        <div className="w-full bg-gray-200 h-2 border border-neo-black rounded-full overflow-hidden">
          <div
            className="bg-neo-primary h-full transition-all duration-300"
            style={{ width: `${categorizedPercentage}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] font-bold mt-1">
          <span className="text-neo-primary">{categorizedCount} CATEGORIZED</span>
          <span className="text-neo-warn">{treeData?.unclustered_count || 0} 未分類</span>
        </div>
      </div>

      {/* 資料夾樹 */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* 特別區塊：未分類 (Inbox) */}
        {treeData && treeData.unclustered_count > 0 && (
          <div className="mb-6">
            <div className="text-xs font-bold text-gray-400 uppercase mb-2">Inbox</div>
            <button
              onClick={() => onClusterFilterChange(null, 'Uncategorized')}
              className={`w-full flex items-center justify-between p-3 bg-neo-warn border-2 border-neo-black shadow-[3px_3px_0px_black] cursor-pointer hover:translate-x-1 transition-transform ${
                currentClusterId === null ? 'ring-2 ring-neo-black' : ''
              }`}
            >
              <div className="flex items-center gap-2 font-bold text-neo-black">
                <span>📥</span>
                <span>Uncategorized</span>
              </div>
              <span className="bg-neo-black text-neo-white text-xs px-1.5 rounded border border-white">
                {treeData.unclustered_count}
              </span>
            </button>
          </div>
        )}

        {/* 一般資料夾 */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-3 border-neo-black border-t-transparent"></div>
          </div>
        ) : (
          <>
            {treeData && sortedClusters.length > 0 && (() => {
              const totalPages = Math.ceil(sortedClusters.length / itemsPerPage);
              const startIndex = (currentPage - 1) * itemsPerPage;
              const endIndex = startIndex + itemsPerPage;
              const currentClusters = sortedClusters.slice(startIndex, endIndex);

              return (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-bold text-gray-400 uppercase">
                      Folders ({sortedClusters.length})
                    </div>
                    <div className="flex items-center gap-2">
                      {isSavingOrder && (
                        <div className="animate-spin rounded-full h-3 w-3 border-2 border-neo-black border-t-transparent"></div>
                      )}
                      {totalPages > 1 && (
                        <div className="text-xs font-bold text-gray-500">
                          {currentPage}/{totalPages}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* 使用 DndContext 包裹整個區域（列表 + 按鈕） */}
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragStart={handleDragStart}
                    onDragOver={handleDragOver}
                    onDragEnd={handleDragEnd}
                  >
                    <SortableContext
                      items={sortedClusters.map(c => c.cluster_id)}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="space-y-1">
                        {currentClusters.map((cluster) => {
                          const isMainCluster = treeData.main_clusters.some(c => c.cluster_id === cluster.cluster_id);
                          return (
                            <SortableFolderItem
                              key={cluster.cluster_id}
                              cluster={cluster}
                              isSelected={currentClusterId === cluster.cluster_id}
                              isMainCluster={isMainCluster}
                              onClick={() => onClusterFilterChange(cluster.cluster_id, cluster.cluster_name)}
                            />
                          );
                        })}
                      </div>
                    </SortableContext>
                    
                    {/* 拖拽預覽層 */}
                    <DragOverlay>
                      {activeId ? (() => {
                        const activeCluster = sortedClusters.find(c => c.cluster_id === activeId);
                        if (!activeCluster) return null;
                        const isMainCluster = treeData.main_clusters.some(c => c.cluster_id === activeId);
                        return (
                          <div className={`w-full flex items-center justify-between p-2 bg-white rounded text-sm border-2 border-neo-black shadow-lg ${isMainCluster ? 'font-bold' : ''}`}>
                            <div className="flex items-center gap-2 flex-1">
                              <span className="text-gray-400">⋮⋮</span>
                              <span className="text-neo-active text-base">■</span>
                              <span className="truncate">{activeCluster.cluster_name}</span>
                            </div>
                            <span className="text-xs bg-gray-200 px-1.5 rounded">
                              {activeCluster.document_count}
                            </span>
                          </div>
                        );
                      })() : null}
                    </DragOverlay>

                    {/* 分頁按鈕 - 必須在 DndContext 內部 */}
                    {totalPages > 1 && (
                      <PaginationButtons
                        currentPage={currentPage}
                        totalPages={totalPages}
                        isDraggingOverPrev={isDraggingOverPrev}
                        isDraggingOverNext={isDraggingOverNext}
                        onPrevClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        onNextClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                      />
                    )}
                  </DndContext>
                </div>
              );
            })()}
          </>
        )}
      </div>
    </aside>
  );
};

export default DocumentsWithClustering;

