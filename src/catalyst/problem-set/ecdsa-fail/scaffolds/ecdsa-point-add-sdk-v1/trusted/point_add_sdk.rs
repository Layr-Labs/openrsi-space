//! Neutral circuit-construction SDK for the point-addition task.
//!
//! This module defines allocation, ABI declaration, raw operation emission,
//! common gates, zero-release wire reuse, and strict inversion of reversible
//! operation lists. It contains no arithmetic or point-addition algorithm.

use std::collections::BTreeSet;

use crate::circuit::{
    BitId, Op, OperationType, QubitId, RegisterId, NO_BIT,
};

pub const REGISTER_WIDTH: usize = 256;

#[derive(Clone, Debug)]
pub struct PointAddRegisters {
    pub target_x: Vec<QubitId>,
    pub target_y: Vec<QubitId>,
    pub offset_x: Vec<BitId>,
    pub offset_y: Vec<BitId>,
}

#[derive(Debug, Default)]
pub struct CircuitBuilder {
    ops: Vec<Op>,
    next_qubit: u64,
    next_bit: u64,
    next_register: u64,
    free_qubits: Vec<QubitId>,
    live_qubits: BTreeSet<QubitId>,
    peak_live_qubits: usize,
}

impl CircuitBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn alloc_qubit(&mut self) -> QubitId {
        let qubit = self.free_qubits.pop().unwrap_or_else(|| {
            let qubit = QubitId(self.next_qubit);
            self.next_qubit += 1;
            qubit
        });
        assert!(
            self.live_qubits.insert(qubit),
            "allocator returned an already-live qubit"
        );
        self.peak_live_qubits = self.peak_live_qubits.max(self.live_qubits.len());
        qubit
    }

    pub fn alloc_qubits(&mut self, count: usize) -> Vec<QubitId> {
        (0..count).map(|_| self.alloc_qubit()).collect()
    }

    pub fn alloc_bit(&mut self) -> BitId {
        let bit = BitId(self.next_bit);
        self.next_bit += 1;
        bit
    }

    pub fn alloc_bits(&mut self, count: usize) -> Vec<BitId> {
        (0..count).map(|_| self.alloc_bit()).collect()
    }

    /// Return a qubit wire to the allocator.
    ///
    /// This emits no reset. The caller must have coherently returned the qubit
    /// to |0>. Authoritative simulation determines whether the complete circuit
    /// is clean.
    pub fn release_zero(&mut self, qubit: QubitId) {
        assert!(
            self.live_qubits.remove(&qubit),
            "release_zero called for a qubit that is not live"
        );
        self.free_qubits.push(qubit);
    }

    pub fn release_zero_many(&mut self, qubits: &[QubitId]) {
        for &qubit in qubits {
            self.release_zero(qubit);
        }
    }

    pub fn declare_point_add_abi(&mut self) -> PointAddRegisters {
        let target_x = self.alloc_qubits(REGISTER_WIDTH);
        self.declare_qubit_register(&target_x);
        let target_y = self.alloc_qubits(REGISTER_WIDTH);
        self.declare_qubit_register(&target_y);
        let offset_x = self.alloc_bits(REGISTER_WIDTH);
        self.declare_bit_register(&offset_x);
        let offset_y = self.alloc_bits(REGISTER_WIDTH);
        self.declare_bit_register(&offset_y);
        PointAddRegisters {
            target_x,
            target_y,
            offset_x,
            offset_y,
        }
    }

    pub fn declare_qubit_register(&mut self, qubits: &[QubitId]) -> RegisterId {
        let register = self.alloc_register();
        for &qubit in qubits {
            let mut op = Op::empty();
            op.kind = OperationType::AppendToRegister;
            op.q_target = qubit;
            op.r_target = register;
            self.emit(op);
        }
        self.emit_register(register);
        register
    }

    pub fn declare_bit_register(&mut self, bits: &[BitId]) -> RegisterId {
        let register = self.alloc_register();
        for &bit in bits {
            let mut op = Op::empty();
            op.kind = OperationType::AppendToRegister;
            op.c_target = bit;
            op.r_target = register;
            self.emit(op);
        }
        self.emit_register(register);
        register
    }

    fn alloc_register(&mut self) -> RegisterId {
        let register = RegisterId(self.next_register);
        self.next_register += 1;
        register
    }

    fn emit_register(&mut self, register: RegisterId) {
        let mut op = Op::empty();
        op.kind = OperationType::Register;
        op.r_target = register;
        self.emit(op);
    }

    pub fn emit(&mut self, op: Op) {
        op.validate();
        self.ops.push(op);
    }

    fn one_qubit(&mut self, kind: OperationType, target: QubitId, condition: BitId) {
        let mut op = Op::empty();
        op.kind = kind;
        op.q_target = target;
        op.c_condition = condition;
        self.emit(op);
    }

    fn two_qubit(
        &mut self,
        kind: OperationType,
        control: QubitId,
        target: QubitId,
        condition: BitId,
    ) {
        let mut op = Op::empty();
        op.kind = kind;
        op.q_control1 = control;
        op.q_target = target;
        op.c_condition = condition;
        self.emit(op);
    }

    fn three_qubit(
        &mut self,
        kind: OperationType,
        control1: QubitId,
        control2: QubitId,
        target: QubitId,
        condition: BitId,
    ) {
        let mut op = Op::empty();
        op.kind = kind;
        op.q_control1 = control1;
        op.q_control2 = control2;
        op.q_target = target;
        op.c_condition = condition;
        self.emit(op);
    }

    pub fn x(&mut self, target: QubitId) {
        self.one_qubit(OperationType::X, target, NO_BIT);
    }

    pub fn x_if(&mut self, target: QubitId, condition: BitId) {
        self.one_qubit(OperationType::X, target, condition);
    }

    pub fn z(&mut self, target: QubitId) {
        self.one_qubit(OperationType::Z, target, NO_BIT);
    }

    pub fn z_if(&mut self, target: QubitId, condition: BitId) {
        self.one_qubit(OperationType::Z, target, condition);
    }

    pub fn cx(&mut self, control: QubitId, target: QubitId) {
        self.two_qubit(OperationType::CX, control, target, NO_BIT);
    }

    pub fn cx_if(&mut self, control: QubitId, target: QubitId, condition: BitId) {
        self.two_qubit(OperationType::CX, control, target, condition);
    }

    pub fn cz(&mut self, control: QubitId, target: QubitId) {
        self.two_qubit(OperationType::CZ, control, target, NO_BIT);
    }

    pub fn cz_if(&mut self, control: QubitId, target: QubitId, condition: BitId) {
        self.two_qubit(OperationType::CZ, control, target, condition);
    }

    pub fn swap(&mut self, left: QubitId, right: QubitId) {
        self.two_qubit(OperationType::Swap, left, right, NO_BIT);
    }

    pub fn ccx(&mut self, control1: QubitId, control2: QubitId, target: QubitId) {
        self.three_qubit(OperationType::CCX, control1, control2, target, NO_BIT);
    }

    pub fn ccx_if(
        &mut self,
        control1: QubitId,
        control2: QubitId,
        target: QubitId,
        condition: BitId,
    ) {
        self.three_qubit(
            OperationType::CCX,
            control1,
            control2,
            target,
            condition,
        );
    }

    pub fn ccz(&mut self, control1: QubitId, control2: QubitId, target: QubitId) {
        self.three_qubit(OperationType::CCZ, control1, control2, target, NO_BIT);
    }

    pub fn hmr(&mut self, target: QubitId, result: BitId) {
        let mut op = Op::empty();
        op.kind = OperationType::Hmr;
        op.q_target = target;
        op.c_target = result;
        self.emit(op);
    }

    pub fn negate_phase(&mut self) {
        let mut op = Op::empty();
        op.kind = OperationType::Neg;
        self.emit(op);
    }

    pub fn op_count(&self) -> usize {
        self.ops.len()
    }

    pub fn peak_live_qubits(&self) -> usize {
        self.peak_live_qubits
    }

    pub fn finish(self) -> Vec<Op> {
        self.ops
    }
}

