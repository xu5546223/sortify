/**
 * 流式問答服務
 * 
 * 對接後端流式 API，實現實時答案顯示
 */

export interface StreamQARequest {
  question: string;
  conversation_id?: string;
  session_id?: string;
  model_preference?: string;
  context_limit?: number;
  use_semantic_search?: boolean;
  use_structured_filter?: boolean;
  workflow_action?: 'approve_search' | 'skip_search' | 'approve_detail_query' | 'skip_detail_query' | 'provide_clarification';
  clarification_text?: string;
}

export interface StreamChunk {
  type: 'chunk' | 'complete' | 'approval_needed' | 'metadata' | 'error' | 'progress';
  text?: string;
  answer?: string;
  workflow_state?: any;
  tokens_used?: number;
  source_documents?: string[];
  processing_time?: number;
  message?: string;
  stage?: string;
  detail?: any; // 詳細信息（如推理內容、重寫查詢等）
}

export interface StreamCallbacks {
  onChunk?: (text: string) => void;
  onComplete?: (fullText: string) => void;
  onApprovalNeeded?: (workflowState: any) => void;
  onMetadata?: (metadata: { tokens_used?: number; source_documents?: string[]; processing_time?: number }) => void;
  onProgress?: (stage: string, message: string, detail?: any) => void;
  onError?: (error: string) => void;
}

/**
 * 流式問答 API 調用
 */
export async function streamQA(
  request: StreamQARequest,
  callbacks: StreamCallbacks
): Promise<void> {
  // 支援電腦端的 authToken 和手機端的 device_token
  const authToken = localStorage.getItem('authToken');
  const deviceToken = localStorage.getItem('sortify_device_token');
  const token = authToken || deviceToken;
  
  if (!token) {
    callbacks.onError?.('未登錄，請先登錄');
    return;
  }

  let fullText = '';

  try {
    const response = await fetch(`${process.env.REACT_APP_API_BASE_URL || ''}/api/v1/qa/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('無法獲取響應流');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        console.log('📥 流式傳輸完成');
        break;
      }

      // 解碼數據塊
      buffer += decoder.decode(value, { stream: true });

      // 處理完整的 SSE 消息
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留不完整的行

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6); // 移除 "data: " 前綴

          if (data === '[DONE]') {
            console.log('✅ 收到完成信號');
            callbacks.onComplete?.(fullText);
            continue;
          }

          try {
            const chunk: StreamChunk = JSON.parse(data);

            switch (chunk.type) {
              case 'chunk':
                if (chunk.text) {
                  fullText += chunk.text;
                  callbacks.onChunk?.(chunk.text);
                }
                break;

              case 'complete':
                if (chunk.answer) {
                  fullText = chunk.answer;
                  callbacks.onChunk?.(chunk.answer);
                  callbacks.onComplete?.(chunk.answer);
                }
                break;

              case 'approval_needed':
                console.log('🔔 [SSE] 收到 approval_needed 事件:', chunk);
                console.log('📋 workflow_state:', chunk.workflow_state);
                callbacks.onApprovalNeeded?.(chunk.workflow_state);
                break;

              case 'metadata':
                callbacks.onMetadata?.({
                  tokens_used: chunk.tokens_used,
                  source_documents: chunk.source_documents,
                  processing_time: chunk.processing_time,
                });
                break;

              case 'progress':
                console.log('📊 [SSE] 收到進度事件:', chunk);
                callbacks.onProgress?.(chunk.stage || '', chunk.message || '', chunk.detail);
                break;

              case 'error':
                callbacks.onError?.(chunk.message || '發生錯誤');
                break;
            }
          } catch (parseError) {
            console.error('解析 SSE 數據失敗:', parseError, 'Data:', data);
          }
        }
      }
    }
  } catch (error) {
    console.error('流式問答失敗:', error);
    callbacks.onError?.(error instanceof Error ? error.message : '未知錯誤');
  }
}

/**
 * 非流式問答 API（備用，用於不支持流式的情況）
 */
export async function nonStreamQA(request: StreamQARequest): Promise<any> {
  // 支援電腦端的 authToken 和手機端的 device_token
  const authToken = localStorage.getItem('authToken');
  const deviceToken = localStorage.getItem('sortify_device_token');
  const token = authToken || deviceToken;
  
  if (!token) {
    throw new Error('未登錄，請先登錄');
  }

  const response = await fetch(`${process.env.REACT_APP_API_BASE_URL || ''}/api/v1/unified-ai/qa`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}`);
  }

  return await response.json();
}

