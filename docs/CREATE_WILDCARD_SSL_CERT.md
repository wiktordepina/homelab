# Create wildcard domain certificates with certbot (DNS-01 challenge)

Run below on nginx reverse proxy node:

```shell
/opt/certbot/bin/certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /opt/certbot/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d matagoth.com \
  -d *.homelab.matagoth.com
```
