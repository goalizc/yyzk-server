"""进销存 service 层：单号生成、单据创建、行锁过账、冲正。

router 只做参数校验与调用，不得直接写余额或流水。
"""

from app.services.inventory.doc_no import next_doc_no
from app.services.inventory.posting import (
    DOC_TYPES,
    IN_TYPES,
    OUT_TYPES,
    DocumentInput,
    ItemInput,
    create_document,
    current_balance,
    edit_document,
    ensure_sku_not_in_use,
    post_document,
    reverse_document,
)

__all__ = [
    "DOC_TYPES",
    "IN_TYPES",
    "OUT_TYPES",
    "DocumentInput",
    "ItemInput",
    "create_document",
    "current_balance",
    "edit_document",
    "ensure_sku_not_in_use",
    "next_doc_no",
    "post_document",
    "reverse_document",
]
