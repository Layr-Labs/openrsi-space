# Reference pricing

`pricing.json` is the immutable comparison-rate schedule. Runtime validation and
budget projection live in `contracts/accounting.py`. Service-issued quotes bind
additional prices by digest; changing a schedule must not reinterpret old receipts.

Duration-priced cache writes use `cache_write_1h_tokens` as a subset of total
`cache_write_tokens`. The remainder uses the ordinary cache-write rate. New
duration-priced quotes require a runtime advertising `cache-duration-accounting-v1`;
missing duration evidence cannot be settled as a cheaper cache write. Historical
receipts without duration pricing keep their original accounting.
