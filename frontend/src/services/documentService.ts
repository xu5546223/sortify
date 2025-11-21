import { apiClient } from './apiClient';
import type {
  Document,
  DocumentStatus,
  DocumentUpdateRequest,
  UploadDocumentOptions,
  BasicResponse,
  BatchDeleteDocumentsApiResponse,
  TriggerDocumentProcessingOptions
} from '../types/apiTypes';
import axios from 'axios'; // For isAxiosError check in deleteDocument

/**
 * 通过 ID 获取单个文档
 */
export const getDocumentById = async (documentId: string): Promise<Document | null> => {
  try {
    const response = await apiClient.get<Document>(`/documents/${documentId}`);
    return response.data;
  } catch (error) {
    console.error(`获取文档 ${documentId} 失败:`, error);
    return null;
  }
};

/**
 * 批量获取多个文档（通过 ID 列表）
 */
export const getDocumentsByIds = async (documentIds: string[]): Promise<Document[]> => {
  try {
    // 并行获取所有文档
    const promises = documentIds.map(id => getDocumentById(id));
    const results = await Promise.all(promises);
    // 过滤掉 null 值
    return results.filter((doc): doc is Document => doc !== null);
  } catch (error) {
    console.error('批量获取文档失败:', error);
    return [];
  }
};

export const getDocuments = async (
    searchTerm?: string,
    status?: DocumentStatus | 'all',
    tagsInclude?: string[],
    sortBy?: keyof Document, 
    sortOrder?: 'asc' | 'desc',
    skip: number = 0,
    limit: number = 20,
    clusterId?: string | null
): Promise<{ documents: Document[], totalCount: number }> => {
    console.log(`API: Fetching documents... Search: ${searchTerm}, Status: ${status}, Tags: ${tagsInclude}, SortBy: ${sortBy} ${sortOrder}, Skip: ${skip}, Limit: ${limit}, ClusterId: ${clusterId}`);
    try {
        const params: Record<string, any> = {
            skip: skip,
            limit: limit
        };
        if (searchTerm) {
            params.filename_contains = searchTerm;
        }
        if (status && status !== 'all') {
            params.status_in = [status]; // 后端接受的是数组
        }
        if (tagsInclude && tagsInclude.length > 0) {
            params.tags_include = tagsInclude;
        }
        if (sortBy) {
            params.sort_by = sortBy; 
            if (sortOrder) {
                params.sort_order = sortOrder; 
            }
        }
        // 處理 cluster_id 過濾：
        // - undefined: 不過濾，返回所有文件
        // - null: 過濾未分類文件（cluster_id 為 null）
        // - string: 過濾指定 cluster_id 的文件
        if (clusterId !== undefined) {
            // 當 clusterId 為 null 時，使用字符串 'null' 來明確告訴後端查詢未分類文件
            // axios 會忽略 null 值，所以必須轉換為字符串
            params.cluster_id = clusterId === null ? 'null' : clusterId;
        }

        const response = await apiClient.get<{ items?: Document[], total?: number }>('/documents/', { params });
        console.log('API: Documents fetched (raw response):', response.data);

        if (response.data?.items) {
          response.data.items.forEach((doc, index) => {
            // console.log(`Document ${index} ID:`, doc.id, typeof doc.id); // Optional: for debugging
            if (doc.id === undefined) {
              console.warn(`Warning: Document at index ${index} has an undefined ID. Document data:`, doc);
            }
          });
        }

        return {
            documents: response.data?.items || [],
            totalCount: response.data?.total || 0
        };

    } catch (error) {
        console.error('API: Failed to fetch documents:', error);
        throw error; 
    }
};

export const uploadDocument = async (
  file: File,
  options?: UploadDocumentOptions
): Promise<Document> => {
  console.log(`API: Uploading document: ${file.name}, size: ${file.size}, type: ${file.type}`);
  const formData = new FormData();
  formData.append('file', file);

  if (options?.tags && options.tags.length > 0) {
    options.tags.forEach(tag => {
      formData.append('tags', tag);
    });
  }

  try {
    const response = await apiClient.post<Document>('/documents/', formData);
    console.log('API: Document uploaded successfully:', response.data);
    return response.data; 
  } catch (error) {
    console.error('API: Failed to upload document:', error);
    throw error;
  }
};

export const deleteDocument = async (documentId: string): Promise<BasicResponse> => {
  console.log(`API: Attempting to delete document: ${documentId}`);
  try {
    const response = await apiClient.delete<BasicResponse>(`/documents/${documentId}`);
    if (response.status === 204) {
      return { success: true, message: "Document deleted successfully." };
    }
    return response.data;
  } catch (error) {
    console.error(`API: Failed to delete document ${documentId}:`, error);
    // It's good practice to check if the error is an AxiosError and has a response
    if (axios.isAxiosError(error) && error.response && error.response.data && typeof error.response.data.success === 'boolean') {
      return error.response.data as BasicResponse; // Return the structured error from backend
    }
    throw error; // Otherwise rethrow the original error
  }
};

export const deleteDocuments = async (documentIds: string[]): Promise<BatchDeleteDocumentsApiResponse> => {
  console.log(`API: Attempting to batch delete documents with IDs: ${documentIds.join(', ')}`);
  try {
    const response = await apiClient.post<BatchDeleteDocumentsApiResponse>('/documents/batch-delete', {
      document_ids: documentIds 
    });
    return response.data;
  } catch (error) {
    console.error('API: Failed to batch delete documents:', error);
    throw error;
  }
};

export const triggerDocumentProcessing = async (documentId: string, options?: TriggerDocumentProcessingOptions): Promise<Document> => {
  console.log(`API: Triggering content processing for document ${documentId} with options:`, options);
  try {
    const payload: DocumentUpdateRequest = { 
      trigger_content_processing: true,
      ai_ensure_chinese_output: options?.ai_ensure_chinese_output
    };
    const response = await apiClient.patch<Document>(`/documents/${documentId}`, payload);
    console.log('API: Document processing triggered successfully, updated document:', response.data);
    return response.data;
  } catch (error) {
    console.error(`API: Failed to trigger content processing for document ${documentId}:`, error);
    throw error; // Throw the error instead of returning a custom object
  }
};