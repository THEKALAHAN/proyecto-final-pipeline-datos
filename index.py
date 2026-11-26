"""Punto de entrada para Vercel.

Vercel busca en la raíz un archivo index.py con una aplicación WSGI llamada `app`.
El tablero de Dash corre sobre Flask, así que se expone su servidor Flask.
Para ejecutar el tablero en local se sigue usando: .venv\\Scripts\\python dashboard\\app.py
"""
from dashboard.app import server as app  # noqa: F401
