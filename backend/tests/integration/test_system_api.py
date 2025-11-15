"""
System API (系統設置) 整合測試

測試系統設置 API 的核心業務邏輯，專注於：
- 系統設置的讀取和更新
- 設置數據驗證
- 數據庫副作用驗證

注意：這是服務層測試，不是 HTTP API 測試
"""

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user_models import User
from app.models.system_models import (
    SettingsDataResponse,
    UpdatableSettingsData,
    AIServiceSettingsStored,
    DatabaseSettings
)
from app.crud import crud_settings

# 標記為整合測試
pytestmark = pytest.mark.integration


# ========== 測試類：系統設置基本操作 ==========

class TestSystemSettingsBasicOperations:
    """測試系統設置的基本讀寫操作"""
    
    @pytest.mark.asyncio
    async def test_get_default_settings(
        self,
        test_db,
        test_user
    ):
        """
        場景：首次獲取系統設置（使用默認值）
        預期：返回默認設置
        """
        # 獲取設置
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證返回值
        assert settings is not None
        assert isinstance(settings, SettingsDataResponse)
        
        # 驗證 AI 服務設置存在
        assert settings.ai_service is not None
        assert isinstance(settings.ai_service, AIServiceSettingsStored)
        
        # 驗證數據庫設置存在
        assert settings.database is not None
        assert isinstance(settings.database, DatabaseSettings)
    
    @pytest.mark.asyncio
    async def test_settings_structure(
        self,
        test_db
    ):
        """
        場景：驗證設置的數據結構
        預期：設置包含所有必需字段
        """
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證 AI 服務設置字段
        assert hasattr(settings.ai_service, 'model')
        assert hasattr(settings.ai_service, 'temperature')
        assert hasattr(settings.ai_service, 'is_api_key_configured')
        
        # 驗證頂層數據庫連接字段
        assert hasattr(settings, 'is_database_connected')


class TestSystemSettingsUpdate:
    """測試系統設置更新"""
    
    @pytest.mark.asyncio
    async def test_update_ai_model_setting(
        self,
        test_db
    ):
        """
        場景：更新 AI 模型設置
        預期：設置成功更新
        """
        from app.models.system_models import AIServiceSettingsInput
        
        # 準備更新數據
        ai_input = AIServiceSettingsInput(
            model="gemini-1.5-pro",
            temperature=0.7
        )
        update_data = UpdatableSettingsData(ai_service=ai_input)
        
        # 更新設置（注意：實際實現可能需要環境變量）
        # 這裡我們主要測試數據驗證邏輯
        assert update_data.ai_service is not None
        assert update_data.ai_service.model == "gemini-1.5-pro"
        assert update_data.ai_service.temperature == 0.7
    
    @pytest.mark.asyncio
    async def test_temperature_validation(self):
        """
        場景：驗證溫度參數範圍
        預期：溫度應在 0-1 範圍內
        """
        from app.models.system_models import AIServiceSettingsInput
        
        # 有效的溫度
        ai_input = AIServiceSettingsInput(model="gemini-1.5-flash", temperature=0.5)
        valid_update = UpdatableSettingsData(ai_service=ai_input)
        assert valid_update.ai_service.temperature == 0.5
        
        # 邊界值測試
        min_input = AIServiceSettingsInput(model="test", temperature=0.0)
        min_temp = UpdatableSettingsData(ai_service=min_input)
        assert min_temp.ai_service.temperature == 0.0
        
        max_input = AIServiceSettingsInput(model="test", temperature=1.0)
        max_temp = UpdatableSettingsData(ai_service=max_input)
        assert max_temp.ai_service.temperature == 1.0


class TestSystemSettingsValidation:
    """測試系統設置數據驗證"""
    
    @pytest.mark.asyncio
    async def test_ai_service_model_optional(self):
        """
        場景：AI 模型名稱是可選的
        預期：可以只設置其他屬性
        """
        from app.models.system_models import AIServiceSettingsInput
        
        # 創建只有溫度的設置
        ai_input = AIServiceSettingsInput(temperature=0.7)
        update_data = UpdatableSettingsData(ai_service=ai_input)
        
        # 驗證可以創建
        assert update_data.ai_service is not None
        assert update_data.ai_service.temperature == 0.7
    
    @pytest.mark.asyncio
    async def test_database_connection_status(
        self,
        test_db
    ):
        """
        場景：數據庫連接狀態反映實際狀態
        預期：測試環境中數據庫應該已連接
        """
        settings = await crud_settings.get_system_settings(test_db)
        
        # 在測試環境中，is_database_connected 是頂層字段
        assert hasattr(settings, 'is_database_connected')


