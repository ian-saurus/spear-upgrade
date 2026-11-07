#!/bin/bash
# Manual deploy: sync play-copy to home dir and push to Vercel production.
set -e
cd "$(dirname "$0")"
cp index.html /home/ian/spear-upgrade.html
vercel deploy --yes --prod
