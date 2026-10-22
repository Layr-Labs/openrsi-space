# Deployment compatibility

`main` contains the versioned `v1` problem manifest. The existing hosted evaluator
at `https://3.21.93.126` uses the earlier unversioned manifest. A new manifest is
not interchangeable with a historical problem hash.

For that deployment, use a separate checkout of
`release/catalyst-prod-20261022-runtime-cleanup`. This branch retains the hosted
problem identity while receiving compatible cleanup backports. Check the service's
advertised problem identity before submitting.
The structural cleanup on `main` does not switch the deployed problem release.

Release the public package, private verifier and Yukon registration together when
changing problem identities or validity policies. Preserve historical receipt
verification and the registered benchmark workflow/upload path. Deployment
procedures and production configuration belong in `catalyst-verifier`.
