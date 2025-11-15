"""
全局测试配置

定义全局的 pytest 配置和通用 fixtures。
"""

import pytest
from uuid import UUID


def pytest_configure(config):
    """
    Pytest 配置钩子
    
    注册自定义标记和配置。
    """
    # 注册测试标记
    config.addinivalue_line(
        "markers",
        "unit: 单元测试，使用 mock，不依赖外部资源"
    )
    config.addinivalue_line(
        "markers",
        "integration: 集成测试，使用真实数据库，测试完整流程"
    )
    config.addinivalue_line(
        "markers",
        "slow: 慢速测试，可能需要较长时间执行"
    )


# 通用的测试辅助 fixtures（可选）

@pytest.fixture
def fixed_uuid():
    """
    提供一个固定的 UUID 用于测试
    
    用途：当需要可预测的 UUID 时使用
    """
    return UUID('12345678-1234-5678-1234-567812345678')


@pytest.fixture
def another_fixed_uuid():
    """
    提供另一个固定的 UUID 用于测试
    
    用途：测试需要比较不同 UUID 时
    """
    return UUID('87654321-4321-8765-4321-876543218765')


# 可以添加更多全局 fixtures...
