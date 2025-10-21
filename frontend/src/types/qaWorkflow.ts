/**
 * QA工作流類型定義
 * 
 * 用於管理AI問答的漸進式交互流程
 */

/**
 * QA工作流步驟枚舉
 */
export enum QAWorkflowStep {
  ANALYZING = 'analyzing',                          // AI 分析中
  CLASSIFICATION_RESULT = 'classification_result',  // 顯示分類結果
  NEED_CLARIFICATION = 'need_clarification',        // 需要澄清
  AWAITING_SEARCH_APPROVAL = 'awaiting_search_approval', // 等待搜索批准
  AWAITING_DETAIL_QUERY_APPROVAL = 'awaiting_detail_query_approval', // 等待詳細查詢批准 ⭐ 新增
  SEARCHING_DOCUMENTS = 'searching_documents',      // 搜索文檔中
  QUERYING_DETAILS = 'querying_details',            // 查詢詳細數據中 ⭐ 新增
  DOCUMENTS_FOUND = 'documents_found',              // 找到文檔
  AWAITING_ANSWER_APPROVAL = 'awaiting_answer_approval', // 等待答案生成批准
  GENERATING_ANSWER = 'generating_answer',          // 生成答案中
  COMPLETED = 'completed',                          // 完成
  ERROR = 'error'                                   // 錯誤
}

/**
 * 問題意圖類型
 */
export enum QuestionIntent {
  GREETING = 'greeting',                    // 寒暄問候
  CHITCHAT = 'chitchat',                   // 閒聊
  CLARIFICATION_NEEDED = 'clarification_needed', // 需要澄清
  SIMPLE_FACTUAL = 'simple_factual',       // 簡單事實查詢
  DOCUMENT_SEARCH = 'document_search',     // 文檔搜索
  DOCUMENT_DETAIL_QUERY = 'document_detail_query', // 文檔詳細查詢 ⭐ 新增
  COMPLEX_ANALYSIS = 'complex_analysis'    // 複雜分析
}

/**
 * 問題分類結果
 */
export interface QuestionClassification {
  intent: QuestionIntent;
  confidence: number;
  reasoning: string;
  requires_documents: boolean;
  requires_context: boolean;
  suggested_strategy: string;
  query_complexity?: string;
  estimated_api_calls?: number;
  clarification_question?: string;
  suggested_responses?: string[];
}

/**
 * 文檔摘要信息
 */
export interface DocumentSummary {
  document_id: string;
  filename: string;
  summary: string;
  similarity: number;
  file_type?: string;
}

/**
 * 工作流狀態
 */
export interface WorkflowState {
  currentStep: QAWorkflowStep;
  classification?: QuestionClassification;
  clarificationQuestion?: string;
  suggestedResponses?: string[];
  foundDocuments?: DocumentSummary[];
  pendingAction?: 'approve_search' | 'approve_answer' | 'provide_clarification';
  canSkipToAnswer?: boolean;
  strategyUsed?: string;
  apiCallsCount?: number;
  errorMessage?: string;
}

/**
 * 處理步驟信息
 */
export interface ProcessingStepInfo {
  step: QAWorkflowStep;
  label: string;
  status: 'waiting' | 'processing' | 'completed' | 'skipped' | 'error';
  icon?: string;
  description?: string;
}

/**
 * 工作流配置
 */
export interface QAWorkflowConfig {
  intelligent_routing_enabled: boolean;
  classifier_enabled: boolean;
  classifier_model: string;
  confidence_threshold: number;
  hybrid_search_enabled: boolean;
}

/**
 * 意圖標籤映射
 */
export const INTENT_LABELS: Record<QuestionIntent, string> = {
  [QuestionIntent.GREETING]: '寒暄問候',
  [QuestionIntent.CHITCHAT]: '閒聊對話',
  [QuestionIntent.CLARIFICATION_NEEDED]: '需要澄清',
  [QuestionIntent.SIMPLE_FACTUAL]: '簡單查詢',
  [QuestionIntent.DOCUMENT_SEARCH]: '文檔搜索',
  [QuestionIntent.DOCUMENT_DETAIL_QUERY]: '詳細查詢',  // ⭐ 新增
  [QuestionIntent.COMPLEX_ANALYSIS]: '複雜分析'
};

