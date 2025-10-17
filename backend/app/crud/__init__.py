from .crud_users import crud_users
from . import crud_documents
from . import crud_settings
from . import crud_logs
from . import crud_dashboard

__all__ = [
    "crud_users",
    "crud_documents",
    "crud_settings",
    "crud_logs",
    "crud_dashboard",
]
