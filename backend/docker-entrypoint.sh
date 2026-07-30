#!/bin/sh
set -eu

# Named volumes are empty on their first use and would otherwise hide the
# configuration and assets baked into the image.
if [ ! -f /app/config/pricing.json ]; then
    cp -a /seed-config/. /app/config/
fi

# Pricing is versioned product configuration; templates remain user-managed.
cp /seed-config/pricing.json /app/config/pricing.json

# Apply targeted schema migrations without replacing user-managed templates.
python /app/migrate_templates.py

if [ ! -d /app/assets/pdf_templates ]; then
    cp -a /seed-assets/. /app/assets/
fi

if [ ! -f /app/assets/reference/comparison-v3.pdf ]; then
    mkdir -p /app/assets/reference
    cp -a /seed-reference/reference/. /app/assets/reference/
fi

exec "$@"
