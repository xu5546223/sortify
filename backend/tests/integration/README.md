# 集成测试

## 🎯 目标

测试真实的业务场景，使用真实的测试数据库，不使用 mock。

## 📋 测试内容

### test_document_permissions.py

测试文档权限控制的核心业务逻辑：

**TestDocumentOwnership** - 基础权限测试
- ✅ `test_get_own_document_success` - 用户可以访问自己的文档
- ✅ `test_get_document_not_found` - 文档不存在返回 404
- ✅ `test_get_other_user_document_forbidden` - 用户不能访问别人的文档（403）

**TestDocumentCRUDWithPermissions** - CRUD 操作权限
- ✅ `test_create_document_sets_correct_owner` - 创建文档设置正确的 owner_id
- ✅ `test_delete_own_document_success` - 用户可以删除自己的文档
- ✅ `test_update_own_document_success` - 用户可以更新自己的文档

**TestDocumentListWithPermissions** - 列表权限过滤
- ✅ `test_list_documents_only_shows_own_documents` - 列表只显示用户自己的文档

**TestRealWorldScenarios** - 真实业务场景
- ✅ `test_user_workflow_create_access_delete` - 完整的用户工作流
- ✅ `test_multiple_users_cannot_access_each_others_documents` - 多用户数据隔离

---

## 🚀 运行测试

### 前提条件

1. **测试数据库**：需要运行 MongoDB（本地或测试服务器）
   ```bash
   # 默认使用 mongodb://localhost:27017
   # 测试数据库名称：sortify_test_db
   ```

2. **环境变量**（可选）：
   ```bash
   # 自定义测试数据库 URL
   export TEST_MONGODB_URL="mongodb://localhost:27017"
   ```

### 运行所有集成测试

```bash
cd backend

# 运行所有集成测试
.venv\Scripts\python.exe -m pytest tests/integration/ -v

# 或使用短命令
pytest tests/integration/ -v
```

### 运行特定测试类

```bash
# 只测试基础权限
pytest tests/integration/test_document_permissions.py::TestDocumentOwnership -v

# 只测试 CRUD 权限
pytest tests/integration/test_document_permissions.py::TestDocumentCRUDWithPermissions -v

# 只测试真实场景
pytest tests/integration/test_document_permissions.py::TestRealWorldScenarios -v
```

### 运行单个测试

```bash
# 测试获取自己的文档
pytest tests/integration/test_document_permissions.py::TestDocumentOwnership::test_get_own_document_success -v

# 测试权限拒绝
pytest tests/integration/test_document_permissions.py::TestDocumentOwnership::test_get_other_user_document_forbidden -v
```

### 显示详细输出

```bash
# 显示 print 输出
pytest tests/integration/ -v -s

# 显示失败的详细信息
pytest tests/integration/ -v --tb=long

# 在第一个失败时停止
pytest tests/integration/ -v -x
```

---

## 🔧 测试数据库清理

每个测试前后都会自动清理测试数据库，确保测试隔离。

### 手动清理（如果需要）

```python
# tests/integration/conftest.py 中的清理逻辑
# 每个测试前后都会执行
```

### 查看测试数据库

```bash
# 连接到测试数据库
mongosh mongodb://localhost:27017/sortify_test_db

# 查看集合
show collections

# 查看用户
db.users.find()

# 查看文档
db.documents.find()
```

---

## ✅ 预期结果

所有测试应该通过：

```
tests/integration/test_document_permissions.py::TestDocumentOwnership::test_get_own_document_success PASSED
tests/integration/test_document_permissions.py::TestDocumentOwnership::test_get_document_not_found PASSED
tests/integration/test_document_permissions.py::TestDocumentOwnership::test_get_other_user_document_forbidden PASSED
tests/integration/test_document_permissions.py::TestDocumentCRUDWithPermissions::test_create_document_sets_correct_owner PASSED
tests/integration/test_document_permissions.py::TestDocumentCRUDWithPermissions::test_delete_own_document_success PASSED
tests/integration/test_document_permissions.py::TestDocumentCRUDWithPermissions::test_update_own_document_success PASSED
tests/integration/test_document_permissions.py::TestDocumentListWithPermissions::test_list_documents_only_shows_own_documents PASSED
tests/integration/test_document_permissions.py::TestRealWorldScenarios::test_user_workflow_create_access_delete PASSED
tests/integration/test_document_permissions.py::TestRealWorldScenarios::test_multiple_users_cannot_access_each_others_documents PASSED

======================== 9 passed in X.XX seconds ========================
```

---

## 🎯 下一步

1. **确保测试通过**
2. **开始重构代码**
3. **重构后再次运行测试验证**

如果所有测试都通过 → 可以安全地重构代码 ✅
