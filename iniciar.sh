#!/bin/sh
# AulaCoach en Linux o Mac. Los docentes entran a la "Network URL" que aparece abajo.
cd "$(dirname "$0")"
exec python3 -m streamlit run app.py
