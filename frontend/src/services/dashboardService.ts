import { apiClient } from './apiClient';
import type { Stats, Activity, BackendSystemStats, BackendActivityItem, BackendRecentActivities } from '../types/apiTypes';

// --- Dashboard API 函數 ---
export const getDashboardStats = async (): Promise<Stats> => {
  console.log('API: Fetching dashboard stats...');
  try {
    const response = await apiClient.get<BackendSystemStats>('/dashboard/stats');
    console.log('API: Dashboard stats fetched (raw):', response.data);
    // Map BackendSystemStats to frontend's Stats
    const frontendStats: Stats = {
      totalDocs: response.data.total_documents,
      analyzedDocs: response.data.processed_documents,
      activeConnections: response.data.active_connections,
    };
    console.log('API: Dashboard stats mapped:', frontendStats);
    return frontendStats;
  } catch (error) {
    console.error('API: Failed to fetch dashboard stats:', error);
    throw error;
  }
};

export const getRecentActivities = async (): Promise<Activity[]> => {
  console.log('API: Fetching recent activities...');
  try {
    const response = await apiClient.get<BackendRecentActivities>('/dashboard/recent-activities');
    console.log('API: Recent activities fetched (raw):', response.data);

    // Map BackendActivityItem to frontend's Activity
    const mappedActivities: Activity[] = response.data.activities.map(item => {
      // Basic mapping for activity_type to frontend's enum-like type
      let frontendActivityType: Activity['type'] = item.activity_type.toLowerCase();
      if (item.activity_type.includes('upload')) frontendActivityType = 'upload';
      else if (item.activity_type.includes('analysis') || item.activity_type.includes('analyze')) frontendActivityType = 'analysis';
      else if (item.activity_type.includes('query') || item.activity_type.includes('search')) frontendActivityType = 'query';
      else if (item.activity_type.includes('error')) frontendActivityType = 'error';
      else if (item.activity_type.includes('login')) frontendActivityType = 'login';

      const knownTypes: Activity['type'][] = ['upload', 'analysis', 'query', 'error', 'login', 'system'];
      if (!knownTypes.includes(frontendActivityType as any) && !item.activity_type.toLowerCase().includes('log')) {
          frontendActivityType = item.activity_type;
      }

      return {
        id: item.id, // Already a string (UUID)
        timestamp: new Date(item.timestamp).toLocaleString(), // Format datetime
        type: frontendActivityType,
        description: item.summary,
      };
    });
    console.log('API: Recent activities mapped:', mappedActivities);
    return mappedActivities;
  } catch (error) {
    console.error('API: Failed to fetch recent activities:', error);
    throw error;
  }
}; 