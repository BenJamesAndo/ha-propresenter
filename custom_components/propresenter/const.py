"""Constants for the ProPresenter integration."""

DOMAIN = "propresenter"

# Configuration constants
CONF_PORT = "port"
DEFAULT_PORT = 50001
DEFAULT_SCAN_INTERVAL = 5  # Poll every 5 seconds for faster updates

# API endpoints
API_VERSION = "v1"
ENDPOINT_VERSION = "/version"
ENDPOINT_PRESENTATION_ACTIVE = "/v1/presentation/active"
ENDPOINT_TRIGGER_NEXT = "/v1/trigger/next"
ENDPOINT_TRIGGER_PREVIOUS = "/v1/trigger/previous"
ENDPOINT_STAGE_SCREENS = "/v1/stage/screens"
ENDPOINT_STAGE_LAYOUTS = "/v1/stage/layouts"
ENDPOINT_STAGE_LAYOUT_MAP = "/v1/stage/layout_map"
ENDPOINT_MESSAGES = "/v1/messages"

# Service names
SERVICE_SHOW_MESSAGE = "show_message"
