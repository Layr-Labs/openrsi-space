# Client

`transport.py` owns bounded HTTP and Yukon login sessions; `evaluations.py` owns
submission/polling/cancellation; `state.py` preserves retry IDs; `catalog.py`
handles public discovery and downloads. Validation belongs in `contracts/`.