/**
 * 步驟標籤映射
 */
export const STEP_LABELS: Record<QAWorkflowStep, string> = {
  [QAWorkflowStep.ANALYZING]: '分析問題',
  [QAWorkflowStep.CLASSIFICATION_RESULT]: '意圖識別',
  [QAWorkflowStep.NEED_CLARIFICATION]: '需要澄清',
  [QAWorkflowStep.AWAITING_SEARCH_APPROVAL]: '等待搜索批准',
  [QAWorkflowStep.AWAITING_DETAIL_QUERY_APPROVAL]: '等待詳細查詢批准',  // ⭐ 新增
  [QAWorkflowStep.SEARCHING_DOCUMENTS]: '搜索文檔',
  [QAWorkflowStep.QUERYING_DETAILS]: '查詢詳細數據',  // ⭐ 新增
  [QAWorkflowStep.DOCUMENTS_FOUND]: '找到文檔',
  [QAWorkflowStep.AWAITING_ANSWER_APPROVAL]: '確認文檔',
  [QAWorkflowStep.GENERATING_ANSWER]: '生成答案',
  [QAWorkflowStep.COMPLETED]: '完成',
  [QAWorkflowStep.ERROR]: '錯誤'
};

/**
 * 獲取當前步驟的索引
 */
export function getCurrentStepIndex(currentStep: QAWorkflowStep): number {
  const stepOrder = [
    QAWorkflowStep.ANALYZING,
    QAWorkflowStep.CLASSIFICATION_RESULT,
    QAWorkflowStep.SEARCHING_DOCUMENTS,
    QAWorkflowStep.GENERATING_ANSWER,
    QAWorkflowStep.COMPLETED
  ];
  
  const index = stepOrder.indexOf(currentStep);
  return index >= 0 ? index : 0;
}

/**
 * 獲取意圖的顏色標記
 */
export function getIntentColor(intent: QuestionIntent): string {
  const colorMap: Record<QuestionIntent, string> = {
    [QuestionIntent.GREETING]: 'green',
    [QuestionIntent.CHITCHAT]: 'cyan',
    [QuestionIntent.CLARIFICATION_NEEDED]: 'orange',
    [QuestionIntent.SIMPLE_FACTUAL]: 'blue',
    [QuestionIntent.DOCUMENT_SEARCH]: 'purple',
    [QuestionIntent.DOCUMENT_DETAIL_QUERY]: 'geekblue',  // ⭐ 新增
    [QuestionIntent.COMPLEX_ANALYSIS]: 'red'
  };
  
  return colorMap[intent] || 'default';
}

/**
 * 獲取步驟的圖標
 */
export function getStepIcon(step: QAWorkflowStep): string {
  const iconMap: Record<QAWorkflowStep, string> = {
    [QAWorkflowStep.ANALYZING]: 'search',
    [QAWorkflowStep.CLASSIFICATION_RESULT]: 'bulb',
    [QAWorkflowStep.NEED_CLARIFICATION]: 'question-circle',
    [QAWorkflowStep.AWAITING_SEARCH_APPROVAL]: 'file-search',
    [QAWorkflowStep.AWAITING_DETAIL_QUERY_APPROVAL]: 'file-text',  // ⭐ 新增
    [QAWorkflowStep.SEARCHING_DOCUMENTS]: 'loading',
    [QAWorkflowStep.QUERYING_DETAILS]: 'database',  // ⭐ 新增
    [QAWorkflowStep.DOCUMENTS_FOUND]: 'check-circle',
    [QAWorkflowStep.AWAITING_ANSWER_APPROVAL]: 'file-done',
    [QAWorkflowStep.GENERATING_ANSWER]: 'robot',
    [QAWorkflowStep.COMPLETED]: 'check',
    [QAWorkflowStep.ERROR]: 'close-circle'
  };
  
  return iconMap[step] || 'info-circle';
}

