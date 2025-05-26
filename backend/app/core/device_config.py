"""
設備配置管理器
提供 CPU/GPU 選擇、智能推薦和運行時切換功能
"""
import os
import logging
from typing import Literal, Optional, Dict, Any
from enum import Enum

from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.INFO).get_logger()

class DeviceType(str, Enum):
    """設備類型枚舉"""
    CPU = "cpu"
    CUDA = "cuda"
    AUTO = "auto"

class DeviceConfigManager:
    """設備配置管理器"""
    
    def __init__(self):
        self._preferred_device: Optional[DeviceType] = None
        self._current_device: Optional[str] = None
        self._gpu_available: bool = False
        self._gpu_info: Optional[Dict[str, Any]] = None
        self._initialize()
    
    def _initialize(self) -> None:
        """初始化設備配置"""
        self._check_gpu_availability()
        self._load_device_preference()
    
    def _check_gpu_availability(self) -> None:
        """檢查 GPU 可用性"""
        try:
            import torch
            self._gpu_available = torch.cuda.is_available()
            
            if self._gpu_available:
                self._gpu_info = {
                    "device_name": torch.cuda.get_device_name(),
                    "memory_total": f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB",
                    "pytorch_version": torch.__version__,
                    "cuda_version": torch.version.cuda
                }
                logger.info(f"GPU 可用: {self._gpu_info['device_name']}")
            else:
                logger.info("GPU 不可用，將使用 CPU")
                
        except ImportError:
            logger.warning("PyTorch 未安裝，無法檢測 GPU")
            self._gpu_available = False
        except Exception as e:
            logger.error(f"檢查 GPU 可用性時發生錯誤: {e}")
            self._gpu_available = False
    
    def _load_device_preference(self) -> None:
        """從環境變數加載設備偏好"""
        env_device = os.getenv("EMBEDDING_DEVICE", "auto").lower()
        
        try:
            self._preferred_device = DeviceType(env_device)
            logger.info(f"從環境變數加載設備偏好: {self._preferred_device}")
        except ValueError:
            logger.warning(f"無效的設備偏好 '{env_device}'，使用默認值 'auto'")
            self._preferred_device = DeviceType.AUTO
    
    def get_optimal_device(self) -> str:
        """獲取最優設備"""
        if self._preferred_device == DeviceType.CPU:
            return "cpu"
        elif self._preferred_device == DeviceType.CUDA:
            if self._gpu_available:
                return "cuda"
            else:
                logger.warning("用戶偏好 GPU 但 GPU 不可用，降級到 CPU")
                return "cpu"
        else:  # AUTO
            return "cuda" if self._gpu_available else "cpu"
    
    def set_device_preference(self, device: DeviceType) -> bool:
        """設置設備偏好"""
        if device == DeviceType.CUDA and not self._gpu_available:
            logger.error("無法設置 GPU 偏好：GPU 不可用")
            return False
        
        self._preferred_device = device
        
        # 可選：保存到環境變數（需要重啟生效）
        os.environ["EMBEDDING_DEVICE"] = device.value
        
        logger.info(f"設備偏好已更新為: {device}")
        return True
    
    def get_device_config(self) -> Dict[str, Any]:
        """獲取完整的設備配置信息"""
        return {
            "current_device": self._current_device or self.get_optimal_device(),
            "preferred_device": self._preferred_device.value if self._preferred_device else "auto",
            "available_devices": self._get_available_devices(),
            "recommended_device": "cuda" if self._gpu_available else "cpu",
            "gpu_available": self._gpu_available,
            "gpu_info": self._gpu_info
        }
    
    def _get_available_devices(self) -> list[str]:
        """獲取可用設備列表"""
        devices = ["cpu"]
        if self._gpu_available:
            devices.append("cuda")
        return devices
    
    def update_current_device(self, device: str) -> None:
        """更新當前使用的設備"""
        self._current_device = device
        logger.info(f"當前設備已更新為: {device}")
    
    def get_performance_recommendation(self) -> Dict[str, Any]:
        """獲取性能建議"""
        recommendations = []
        
        if self._gpu_available and self._preferred_device != DeviceType.CUDA:
            recommendations.append({
                "type": "performance",
                "message": f"檢測到 {self._gpu_info['device_name']}，切換到 GPU 模式可顯著提升性能",
                "action": "switch_to_gpu"
            })
        
        if not self._gpu_available and self._preferred_device == DeviceType.CUDA:
            recommendations.append({
                "type": "fallback",
                "message": "GPU 不可用，已自動降級到 CPU 模式",
                "action": "fallback_to_cpu"
            })
        
        return {
            "recommendations": recommendations,
            "current_optimal": self.get_optimal_device(),
            "performance_impact": self._get_performance_impact()
        }
    
    def _get_performance_impact(self) -> Dict[str, str]:
        """獲取性能影響說明"""
        current_device = self.get_optimal_device()
        
        if current_device == "cuda":
            return {
                "embedding_speed": "快速 (3-6 秒)",
                "search_latency": "低延遲 (50-150ms)",
                "batch_processing": "高效 (3-8 分鐘/1000 文檔)"
            }
        else:
            return {
                "embedding_speed": "較慢 (8-12 秒)",
                "search_latency": "中等延遲 (200-500ms)",
                "batch_processing": "較慢 (15-25 分鐘/1000 文檔)"
            }

# 創建全局設備配置管理器實例
device_config_manager = DeviceConfigManager() 