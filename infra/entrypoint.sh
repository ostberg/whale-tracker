#!/bin/sh
# The job image's entrypoint (W-042). Container Apps jobs get their arguments through the az CLI, whose own
# parser refuses a list element that starts with "--" (so `--args collect sec --apply` fails). The deploy
# therefore passes the arguments as ONE string, "collect sec --apply", and this script splits it on spaces.
# Globbing is off, so an argument is never expanded against the file system.
set -f
set -- $*
exec python -m whales "$@"
