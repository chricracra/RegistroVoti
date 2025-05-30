#!/bin/bash
set -o errexit

# Comando per applicare le migrazioni
flask db upgrade

# Avvia l'applicazione con Gunicorn
gunicorn app:app
