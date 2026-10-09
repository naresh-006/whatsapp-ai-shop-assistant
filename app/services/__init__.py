"""Services package exports."""

from app.services.product_service import (
    upsert_product,
    get_product_by_id,
    list_products,
    search_products,
    seed_real_products,
    seed_dummy_products,
    clear_dummy_products,
    seed_all,
)
from app.services.billing_service import (
    validate_unit,
    calculate_item_amount,
    calculate_bundle_amount,
    calculate_total,
    calculate_bill,
)
from app.services.order_service import (
    create_order,
    get_order,
    get_active_order_by_session,
    add_item_to_order,
    update_item_quantity,
    remove_item_from_order,
    confirm_order,
    cancel_order,
)
from app.services.ai_service import extract_order_from_text
from app.services.resolver_service import (
    resolve_product_text,
    resolve_extracted_order,
    ResolutionStatus,
    ResolutionResult,
)
from app.services.pipeline_service import (
    process_natural_language_order,
    apply_conversational_correction,
)
from app.services.sales_service import (
    save_confirmed_sale,
    get_sale_by_invoice,
    search_sales_by_customer,
    get_sales_by_product,
    get_sales_for_today,
    get_daily_sales_summary,
)

__all__ = [
    "upsert_product",
    "get_product_by_id",
    "list_products",
    "search_products",
    "seed_real_products",
    "seed_dummy_products",
    "clear_dummy_products",
    "seed_all",
    "validate_unit",
    "calculate_item_amount",
    "calculate_bundle_amount",
    "calculate_total",
    "calculate_bill",
    "create_order",
    "get_order",
    "get_active_order_by_session",
    "add_item_to_order",
    "update_item_quantity",
    "remove_item_from_order",
    "confirm_order",
    "cancel_order",
    "extract_order_from_text",
    "resolve_product_text",
    "resolve_extracted_order",
    "ResolutionStatus",
    "ResolutionResult",
    "process_natural_language_order",
    "apply_conversational_correction",
    "save_confirmed_sale",
    "get_sale_by_invoice",
    "search_sales_by_customer",
    "get_sales_by_product",
    "get_sales_for_today",
    "get_daily_sales_summary",
]
