#!/usr/bin/env bash
set -o errexit

pip install -r tsproj/requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

