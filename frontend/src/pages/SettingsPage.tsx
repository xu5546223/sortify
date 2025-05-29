import React, { useState, useEffect, useCallback } from 'react';
import { PageHeader, Card, Input, Button, ToggleSwitch, Select } from '../components';
import type {
    SettingsData,
    UpdatableSettingsPayload,
    TestApiKeyResponse,
    TestDBConnectionRequest,
    TestDBConnectionResponse
} from '../types/apiTypes';
import {
    getSettings,
    updateSettings,
    getGoogleAIModels,
    testGoogleApiKey,
    testDBConnection,
} from '../services/systemService';

interface SettingsPageProps {
  showPCMessage: (message: string, type: 'success' | 'error' | 'info') => void;
}

const SettingsPage: React.FC<SettingsPageProps> = ({ showPCMessage }) => {
  const initialSettings: SettingsData = {
    aiService: {
      model: '',
      temperature: 0.7,
      is_api_key_configured: false,
      provider: 'google',
      force_stable_model: true,
      ensure_chinese_output: true,
      max_output_tokens: null,
    },
    database: {
      uri: '',
      dbName: '',
    },
    autoConnect: false,
    autoSync: false,
  };
  const [settings, setSettings] = useState<SettingsData>(initialSettings);
  const [apiKeyInput, setApiKeyInput] = useState<string>('');
  const [isApiKeyVerified, setIsApiKeyVerified] = useState<boolean>(false);
  const [apiKeyTestMessage, setApiKeyTestMessage] = useState<string | null>(null);
  const [isTestingApiKey, setIsTestingApiKey] = useState<boolean>(false);
  const [availableAIModels, setAvailableAIModels] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const [isTestingDB, setIsTestingDB] = useState<boolean>(false);
  const [dbTestMessage, setDbTestMessage] = useState<string | null>(null);
  const [isDBVerified, setIsDBVerified] = useState<boolean>(false);

  const fetchInitialData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getSettings();
      setSettings(prev => {
        const newAiServiceSettings = {
          ...prev.aiService,
          ...(data.aiService || {}),
        };

        // Explicitly set boolean fields if they exist in data.aiService
        // If they are explicitly null or undefined in data.aiService, they might keep prev values or default.
        // We want to prioritize the value from 'data' if it's a boolean.
        if (typeof data.aiService?.force_stable_model === 'boolean') {
          newAiServiceSettings.force_stable_model = data.aiService.force_stable_model;
        } else {
          // If not a boolean (e.g. undefined, null), keep previous or default to true
          newAiServiceSettings.force_stable_model = prev.aiService?.force_stable_model ?? true;
        }

        if (typeof data.aiService?.ensure_chinese_output === 'boolean') {
          newAiServiceSettings.ensure_chinese_output = data.aiService.ensure_chinese_output;
        } else {
          newAiServiceSettings.ensure_chinese_output = prev.aiService?.ensure_chinese_output ?? true;
        }

        if (typeof data.aiService?.max_output_tokens === 'number') {
          newAiServiceSettings.max_output_tokens = data.aiService.max_output_tokens;
        } else {
          newAiServiceSettings.max_output_tokens = prev.aiService?.max_output_tokens ?? null;
        }
        
        return {
          ...prev,
          ...data,
          aiService: newAiServiceSettings,
          database: { ...prev.database, ...(data.database || {}) },
        };
      });
      setIsApiKeyVerified(data.aiService?.is_api_key_configured || false);
      
      const models = await getGoogleAIModels();
      setAvailableAIModels(models);
      showPCMessage('成功獲取目前設定與AI模型列表', 'success');
    } catch (error) {
      console.error('Failed to fetch settings or AI models:', error);
      showPCMessage('獲取設定或AI模型列表失敗', 'error');
    }
    setIsLoading(false);
  }, [showPCMessage]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  const handleApiKeyInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setApiKeyInput(e.target.value);
    setIsApiKeyVerified(false);
    setApiKeyTestMessage(null);
  };

  const handleTestApiKey = async () => {
    if (!apiKeyInput) {
      setApiKeyTestMessage("請先輸入 API 金鑰");
      return;
    }
    setIsTestingApiKey(true);
    setApiKeyTestMessage(null);
    try {
      const response = await testGoogleApiKey(apiKeyInput);
      setApiKeyTestMessage(response.message);
      setIsApiKeyVerified(response.is_valid);
      if(response.is_valid) {
        showPCMessage('API 金鑰驗證成功！', 'success');
      } else {
        showPCMessage(`API 金鑰驗證失敗: ${response.message}`, 'error');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "測試API金鑰時發生未知錯誤";
      setApiKeyTestMessage(message);
      setIsApiKeyVerified(false);
      showPCMessage(`測試失敗: ${message}`, 'error');
    }
    setIsTestingApiKey(false);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    const inputElement = e.target as HTMLInputElement; // Cast for accessing .checked
    const newBooleanState = inputElement.checked; // Get boolean state, assuming ToggleSwitch uses this

    setSettings(prev => {
      const newSettings = { ...prev };
      const nameParts = name.split('.');
      const section = nameParts[0];
      const field = nameParts[1];

      if (field && (section === 'aiService' || section === 'database')) { // Nested setting
        const currentSectionData = newSettings[section as keyof Pick<SettingsData, 'aiService' | 'database'>] || {};
        let newValue;

        // Explicitly handle boolean toggles for aiService
        if (section === 'aiService' && (field === 'force_stable_model' || field === 'ensure_chinese_output')) {
          newValue = newBooleanState;
        } else if (type === 'number' || name === 'aiService.max_output_tokens') {
          newValue = parseInt(value, 10);
          if (name === 'aiService.max_output_tokens' && (isNaN(newValue) || newValue <= 0)) {
            newValue = null;
          }
        } else { // Handle other string inputs (like model select, db uri, dbName)
          newValue = value;
        }
        
        newSettings[section as keyof Pick<SettingsData, 'aiService' | 'database'>] = {
          ...(typeof currentSectionData === 'object' && currentSectionData !== null ? currentSectionData : {}),
          [field]: newValue,
        };

        if (section === 'database') {
          setIsDBVerified(false);
          setDbTestMessage(null);
        }
      } else { // Top-level setting (e.g., autoConnect, autoSync)
        if (name === 'autoConnect' || name === 'autoSync') {
          (newSettings as any)[name] = newBooleanState;
        } else {
          // Fallback for any other top-level simple inputs if they exist
          (newSettings as any)[name] = (type === 'checkbox' && inputElement.checked !== undefined) 
                                       ? newBooleanState 
                                       : value;
        }
      }
      return newSettings;
    });
  };

  const handleTestDBConnection = async () => {
    const dbUri = settings.database?.uri;
    const dbName = settings.database?.dbName;

    if (!dbUri || !dbName) {
      setDbTestMessage("請先輸入 MongoDB URI 和資料庫名稱。");
      setIsDBVerified(false);
      return;
    }

    setIsTestingDB(true);
    setDbTestMessage(null);
    try {
      const payload: TestDBConnectionRequest = { uri: dbUri, db_name: dbName };
      const response = await testDBConnection(payload);
      setDbTestMessage(response.message);
      setIsDBVerified(response.success);
      if (response.success) {
        showPCMessage(`資料庫連線成功: ${response.message}`, 'success');
      } else {
        let detailedMessage = `資料庫連線失敗: ${response.message}`;
        if (response.error_details) {
            detailedMessage += ` (${response.error_details})`;
        }
        showPCMessage(detailedMessage, 'error');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "測試資料庫連線時發生未知錯誤";
      setDbTestMessage(message);
      setIsDBVerified(false);
      showPCMessage(`測試失敗: ${message}`, 'error');
    }
    setIsTestingDB(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (apiKeyInput && !isApiKeyVerified) {
      showPCMessage("請先測試並驗證您輸入的 API 金鑰，或清除 API 金鑰欄位以保留現有金鑰。", "error");
      setApiKeyTestMessage("請先測試此 API 金鑰或清空此欄位。");
      return;
    }

    const dbUri = settings.database?.uri;
    const dbName = settings.database?.dbName;

    const hasDatabaseSettings = settings.database && (dbUri || dbName);

    if (hasDatabaseSettings && !isDBVerified) {
        showPCMessage("您修改了資料庫設定，請先成功測試資料庫連線後再儲存。", "error");
        setDbTestMessage("請先成功測試此資料庫連線。");
        return;
    }

    setIsSaving(true);
    const payload: UpdatableSettingsPayload = {
      aiService: {
        provider: settings.aiService?.provider || 'google',
        model: settings.aiService?.model || null,
        temperature: settings.aiService?.temperature ?? 0.7,
        force_stable_model: settings.aiService?.force_stable_model ?? true,
        ensure_chinese_output: settings.aiService?.ensure_chinese_output ?? true,
        max_output_tokens: settings.aiService?.max_output_tokens ?? null,
      },
      database: {
        uri: settings.database?.uri || null,
        dbName: settings.database?.dbName || null,
      },
      autoConnect: settings.autoConnect ?? false,
      autoSync: settings.autoSync ?? false,
    };

    if (apiKeyInput && isApiKeyVerified) {
      if (payload.aiService) {
        payload.aiService.apiKey = apiKeyInput;
      }
    } else if (!apiKeyInput && settings.aiService?.is_api_key_configured) {
    }

    try {
      const updatedSettingsData = await updateSettings(payload);
      setSettings(prev => ({
        ...prev,
        ...updatedSettingsData,
        aiService: {
            ...(prev.aiService || {}),
            ...(updatedSettingsData.aiService || {}),
        }
      }));
      
      if (apiKeyInput && isApiKeyVerified) {
        showPCMessage('設定已成功儲存 (包含新的 API 金鑰)', 'success');
        setApiKeyInput('');
        setIsApiKeyVerified(true);
        setApiKeyTestMessage("新的 API 金鑰已儲存並驗證。");
      } else {
        showPCMessage('設定已成功儲存', 'success');
      }
      await fetchInitialData();

    } catch (error) {
      console.error('Failed to save settings:', error);
      showPCMessage('儲存設定失敗', 'error');
    }
    setIsSaving(false);
  };

  if (isLoading) {
    return <div className="p-4">正在載入設定...</div>;
  }

  return (
    <div className="p-6 bg-surface-100 min-h-screen">
      <PageHeader title="系統設定" />

      <form onSubmit={handleSubmit}>
        <Card title="AI 服務設定" className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            <div className="flex flex-col space-y-1">
              <Input
                label="API 金鑰 (Google AI)"
                name="aiService.apiKeyInput"
                type="password"
                value={apiKeyInput}
                onChange={handleApiKeyInputChange}
                placeholder="輸入新的 API 金鑰以更新"
              />
              <Button 
                type="button" 
                onClick={handleTestApiKey} 
                disabled={isTestingApiKey || !apiKeyInput}
                className="mt-1 w-full md:w-auto"
              >
                {isTestingApiKey ? '測試中...' : '測試連線'}
              </Button>
              {apiKeyTestMessage && (
                <p className={`text-sm mt-1 ${isApiKeyVerified ? 'text-green-600' : 'text-red-600'}`}>
                  {apiKeyTestMessage}
                </p>
              )}
              {!apiKeyTestMessage && settings.aiService?.is_api_key_configured !== undefined && (
                <p className="text-sm text-gray-500 mt-1">
                  系統目前 API 金鑰狀態: {settings.aiService.is_api_key_configured ? 
                    <span className="text-green-600">已配置</span> : 
                    <span className="text-red-600">未配置</span>}
                </p>
              )}
            </div>
            
            <Select
              label="AI 模型 (Google)"
              name="aiService.model"
              value={settings.aiService?.model || ''}
              onChange={handleChange}
              options={availableAIModels.map(model => ({ value: model, label: model }))}
              disabled={availableAIModels.length === 0}
            />

            <div>
              <label htmlFor="aiService.temperature" className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
              <input
                id="aiService.temperature"
                name="aiService.temperature"
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={settings.aiService?.temperature ?? 0.7}
                onChange={handleChange}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
              />
              <span className="text-sm text-gray-500">目前: {settings.aiService?.temperature ?? 0.7}</span>
            </div>

            <div className="md:col-span-1">
              <Input
                label="最大輸出 Token (AI)"
                name="aiService.max_output_tokens"
                type="number"
                value={settings.aiService?.max_output_tokens === null || settings.aiService?.max_output_tokens === undefined ? '' : String(settings.aiService.max_output_tokens)}
                onChange={handleChange}
                placeholder="例如: 2048, 留空則使用默認值"
                min="0"
              />
              <p className="text-xs text-gray-500 mt-1">
                設定 AI 生成內容的最大 token 數量。影響內容完整性與請求成本。
              </p>
            </div>

            <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
              <ToggleSwitch
                label="AI 強制穩定模型"
                name="aiService.force_stable_model"
                checked={settings.aiService?.force_stable_model ?? true}
                onChange={handleChange}
              />
              <ToggleSwitch
                label="AI 強制中文輸出"
                name="aiService.ensure_chinese_output"
                checked={settings.aiService?.ensure_chinese_output ?? true}
                onChange={handleChange}
              />
            </div>
          </div>
        </Card>

        <Card title="資料庫設定" className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="MongoDB URI"
              name="database.uri"
              value={settings.database?.uri || ''}
              onChange={handleChange}
              placeholder="例如：mongodb://localhost:27017"
            />
            <Input
              label="資料庫名稱"
              name="database.dbName"
              value={settings.database?.dbName || ''}
              onChange={handleChange}
              placeholder="例如：sortify_db"
            />
          </div>
          <div className="mt-4">
            <Button
              type="button"
              onClick={handleTestDBConnection}
              disabled={isTestingDB || !settings.database?.uri || !settings.database?.dbName}
              className="w-full md:w-auto"
            >
              {isTestingDB ? '測試中...' : '測試資料庫連線'}
            </Button>
            {dbTestMessage && (
              <p className={`text-sm mt-2 ${isDBVerified ? 'text-green-600' : 'text-red-600'}`}>
                {dbTestMessage}
              </p>
            )}
          </div>
        </Card>

        <Card title="其他設定" className="mb-6">
            <ToggleSwitch 
                label="自動連線到後端服務"
                name="autoConnect"
                checked={settings.autoConnect ?? false}
                onChange={handleChange}
            />
            <ToggleSwitch 
                label="自動同步檔案"
                name="autoSync"
                checked={settings.autoSync ?? false}
                onChange={handleChange}
            />
        </Card>

        <div className="flex justify-end">
          <Button 
            type="submit" 
            className="bg-blue-600 hover:bg-blue-700 text-white" 
            disabled={isSaving || isTestingApiKey || (apiKeyInput !== '' && !isApiKeyVerified) || (settings.database?.uri !== '' && settings.database?.dbName !== '' && !isDBVerified) }
          >
            {isSaving ? '儲存中...' : '儲存設定'}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default SettingsPage;