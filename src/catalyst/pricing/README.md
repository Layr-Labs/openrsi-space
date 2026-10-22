# Reference pricing

`pricing.json` is the immutable comparison-rate schedule. Runtime validation and
budget projection live in `contracts/accounting.py`. Service-issued quotes bind
additional prices by digest; changing a schedule must not reinterpret old receipts.
