#!/bin/sh
set -eu

# Named volumes are empty on their first use and would otherwise hide the
# configuration and assets baked into the image.
if [ ! -f /app/config/pricing.json ]; then
    cp -a /seed-config/. /app/config/
fi

if [ ! -d /app/assets/pdf_templates ]; then
    cp -a /seed-assets/. /app/assets/
fi

exec "$@"