/// Return the exact inverse of a block containing only reversible operations.
///
/// Every currently supported reversible gate is self-inverse, so inversion is
/// reversal of operation order. Measurements, resets, register declarations,
/// classical stores, condition-stack operations, and debug operations are
/// rejected.
pub fn inverse_ops(ops: &[Op]) -> Result<Vec<Op>, String> {
    for op in ops {
        match op.kind {
            OperationType::Neg
            | OperationType::X
            | OperationType::Z
            | OperationType::CX
            | OperationType::CZ
            | OperationType::Swap
            | OperationType::CCX
            | OperationType::CCZ => {}
            other => {
                return Err(format!(
                    "operation {:?} is not accepted by the strict inverse builder",
                    other
                ));
            }
        }
    }
    Ok(ops.iter().rev().copied().collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abi_has_expected_shape() {
        let mut builder = CircuitBuilder::new();
        let registers = builder.declare_point_add_abi();
        assert_eq!(registers.target_x.len(), REGISTER_WIDTH);
        assert_eq!(registers.target_y.len(), REGISTER_WIDTH);
        assert_eq!(registers.offset_x.len(), REGISTER_WIDTH);
        assert_eq!(registers.offset_y.len(), REGISTER_WIDTH);
        assert_eq!(builder.peak_live_qubits(), 2 * REGISTER_WIDTH);
    }

    #[test]
    fn release_reuses_without_emitting_reset() {
        let mut builder = CircuitBuilder::new();
        let qubit = builder.alloc_qubit();
        builder.release_zero(qubit);
        assert_eq!(builder.alloc_qubit(), qubit);
        assert_eq!(builder.op_count(), 0);
    }

    #[test]
    fn inverse_rejects_measurement() {
        let mut op = Op::empty();
        op.kind = OperationType::Hmr;
        op.q_target = QubitId(0);
        op.c_target = BitId(0);
        assert!(inverse_ops(&[op]).is_err());
    }
}
