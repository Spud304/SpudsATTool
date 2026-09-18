# Deploying behind an existing reverse proxy

[SETUP.md](SETUP.md) covers the standalone install where the bundled Caddy owns ports 80 and 443 and gets its own certificate. This page covers a box where another proxy already owns those ports. The tool then publishes no ports at all: Caddy joins the proxy's Docker network and serves plain HTTP there as `attool-caddy:80`, and the outer proxy terminates TLS and forwards to it.

The stack is otherwise identical: `caddy` (static frontend + routing), `web` (Django), `scheduler`, `db`, `redis`, all on the stack's own network. Only `caddy` is also attached to the proxy network.

## 1. Find the proxy's network

```bash
docker inspect <proxy container> --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

On the homelab this is `aa-docker-proxy-1` (Nginx Proxy Manager, from the `aa-docker` compose project) and the network is `aa-docker_default`.

## 2. Install

```bash
git clone <repo> attool && cd attool
make init
$EDITOR deploy/.env
```

Set in `deploy/.env`:

| Key | Value |
|---|---|
| `DOMAIN` | the public hostname; the homelab uses `at22.playwfire.org` |
| `PROXY_NETWORK` | the network from step 1, e.g. `aa-docker_default` |
| `PUBLIC_ORIGIN` | `https://$DOMAIN` (share links are built from it) |
| `EVE_CLIENT_ID`, `EVE_CLIENT_SECRET` | an EVE application whose callback is `https://$DOMAIN/auth/callback` |
| `ESI_CONTACT_EMAIL`, `TEAM_NAME`, `ADMIN_CHARACTER_IDS` | as in SETUP.md |
| `ACME_EMAIL` | any address; unused in this mode because Caddy issues no certificate |

Then:

```bash
make build
make up
make logs
```

When `PROXY_NETWORK` is set the Makefile adds `deploy/docker-compose.proxy.yml`, which removes Caddy's published ports, names the container `attool-caddy`, sets `SITE_ADDRESS=:80` and attaches it to the external network. `make build` builds the two images locally; `make up` pulls only the images it cannot build (Postgres, Redis).

Check from the host before touching the proxy:

```bash
docker run --rm --network aa-docker_default curlimages/curl -si -H "Host: at22.playwfire.org" http://attool-caddy/api/health | head -20
```

## 3. Add the host in Nginx Proxy Manager

Hosts → Proxy Hosts → Add:

- **Details.** Domain name `$DOMAIN`. Scheme `http`, forward hostname `attool-caddy`, port `80`. Turn on **Websockets Support** (it sets `proxy_http_version 1.1` and the `Upgrade` headers, which the event stream also needs). Leave **Cache Assets** off. **Block Common Exploits** is fine.
- **SSL.** Request a new Let's Encrypt certificate, **Force SSL**, **HTTP/2 Support**, **HSTS Enabled**. DNS for `$DOMAIN` must already resolve. On the homelab the zone is on Cloudflare with the proxy on (the existing `auth.playwfire.org` resolves to Cloudflare addresses), so `at22` should be set up the same way: an A record to the box's public IP, proxied, and the zone's SSL mode at Full (strict). Turn on **Always Use HTTPS** in the Cloudflare zone so plain `http://` requests redirect (Proxy Manager's Force SSL only sees traffic that reaches it over HTTP). Cloudflare passes the event stream through unchanged; it closes idle connections after 100 s and the stream sends a `ping` every 20 s, so that limit is not reached.
- **Advanced.** The scrim page holds a server-sent-events stream open per tab. nginx buffers proxied responses by default and would hold the events back, so paste:

```nginx
proxy_buffering off;
proxy_request_buffering off;
proxy_read_timeout 1h;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
```

Save. The first HTTPS request to `https://$DOMAIN/api/health` should return JSON, and `https://$DOMAIN/` the login page.

Why the headers matter: Django only trusts the request as HTTPS when `X-Forwarded-Proto: https` arrives, and the callback URL sent to EVE is built from the forwarded host. Caddy keeps these headers because the Caddyfile marks private-range clients as trusted proxies; without that it would overwrite them with `http`.

## 4. Hand-written nginx instead of Proxy Manager

The equivalent server block:

```nginx
server {
    listen 443 ssl http2;
    server_name at.example.org;
    # ssl_certificate ...; ssl_certificate_key ...;

    location / {
        proxy_pass http://attool-caddy:80;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 1h;
    }
}
```

The nginx container must be on the same Docker network as `attool-caddy`, or forward to a published port instead (add `ports:` back in a local override).

## 5. Operations

Same as SETUP.md: `make upgrade` (backup, then rebuild and restart), `make backup`, `make logs`. Because images are built locally, upgrading is `git pull && make build && make up`. Nightly dumps land in the `backups` volume. The backend image does not include `rclone`, so `BACKUP_RCLONE_REMOTE` only prints a warning today; copy the volume off the box by other means or leave it empty.

## Checklist for a first night

1. `https://$DOMAIN/api/health` returns `sde_build` and `sde_stale: false` (the scheduler downloads the SDE on first boot; this takes a few minutes).
2. Log in with an admin character, open Team, add the roster.
3. Open a scrim in two browsers; a change in one appears in the other within a second. If it only appears on reload, the proxy is buffering: re-check step 3's Advanced block.
4. Create a share link and open it in a private window.
