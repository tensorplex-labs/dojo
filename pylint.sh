#!/usr/bin/env bash

checks=(
"unused-import"            # W0611: Unused import
"unused-variable"          # W0612: Unused variable
"unused-argument"          # W0613: Unused argument
"unused-wildcard-import"   # W0614: Unused wildcard import
"unused-private-member"    # W0238: Unused private member
"unused-format-string-argument" # W1304: Unused format string argument
"unused-format-string-key"      # W1303: Unused format string key
"unreachable"              # W0101: Unreachable code
"unnecessary-pass"         # W0107: Unnecessary pass statement
"global-at-module-level"   # W0604: Using global at module level (redundant)
)

# Join the checks array into a comma-separated string
enabled_checks=$(IFS=,; echo "${checks[*]}")

files=$(git ls-files "*.py")
echo $files
ignore_files="--ignore=venv,node_modules,build,database/prisma,.nox,.venv"
args="--disable=all --enable=$enabled_checks"

pylint $ignore_files $args $files
