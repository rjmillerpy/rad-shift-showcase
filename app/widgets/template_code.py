"""Widget template starter code strings.

Split across ``template_code_ui``, ``template_code_data``, and
``template_code_langs`` so each sibling stays under the 400-line cap.
This entry-point re-exports every constant for unchanged call sites.
"""

from app.widgets.template_code_data import (
    API_CODE,
    DB_CONNECTOR_CODE,
    LAMBDA_CODE_NODE,
    LAMBDA_CODE_PY,
)
from app.widgets.template_code_langs import (
    C_WASM_CODE,
    PHP_CODE,
    REACT_CODE,
    RUBY_CODE,
)
from app.widgets.template_code_ui import (
    DISPLAY_MOD_CODE,
    GAME_CODE,
    SOCIAL_CODE,
    TOOL_CODE,
    VIZ_CODE,
)

__all__ = [
    "GAME_CODE",
    "TOOL_CODE",
    "VIZ_CODE",
    "SOCIAL_CODE",
    "DISPLAY_MOD_CODE",
    "API_CODE",
    "LAMBDA_CODE_PY",
    "LAMBDA_CODE_NODE",
    "DB_CONNECTOR_CODE",
    "REACT_CODE",
    "C_WASM_CODE",
    "RUBY_CODE",
    "PHP_CODE",
]
