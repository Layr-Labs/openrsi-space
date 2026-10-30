# The secp256k1 Point-Addition Challenge

Build a reversible circuit that overwrites a quantum affine point with its sum
with a classical affine offset on secp256k1.

Your `src/point_add/` module must export:

```rust
pub fn build() -> Vec<Op>
```

The trusted circuit builder calls this as `point_add::build()`. The upstream
circuit interface and evaluator are pinned to commit
`62ae3d00d1e01d7bc640b5163cfea8dabffd8392`. Each new research run starts from a
**blank scaffold**, not that commit's point-addition implementation.

The starter declares four 256-element little-endian registers in this order:

1. `target_x`: quantum input/output;
2. `target_y`: quantum input/output;
3. `offset_x`: classical input;
4. `offset_y`: classical input.

For every sampled pair of non-infinity curve points with different
x-coordinates, transform:

```text
(target_x, target_y) := (target_x, target_y) + (offset_x, offset_y)
```

All ancillas must be uncomputed before being freed, and all non-output qubits
must end in zero. The circuit must leave no phase garbage; running it followed
by its gate-reversed inverse must restore the original state.
The trusted evaluator derives its test points from the emitted operation
stream. Validation proceeds through 1, 64, 512 and 9,024 shots, stopping on
failure. Only a candidate passing all 9,024 shots is valid.

Among valid candidates, minimize:

```text
average executed Toffoli count * peak qubit count
```

The scaffold declares the required registers but contains **no point-addition
algorithm and no valid baseline score**. Build a valid circuit before saving
a best candidate. `POINT_ADD_SDK.md` documents `crate::point_add_sdk`, the
trusted neutral helpers for declaring registers, allocating wires and emitting
gates. It contains no point-addition or arithmetic implementation.

You may replace the stub, add files under `src/point_add/`, or emit operations
directly from `build()`. Only
`src/point_add/` is collected as the candidate. Do not modify the trusted
builder, evaluator, dependencies or benchmark scripts, or forge their outputs.

Use `evaluate` for feedback during a research run and retain your best verified
candidate after the first successful check. For an equivalent local starting
workspace, use `openrsi-space local run` with the pinned Dungeness runtime.
Papers, general methods and the pinned baseline are permitted. Importing or
replaying existing ECDSA GitHub/leaderboard solutions, including answers embedded
in harness instructions or knowledge files, is prohibited.

Continue researching and improving; do not terminate voluntarily. The
environment will stop the run when its resource limits are reached.

See [the upstream review](../../../docs/ecdsa-upstream.md) for the mathematical
requirements and execution pin. The scaffold, neutral SDK and progressive
validation are selected by the trusted problem package and pinned runtime.
Harness source cannot select a different starting workspace or verifier.