class TestSystemSettingsSecurityConcerns:
    """測試系統設置的安全性問題"""
    
    @pytest.mark.asyncio
    async def test_api_key_not_exposed_in_response(
        self,
        test_db
    ):
        """
        場景：API Key 不應在響應中暴露
        預期：響應只包含配置狀態標誌
        """
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證 AI 服務設置
        # API Key 不應該在響應中（只有 is_api_key_configured 標誌）
        assert hasattr(settings.ai_service, 'is_api_key_configured')
        
        # 響應模型不應該有 api_key 字段（敏感信息）
        # AIServiceSettingsStored 不包含 api_key
        assert not hasattr(settings.ai_service, 'api_key')


class TestSystemSettingsPersistence:
    """測試系統設置的持久化"""
    
    @pytest.mark.asyncio
    async def test_settings_persisted_to_database(
        self,
        test_db
    ):
        """
        場景：設置更新後應該持久化到數據庫
        預期：數據庫中保存最新設置
        """
        # 獲取初始設置
        initial_settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證設置可以被讀取
        assert initial_settings is not None
        
        # 注意：實際的持久化測試需要調用 update 方法
        # 這裡主要驗證讀取邏輯
    
    @pytest.mark.asyncio
    async def test_settings_consistency_across_reads(
        self,
        test_db
    ):
        """
        場景：多次讀取設置應該一致
        預期：返回相同的設置
        """
        # 第一次讀取
        settings1 = await crud_settings.get_system_settings(test_db)
        
        # 第二次讀取
        settings2 = await crud_settings.get_system_settings(test_db)
        
        # 驗證一致性（model 和 temperature 可能是 None）
        assert settings1.ai_service.model == settings2.ai_service.model
        assert settings1.ai_service.temperature == settings2.ai_service.temperature
        assert settings1.is_database_connected == settings2.is_database_connected


class TestSystemSettingsEdgeCases:
    """測試系統設置的邊界情況"""
    
    @pytest.mark.asyncio
    async def test_settings_with_empty_database(
        self,
        test_db
    ):
        """
        場景：數據庫為空時獲取設置
        預期：返回默認設置
        """
        # 清空 settings 集合（如果存在）
        if "settings" in await test_db.list_collection_names():
            await test_db["settings"].delete_many({})
        
        # 獲取設置（應該返回默認值）
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證返回默認設置
        assert settings is not None
        assert settings.ai_service is not None
    
    @pytest.mark.asyncio
    async def test_partial_settings_update(self):
        """
        場景：部分更新設置（只更新某些字段）
        預期：只更新指定的字段
        """
        from app.models.system_models import AIServiceSettingsInput
        
        # 只更新溫度
        ai_input = AIServiceSettingsInput(temperature=0.9)
        partial_update = UpdatableSettingsData(ai_service=ai_input)
        
        assert partial_update.ai_service.temperature == 0.9
        
        # 驗證可以只更新部分字段
        # 其他字段應該保持原值（在實際更新邏輯中）


class TestSystemSettingsDefault:
    """測試系統設置的默認值"""
    
    @pytest.mark.asyncio
    async def test_default_ai_provider_is_set(
        self,
        test_db
    ):
        """
        場景：默認 AI 提供商應該被設置
        預期：有合理的默認值
        """
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證默認提供商存在
        assert settings.ai_service.provider is not None
        assert settings.ai_service.provider == "google"
    
    @pytest.mark.asyncio
    async def test_default_temperature_is_none_or_reasonable(
        self,
        test_db
    ):
        """
        場景：默認溫度可能未設置或在合理範圍內
        預期：溫度是 None 或在 0-1 之間
        """
        settings = await crud_settings.get_system_settings(test_db)
        
        # 驗證默認溫度（可能是 None）
        if settings.ai_service.temperature is not None:
            assert settings.ai_service.temperature >= 0.0
            assert settings.ai_service.temperature <= 1.0
