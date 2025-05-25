#!/bin/bash
# Script de inicio para Render

# Iniciar con gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app 