"""Report generator: writes audit output to clients/[slug]/output/.

Produces violations.csv, canonical_conflicts.csv, unclassified_urls.csv,
and summary.md.
"""

import pandas as pd
