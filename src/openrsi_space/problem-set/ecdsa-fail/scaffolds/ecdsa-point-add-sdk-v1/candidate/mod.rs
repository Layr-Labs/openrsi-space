use crate::circuit::Op;
use crate::point_add_sdk::CircuitBuilder;

/// Build the point-addition circuit.
///
/// The starter declares the required four-register ABI and intentionally emits
/// no point-addition algorithm. Add any modules or architecture you need under
/// `src/point_add/`.
pub fn build() -> Vec<Op> {
    let mut circuit = CircuitBuilder::new();
    let _registers = circuit.declare_point_add_abi();
    circuit.finish()
}
