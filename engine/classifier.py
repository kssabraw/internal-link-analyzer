"""URL classifier: maps a raw URL to a PageClassification.

Reads the client config to match URL slug tokens against known services,
locations, subservices, and neighborhoods. Returns PageType.UNKNOWN for
any URL that cannot be matched — never guesses.
"""

import pandas as pd
