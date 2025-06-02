import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  PageHeader,
  Card,
  Select,
  Input,
  Button,
  Table,
  TableRow,
  TableCell
} from '../components';
import { HeaderConfig } from '../components/table/Table';
import type { LogEntry, LogLevel } from '../types/apiTypes';
import { getLogs } from '../services/logService';

interface LogsPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

// 防抖函數
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

// 新增時間格式化函數
const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'Invalid Date';
  
  try {
    // 解析 ISO 8601 時間格式
    const date = new Date(timestamp);
    
    // 檢查日期是否有效
    if (isNaN(date.getTime())) return 'Invalid Date';
    
    // 格式化為 YYYY-MM-DD HH:MM:SS 格式
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Date Error';
  }
};

const LogsPage: React.FC<LogsPageProps> = ({ showPCMessage }) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [filterLevel, setFilterLevel] = useState<LogLevel | 'all'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'timestamp', direction: 'desc' });
  
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  const isMounted = useRef(true);
  const hasLoadedInitialData = useRef(false);

  const fetchLogs = useCallback(async () => {
    if (!isMounted.current) return;
    
    setIsLoading(true);
    try {
      const data = await getLogs(filterLevel, debouncedSearchTerm, sortConfig.key as keyof LogEntry, sortConfig.direction);
      
      if (isMounted.current) {
        setLogs(data);
        hasLoadedInitialData.current = true;
      }
    } catch (error) {
      console.error('Failed to fetch logs:', error);
      if (isMounted.current) {
        showPCMessage('獲取日誌失敗', 'error');
        setLogs([]);
      }
    }
    
    if (isMounted.current) {
      setIsLoading(false);
    }
  }, [filterLevel, debouncedSearchTerm, sortConfig, showPCMessage]);

  useEffect(() => {
    isMounted.current = true;
    fetchLogs();
    return () => {
      isMounted.current = false;
    };
  }, [fetchLogs]);

  const handleSort = useCallback((key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    const validKeys: Array<keyof LogEntry> = ['timestamp', 'level', 'message', 'source'];
    if (validKeys.includes(key as keyof LogEntry)) {
      if (sortConfig.key === key && sortConfig.direction === 'asc') {
        direction = 'desc';
      }
      setSortConfig({ key, direction });
    } else {
      console.warn("Attempted to sort by an invalid key:", key);
    }
  }, [sortConfig]);

  const logLevelOptions: { value: LogLevel | 'all'; label: string }[] = [
    { value: 'all', label: '所有等級' },
    { value: 'info', label: '資訊 (Info)' },
    { value: 'warning', label: '警告 (Warning)' },
    { value: 'error', label: '錯誤 (Error)' },
    { value: 'debug', label: '除錯 (Debug)' },
  ];

  const getLogLevelClass = (level: LogLevel) => {
    switch (level.toLowerCase()) {
      case 'info': return 'bg-blue-100 text-blue-800 border border-blue-200';
      case 'warning': return 'bg-yellow-100 text-yellow-800 border border-yellow-200';
      case 'error': return 'bg-red-100 text-red-800 border border-red-200';
      case 'debug': return 'bg-surface-100 text-surface-800 border border-surface-200';
      default: return 'bg-surface-100 text-surface-800 border border-surface-200';
    }
  };
  
  const tableHeadersForTableComponent: HeaderConfig[] = useMemo(() => [
    { key: 'timestamp', label: '時間戳記', sortable: true, onSort: handleSort, className: 'w-1/5' },
    { key: 'level', label: '等級', sortable: true, onSort: handleSort, className: 'w-1/12' },
    { key: 'message', label: '訊息', sortable: true, onSort: handleSort, className: 'w-3/5' },
    { key: 'source', label: '來源', sortable: true, onSort: handleSort, className: 'w-1/6' },
  ], [handleSort]);

  const tableCellRenderers: Partial<Record<keyof LogEntry, (log: LogEntry) => React.ReactNode>> = useMemo(() => ({
    timestamp: (log: LogEntry) => formatTimestamp(log.timestamp),
    level: (log: LogEntry) => (
      <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${getLogLevelClass(log.level)}`}>
        {log.level.toUpperCase()}
      </span>
    ),
    message: (log: LogEntry) => <span className="break-words whitespace-pre-wrap">{log.message}</span>,
    source: (log: LogEntry) => log.source || 'N/A',
  }), [getLogLevelClass]);

  const handleDownloadLogs = () => {
    if (logs.length === 0) {
      showPCMessage('目前沒有日誌可供下載', 'info');
      return;
    }

    try {
      const headers = '時間戳記\t等級\t訊息\t來源\n';
      
      const txtContent = headers + logs.map(log => {
        const timestamp = formatTimestamp(log.timestamp);
        const level = log.level.toUpperCase();
        const message = log.message || '';
        const source = log.source || 'N/A';
        
        return `${timestamp}\t${level}\t${message}\t${source}`;
      }).join('\n');

      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      
      const date = new Date().toISOString().split('T')[0];
      link.setAttribute('href', url);
      link.setAttribute('download', `sortify_logs_${date}.txt`);
      
      document.body.appendChild(link);
      link.click();
      
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      showPCMessage('日誌下載成功', 'success');
    } catch (error) {
      console.error('下載日誌時發生錯誤:', error);
      showPCMessage('下載日誌時發生錯誤', 'error');
    }
  };

  const refreshLogs = () => {
    fetchLogs();
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <PageHeader title="系統日誌" />
      
      <div className="mb-4 text-gray-600">
        查看系統操作和錯誤日誌
      </div>
      
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap gap-4">
          <Select
            label="日誌級別"
            value={filterLevel}
            onChange={(e) => setFilterLevel(e.target.value as LogLevel | 'all')}
            options={logLevelOptions}
            className="w-48"
          />
          
          <div className="relative">
            <Input
              type="text"
              placeholder="搜尋日誌..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 w-64"
            />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <i className="fas fa-search text-gray-400"></i>
            </div>
          </div>
        </div>
        
        <div className="flex gap-2">
          <Button onClick={refreshLogs} variant="secondary">
            <i className="fas fa-sync-alt mr-2"></i>刷新
          </Button>
          <Button onClick={handleDownloadLogs} variant="primary">
            <i className="fas fa-download mr-2"></i>下載日誌
          </Button>
        </div>
      </div>
      
      <Card className="shadow-lg rounded-lg overflow-hidden">
        {isLoading && logs.length === 0 && !hasLoadedInitialData.current ? (
          <div className="p-6 text-center text-gray-500">
            <i className="fas fa-spinner fa-spin text-2xl mb-2"></i>
            <p>正在載入日誌...</p>
          </div>
        ) : (
          <Table 
            headers={tableHeadersForTableComponent}
            sortConfig={sortConfig}
            className="min-w-full"
            headerClassName="bg-slate-50"
            thClassName="py-3.5"
          >
            {logs.length > 0 ? (
              logs.map((log) => (
                <TableRow key={log.id} className="hover:bg-surface-100">
                  {tableHeadersForTableComponent.map(header => {
                    const cellRenderer = tableCellRenderers[header.key as keyof LogEntry];
                    return (
                      <TableCell key={`${header.key}-${log.id}`} className={header.className}>
                        {cellRenderer
                          ? cellRenderer(log)
                          : (log[header.key as keyof LogEntry] as React.ReactNode || 'N/A')}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={tableHeadersForTableComponent.length} className="text-center py-10 text-gray-500">
                  {isLoading ? '正在載入...' : (hasLoadedInitialData.current && logs.length === 0) ? '找不到符合條件的日誌。' : '目前沒有日誌記錄。'}
                </TableCell>
              </TableRow>
            )}
          </Table>
        )}
      </Card>
    </div>
  );
};

export default LogsPage; 