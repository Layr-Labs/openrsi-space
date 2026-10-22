# Point-add circuit SDK

`crate::point_add_sdk` is trusted construction infrastructure. It contains no
point-addition or arithmetic implementation.

The candidate entry point is:

```rust
pub fn build() -> Vec<Op>
```

Start with `CircuitBuilder::new()` and call `declare_point_add_abi()` exactly
once. It declares four 256-element little-endian registers in this order:

1. quantum `target_x`;
2. quantum `target_y`;
3. classical `offset_x`;
4. classical `offset_y`.

The returned `PointAddRegisters` exposes those wires.

## Allocation

- `alloc_qubit`, `alloc_qubits`
- `alloc_bit`, `alloc_bits`
- `release_zero`, `release_zero_many`

`release_zero` emits no reset operation. It only makes a wire identifier
available for reuse. The caller must first return the qubit coherently to
`|0>`. Trusted simulation is authoritative.

## Gates

The builder exposes `x`, `z`, `cx`, `cz`, `swap`, `ccx`, `ccz`, conditional
variants, X-basis measurement/reset through `hmr`, and raw validated `Op`
emission through `emit`.

`inverse_ops` accepts only reversible operations. It rejects measurements,
resets, register operations, classical stores, condition-stack operations, and
debug operations.

`op_count` and `peak_live_qubits` are development diagnostics only. The trusted
evaluator independently computes all reported metrics.
