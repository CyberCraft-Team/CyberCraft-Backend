"""
CyberCraft settings package.

DJANGO_SETTINGS_MODULE stays `config.settings`; this module picks the
environment. base.py holds everything shared, dev.py and prod.py each
import it once, and nothing imports back into this package -- so unlike
the previous settings.py / settings_prod.py pair, there is no cycle and
no chance of one file silently overwriting the other's values.
"""

import os

if os.environ.get("PRODUCTION"):
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
