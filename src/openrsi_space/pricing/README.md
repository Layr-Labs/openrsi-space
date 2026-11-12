# Reference pricing

`pricing.json` preserves the existing comparison-rate entries.
`contracts/model_registry.py` defines canonical model identities, exact provider
IDs, and reference rates for newly supported models. `pricing_schedule()` derives
missing route entries from that registry without rewriting existing entries.
Adding a new supported pair updates setup, evidence matching and public policy
from the same registry. Tests require every registered route to have a price.
These are pinned reference credits, not a live provider quote or a grant of access.
Saved schedules and receipts retain their own rates and digests. Runtime validation and
budget projection live in `contracts/accounting.py`. Service-issued quotes bind
additional prices by digest; changing a schedule must not reinterpret old receipts.

Duration-priced cache writes use `cache_write_1h_tokens` as a subset of total
`cache_write_tokens`. The remainder uses the ordinary cache-write rate. New
duration-priced quotes require a runtime advertising `cache-duration-accounting-v1`;
missing duration evidence cannot be settled as a cheaper cache write. Historical
receipts without duration pricing keep their original accounting.
