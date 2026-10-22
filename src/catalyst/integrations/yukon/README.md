# Yukon integration

`authentication.py` establishes workflow identity and problem setup; `receipts.py`
retrieves and checks retained results; `submission.py` invokes Yukon and registers
the execution binding. Receipt retrieval never starts a new paid evaluation.
