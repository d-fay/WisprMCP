"""
MCP Apps (``ui://``) resources for WisprMCP.

Implements the server half of SEP-1865 / ``io.modelcontextprotocol/ui``
(Stable 2026-01-26): a tool declares ``_meta.ui.resourceUri`` pointing at a
``ui://`` resource, and the host fetches that resource's HTML via
``resources/read`` to mount as an interactive view.

Server obligations, and only these:
  1. serve the ``ui://`` resource from ``resources/read``
  2. name it from the tool definition via ``_meta.ui.resourceUri``

Everything else is the host's. A host without MCP Apps support ignores the
metadata and the tool degrades to its normal text output, so declaring a UI
resource is safe unconditionally.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

#: SEP-1865 reserves this MIME type for HTML app views.
APP_MIME_TYPE = "text/html;profile=mcp-app"

UI_DIR = Path(__file__).parent / "ui"

TRANSCRIPT_URI = "ui://wispr/transcript"


class UIResource:
    """One ``ui://`` resource backed by an HTML file on disk."""

    def __init__(self, uri: str, name: str, description: str, filename: str,
                 csp: Optional[Dict[str, Any]] = None):
        self.uri = uri
        self.name = name
        self.description = description
        self.filename = filename
        self.csp = csp or {}

    @property
    def path(self) -> Path:
        return UI_DIR / self.filename

    def descriptor(self) -> Dict[str, Any]:
        """The ``resources/list`` entry for this resource."""
        descriptor: Dict[str, Any] = {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": APP_MIME_TYPE,
        }
        # An empty csp is meaningful: it declares that the view needs no
        # external origins, which is the secure default the spec wants.
        descriptor["_meta"] = {"ui": {"csp": self.csp}}
        return descriptor

    def read(self) -> Dict[str, Any]:
        """The ``resources/read`` contents entry, with the HTML inlined."""
        return {
            "uri": self.uri,
            "mimeType": APP_MIME_TYPE,
            "text": self.path.read_text(encoding="utf-8"),
        }


#: Every UI resource this server serves.
UI_RESOURCES: Dict[str, UIResource] = {
    TRANSCRIPT_URI: UIResource(
        uri=TRANSCRIPT_URI,
        name="Meeting transcript",
        description=(
            "Speaker-attributed meeting transcript with per-speaker filtering, "
            "text search, and inline display of user corrections."
        ),
        filename="transcript.html",
        # No external origins: the view is zero-dependency and fetches nothing.
        csp={"resourceDomains": [], "frameDomains": [], "baseUriDomains": []},
    ),
}


def list_ui_resources() -> List[Dict[str, Any]]:
    """Descriptors for every available UI resource.

    SEP-1865 permits omitting UI-only resources from ``resources/list`` because
    discovery runs through tool metadata, but listing them keeps the set
    enumerable and inspectable, which is the auditability the spec asks for.
    """
    return [
        resource.descriptor()
        for resource in UI_RESOURCES.values()
        if resource.path.is_file()
    ]


def read_ui_resource(uri: str) -> Optional[Dict[str, Any]]:
    """Read one UI resource by URI, or None when unknown or missing on disk."""
    resource = UI_RESOURCES.get(uri)
    if not resource or not resource.path.is_file():
        return None
    return resource.read()
