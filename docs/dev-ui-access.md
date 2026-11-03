# Protected development UI

A Vercel preview may be protected by a shared-password form. In a browser, open
the supplied preview URL and enter the password provided separately by an
operator. Agents using an HTTP client can POST the form field
`_vercel_password` to that same protected page and retain the returned cookies
for subsequent requests. Follow the form action and redirects on the trusted
preview host; do not send the password to other origins. Do not put passwords,
cookies or bypass tokens in harness source or submitted evidence.

This authenticates access to the preview only, not Yukon or model inference.
A sandbox failure before curl starts is a local tooling problem; do not disable
sandbox isolation to work around it. Use an available browser instead.
