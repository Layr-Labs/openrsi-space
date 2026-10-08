# HTTPS on the existing EC2 verifier

The MVP endpoint is **https://35.92.254.142**. Nginx terminates TLS on port 443
and forwards requests to the existing screen-managed Catalyst API on
`127.0.0.1:8778`. No SSH tunnel or domain is needed by an HTTPS client.

The user obtained a trusted Let's Encrypt certificate for this public IP using
Certbot 5.8.0 with the `shortlived` profile and standalone HTTP validation.
The certificate and server private key are under
`/etc/letsencrypt/live/35.92.254.142/`. Keep the public IP assigned to this VM;
an IP change requires a matching certificate and a client URL update.

## Deployed configuration

- [Nginx configuration](../deploy/nginx/catalyst-https.conf) is installed at
  `/etc/nginx/sites-available/catalyst-https.conf` and enabled through
  `/etc/nginx/sites-enabled/catalyst-https.conf`.
- [Renewal hook](../deploy/certbot/reload-catalyst-nginx) is installed executable
  at `/etc/letsencrypt/renewal-hooks/deploy/reload-catalyst-nginx`.
- Nginx and the existing `snap.certbot.renew.timer` are enabled. Catalyst's API
  keeps its existing screen lifecycle; this setup does not add API boot startup.
- The freshly installed packaged Nginx default site is disabled. Nginx listens
  only on 443. Port 80 must remain available for Certbot's temporary validation
  server, including future unattended renewals.
- AWS inbound TCP 80 and 443 must remain reachable. Port 8778 stays bound to
  loopback. Requests require the existing Catalyst authentication.

API access/error request logging is disabled in the HTTPS virtual host, and
request/response proxy buffering to disk is disabled. The upload limit is 12 MiB,
matching the API's JSON body limit. Global Nginx configuration/startup diagnostics
and Certbot's certificate-management logs remain available.

User LLM credentials are not accepted by the current model-disabled MVP.
Their future memory-only lifecycle is specified in
[runtime requirements](runtime-platform-requirements.md). Server TLS keys and
ACME account state are operational certificate material, not user LLM credentials.

## Verification completed

On October 7, 2026:

- A connection from the Mac validated the public IP certificate with the default
  trust store and negotiated TLS 1.3, without bypassing certificate verification.
- An unauthenticated API request returned HTTP 401.
- An authenticated receipt lookup returned the independently verified scores
  `[10758874395, 0]` and the expected harness digest for existing evaluation
  `03586584-86c1-4b9d-9a09-1a13701efabe`, without starting a new evaluation.
- Certbot's renewal simulation passed and executed the Nginx configuration
  check and reload hook successfully.
- Stock `yukon run` retrieved the same receipt directly over public HTTPS after
  that reload. The server's job count remained one completed and two failed
  historical evaluations.

To repeat the renewal check:

```sh
ssh openclaw
sudo /snap/bin/certbot renew \
  --cert-name 35.92.254.142 \
  --dry-run --run-deploy-hooks \
  --no-random-sleep-on-renew --non-interactive
```

The deploy hook validates Nginx configuration before reloading it. Certbot's
standalone mode must be retained unless the renewal configuration is deliberately
migrated to another supported validation method.

## Client configuration

Yukon login is live against `https://api-dev.yukon.org`; use a dev Yukon key
or the existing local dev login. Production keys from `www.yukon.org` do not
work with this integration. See [deployment status](remote-vm.md).

```sh
export CATALYST_EVALUATOR_URL=https://35.92.254.142
export YUKON_API_URL=https://api-dev.yukon.org
unset CATALYST_API_TOKEN
# Use your existing Yukon login, or supply YUKON_API_TOKEN privately.
uv run --frozen catalyst yukon-run
```

This previews an existing receipt. Starting a harness still uses
`catalyst remote submit HARNESS_DIRECTORY --wait`.

HTTPS transport is verified and the GitHub workflow calls this URL directly.
Configuring its OIDC repository authorization and registering/testing the hosted Yukon
benchmark remain separate integration steps. See
[the end-to-end guide](github-actions-e2e.md).
