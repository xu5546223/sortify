import { apiClient } from './apiClient';
import type { LogEntry, LogLevel, BackendLogEntry } from '../types/apiTypes';

export const getLogs = async (
    filterLevel?: LogLevel | 'all', 
    searchTerm?: string, 
    sortBy: keyof LogEntry = 'timestamp', // Note: sortBy is LogEntry, not BackendLogEntry for now
    sortOrder: 'asc' | 'desc' = 'desc' 
): Promise<LogEntry[]> => {
    try {
        const params: Record<string, string> = {}; // Make params explicitly Record<string, string>
        
        if (filterLevel && filterLevel !== 'all') {
            params.level = filterLevel;
        }
        
        if (searchTerm && searchTerm.trim()) {
            params.message_contains = searchTerm.trim();
        }
        // sortBy and sortOrder are not directly passed as query params in the original code for /logs/
        // If they need to be, this is where they'd be added to `params`.
        // For now, the backend handles sorting internally or doesn't support it for this endpoint.

        const response = await apiClient.get<{ items: BackendLogEntry[], total: number }>('/logs/', { params });
        // Assuming the backend returns an object like { items: [], total: 0 }
        // If it's just an array, then: const response = await apiClient.get<BackendLogEntry[]>('/logs/', { params });
        // And then map response.data directly.

        // Based on original code, backend /logs/ directly returns an array of log entries.
        // So, the direct response.data should be BackendLogEntry[]
        const backendLogs: BackendLogEntry[] = response.data as any; // Cast if apiClient.get doesn't match direct array
                                                                   // Or ensure apiClient.get is <BackendLogEntry[]>

        return backendLogs.map((log: BackendLogEntry) => ({
            id: log.id,
            timestamp: log.timestamp, // Consider formatting here if needed globally for LogEntry
            level: log.level,
            message: log.message,
            source: log.source || undefined, // Ensure undefined if null/empty for consistency
        }));
    } catch (error) {
        console.error('獲取日誌失敗:', error);
        throw error;
    }
}; 