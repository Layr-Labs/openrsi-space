# Catalyst package

See [architecture](../../docs/architecture.md) for ownership and dependency direction.
`cli/` exposes commands, `contracts/` defines shared rules, `client/` speaks HTTP,
and `integrations/` connects Dungeness and Yukon. Root compatibility modules keep
existing verifier imports working; add implementation to its owning package.
