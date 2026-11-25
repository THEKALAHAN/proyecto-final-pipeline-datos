"""Tablero de solicitudes 311 de Nueva York.

Lee únicamente las tablas de indicadores que el pipeline deja en la zona de servicio
(servicio_nyc311.db). No hace agregaciones ni cálculos: solo selecciona, ordena y dibuja.

Ejecutar desde la carpeta del proyecto:
    .venv\\Scripts\\python dashboard\\app.py
y abrir http://127.0.0.1:8050
"""
import base64
import os
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

RAIZ = Path(__file__).resolve().parent.parent
DB_SERVICIO = Path(os.environ.get("DB_SERVICIO", RAIZ / "servicio_nyc311.db"))
DIAGRAMA = RAIZ / "diagrama_pipeline.png"

# Paleta (un solo tono para magnitudes, gris para contexto, verde solo para estado "verificado")
AZUL = "#2a78d6"
GRIS_CONTEXTO = "#d3d2cc"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_SUAVE = "#898781"
REJILLA = "#e1e0d9"
EJE = "#c3c2b7"
SUPERFICIE = "#fcfcfb"
ESCALA_AZUL = [[0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1, "#0d366b"]]
FUENTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# --------------------------------------------------------------------------- lectura de la zona de servicio
def leer(consulta):
    with sqlite3.connect(DB_SERVICIO) as conn:
        return pd.read_sql(consulta, conn)


def leer_metadatos():
    df = leer("SELECT clave, valor FROM ind_metadatos")
    return dict(zip(df["clave"], df["valor"]))


def duracion(horas):
    """Formato de presentación (no cálculo): horas o días según la magnitud."""
    if pd.isna(horas):
        return "sin cierres"
    texto = f"{horas:.1f} h" if horas < 48 else f"{horas / 24:.1f} días"
    return texto.replace(".", ",")


def numero(valor, decimales=0):
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- estilo común de los gráficos
def estilo(fig, alto, margen_izq=10):
    fig.update_layout(
        height=alto,
        margin=dict(l=margen_izq, r=24, t=8, b=40),
        paper_bgcolor=SUPERFICIE,
        plot_bgcolor=SUPERFICIE,
        font=dict(family=FUENTE, size=13, color=TINTA_2),
        hoverlabel=dict(bgcolor="white", bordercolor=REJILLA, font=dict(family=FUENTE, size=13, color=TINTA)),
        showlegend=False,
        barcornerradius=4,
        separators=",.",   # coma decimal y punto de miles
    )
    fig.update_xaxes(gridcolor=REJILLA, linecolor=EJE, zeroline=False, tickfont=dict(color=TINTA_SUAVE))
    fig.update_yaxes(gridcolor=REJILLA, linecolor=EJE, zeroline=False, tickfont=dict(color=TINTA_2))
    return fig


def fig_problemas():
    df = leer("SELECT * FROM ind_problemas_principales WHERE ranking <= 10 ORDER BY ranking")
    destacado = df["ranking"] <= 3
    fig = go.Figure(go.Bar(
        x=df["solicitudes"], y=df["complaint_type"], orientation="h",
        marker=dict(color=[AZUL if d else GRIS_CONTEXTO for d in destacado], line=dict(color=SUPERFICIE, width=2)),
        text=[f"{p:.1f}%".replace(".", ",") if d else "" for p, d in zip(df["pct_total"], destacado)],
        textposition="outside", textfont=dict(color=TINTA, size=13), cliponaxis=False,
        customdata=list(zip(df["pct_total"], df["pct_cerradas"], df["mediana_horas"].map(duracion))),
        hovertemplate="<b>%{y}</b><br>%{x:,} solicitudes (%{customdata[0]}% del total)"
                      "<br>Cerradas: %{customdata[1]}%<br>Mediana de resolución: %{customdata[2]}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(title=dict(text="Solicitudes en la muestra", font=dict(color=TINTA_SUAVE)),
                     range=[0, df["solicitudes"].max() * 1.18])   # espacio para la etiqueta de la barra más larga
    return estilo(fig, 430), df


def fig_agencias(metrica):
    df = leer(f"SELECT * FROM ind_tiempo_por_agencia WHERE muestra_suficiente = 1 ORDER BY {metrica}")
    etiquetas = [""] * len(df)
    if len(df):
        etiquetas[0] = duracion(df[metrica].iloc[0])
        etiquetas[-1] = duracion(df[metrica].iloc[-1])
    fig = go.Figure(go.Bar(
        x=df[metrica], y=df["agency"], orientation="h",
        marker=dict(color=AZUL, line=dict(color=SUPERFICIE, width=2)),
        text=etiquetas, textposition="outside", textfont=dict(color=TINTA, size=13), cliponaxis=False,
        customdata=list(zip(df["agency_name"], df["cerradas"], df["pct_cerradas"], df[metrica].map(duracion))),
        hovertemplate="<b>%{y}</b> · %{customdata[0]}<br>%{customdata[3]}"
                      "<br>%{customdata[1]:,} solicitudes cerradas (%{customdata[2]}%)<extra></extra>",
    ))
    nombre = {"mediana_horas": "Mediana", "p90_horas": "Percentil 90", "promedio_horas": "Promedio"}[metrica]
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(range=[0, df[metrica].max() * 1.22] if len(df) else None, title=dict(text=f"{nombre} de horas hasta el cierre", font=dict(color=TINTA_SUAVE)))
    return estilo(fig, 430), df


def fig_mapa(metrica):
    df = leer("SELECT * FROM ind_distrito_problema ORDER BY orden_problema, borough")
    orden_problemas = df.drop_duplicates("complaint_type")["complaint_type"].tolist()
    etiquetas = {"solicitudes": "Solicitudes", "mediana_horas": "Mediana de horas hasta el cierre",
                 "pct_cerradas": "% de solicitudes cerradas"}
    fig = go.Figure(go.Heatmap(
        x=df["complaint_type"], y=df["borough"], z=df[metrica],
        colorscale=ESCALA_AZUL, xgap=2, ygap=2,
        colorbar=dict(title=dict(text=etiquetas[metrica], side="right", font=dict(color=TINTA_SUAVE)),
                      thickness=12, outlinewidth=0, tickfont=dict(color=TINTA_SUAVE)),
        customdata=list(zip(df["solicitudes"], df["mediana_horas"].map(duracion), df["pct_cerradas"])),
        hovertemplate="<b>%{y}</b> · %{x}<br>%{customdata[0]:,} solicitudes"
                      "<br>Mediana de resolución: %{customdata[1]}<br>Cerradas: %{customdata[2]}%<extra></extra>",
    ))
    fig.update_xaxes(categoryorder="array", categoryarray=orden_problemas, showgrid=False, tickangle=-30)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    estilo(fig, 400)
    fig.update_layout(margin=dict(b=110))
    return fig, df


def fig_capa_rapida():
    df = leer("SELECT * FROM ind_capa_rapida ORDER BY inicio_ventana")
    fig = go.Figure(go.Scatter(
        x=pd.to_datetime(df["inicio_ventana"]), y=df["total_solicitudes"], mode="lines+markers",
        line=dict(color=AZUL, width=2), marker=dict(size=8, color=AZUL, line=dict(color=SUPERFICIE, width=2)),
        customdata=df["problema_principal"],
        hovertemplate="%{y} solicitudes<br>Problema principal: %{customdata}<extra></extra>",
    ))
    dia = df["inicio_ventana"].iloc[0][:10] if len(df) else ""
    fig.update_xaxes(showgrid=False, showspikes=True, spikemode="across", spikecolor=EJE, spikethickness=1,
                     tickformat="%H:%M", hoverformat="%H:%M", title=dict(text=f"Hora de creación ({dia})", font=dict(color=TINTA_SUAVE)))
    fig.update_yaxes(title=dict(text="Solicitudes por ventana de 15 min", font=dict(color=TINTA_SUAVE)), rangemode="tozero")
    estilo(fig, 360)
    fig.update_layout(hovermode="x unified")
    return fig, df


# --------------------------------------------------------------------------- piezas de la interfaz
def celda(valor):
    """Números con formato en español (punto de miles, coma decimal)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or pd.isna(valor):
        return valor
    return numero(valor, 0 if float(valor).is_integer() else 1)


def tabla(df, columnas, abierta=False):
    """Vista de tabla equivalente a cada gráfico (accesible y para leer los valores exactos)."""
    encabezado = html.Tr([html.Th(titulo) for titulo in columnas.values()])
    filas = [html.Tr([html.Td(celda(fila[col])) for col in columnas]) for _, fila in df.iterrows()]
    return html.Details([
        html.Summary("Ver tabla de datos"),
        html.Div(html.Table([html.Thead(encabezado), html.Tbody(filas)], className="tabla"), className="tabla-scroll"),
    ], className="detalle-tabla", open=abierta)


def tarjeta(titulo, pregunta, contenido, controles=None, nota=None):
    return html.Section([
        html.Div([
            html.Div([html.H3(titulo), html.P(pregunta, className="tarjeta-pregunta")]),
            controles,
        ], className="tarjeta-encabezado"),
        *contenido,
        html.P(nota, className="nota") if nota else None,
    ], className="tarjeta")


def selector(id_, opciones, valor):
    return dcc.RadioItems(id=id_, options=[{"label": e, "value": v} for v, e in opciones], value=valor,
                          className="selector", inline=True)


def kpi(valor, etiqueta):
    return html.Div([html.Div(valor, className="kpi-valor"), html.Div(etiqueta, className="kpi-etiqueta")], className="kpi")


def imagen_diagrama():
    if not DIAGRAMA.exists():
        return html.P("Ejecuta el cuaderno para generar diagrama_pipeline.png.", className="nota")
    datos = base64.b64encode(DIAGRAMA.read_bytes()).decode("ascii")
    return html.Img(src=f"data:image/png;base64,{datos}", alt="Diagrama del pipeline de datos", className="diagrama")


def seccion_indicadores(meta):
    fig_p, df_p = fig_problemas()
    fig_a, df_a = fig_agencias("mediana_horas")
    fig_m, df_m = fig_mapa("solicitudes")
    df_d = leer("SELECT * FROM ind_distritos ORDER BY solicitudes DESC")
    return html.Div([
        html.Div([
            tarjeta("1. Principales problemas reportados", "¿Qué reportan más los ciudadanos?", [
                dcc.Graph(figure=fig_p, config={"displayModeBar": False}),
                tabla(df_p.assign(mediana=df_p["mediana_horas"].map(duracion)),
                      {"ranking": "#", "complaint_type": "Problema", "solicitudes": "Solicitudes",
                       "pct_total": "% del total", "pct_acumulado": "% acumulado", "pct_cerradas": "% cerradas",
                       "mediana": "Mediana de resolución"}),
            ], nota=f"Los 3 problemas en azul concentran el {meta['pct_top3']} de las solicitudes."),
            tarjeta("2. Tiempo de resolución por agencia", "¿Qué agencias resuelven más rápido?", [
                dcc.Graph(id="grafico-agencias", figure=fig_a, config={"displayModeBar": False}),
                html.Div(id="tabla-agencias", children=tabla_agencias(df_a, "mediana_horas")),
            ], controles=selector("metrica-agencias", [("mediana_horas", "Mediana"), ("p90_horas", "Percentil 90")],
                                  "mediana_horas"),
               nota=f"Solo agencias con al menos {meta['min_cerradas_agencia']} solicitudes cerradas. "
                    f"Más rápida: {meta['agencia_rapida']}; más lenta: {meta['agencia_lenta']}. "
                    "Una mediana cercana a 0 h significa que la mayoría de solicitudes se cierran casi al recibirse."),
        ], className="rejilla-2"),
        tarjeta("3. Problemas por distrito", "¿Cómo cambian el volumen y los tiempos según la ubicación?", [
            dcc.Graph(id="grafico-mapa", figure=fig_m, config={"displayModeBar": False}),
            html.Div(id="tabla-mapa", children=tabla_mapa(df_m)),
        ], controles=selector("metrica-mapa", [("solicitudes", "Solicitudes"), ("mediana_horas", "Mediana de resolución"),
                                               ("pct_cerradas", "% cerradas")], "solicitudes"),
           nota=f"Los 10 problemas más frecuentes. Distrito más rápido: {meta['distrito_rapido']}; "
                f"más lento: {meta['distrito_lento']}."),
        tarjeta("Resumen por distrito", "Volumen y tiempos de cada distrito", [
            tabla(abierta=True, df=df_d, columnas={"borough": "Distrito", "solicitudes": "Solicitudes", "pct_total": "% del total",
                         "pct_cerradas": "% cerradas", "mediana_texto": "Mediana de resolución"}),
        ]),
    ])


def tabla_agencias(df, metrica):
    return tabla(df.assign(valor=df[metrica].map(duracion)),
                 {"agency": "Agencia", "agency_name": "Nombre", "cerradas": "Cerradas",
                  "pct_cerradas": "% cerradas", "valor": "Tiempo"})


def tabla_mapa(df):
    return tabla(df.assign(mediana=df["mediana_horas"].map(duracion)),
                 {"borough": "Distrito", "complaint_type": "Problema", "solicitudes": "Solicitudes",
                  "pct_cerradas": "% cerradas", "mediana": "Mediana de resolución"})


def seccion_pipeline():
    etapas = leer("SELECT * FROM ind_pipeline ORDER BY orden")
    tarjetas = []
    for _, e in etapas.iterrows():
        verificado = ("coinciden" in e["detalle"] and e["detalle"].rstrip().endswith("Sí")) or e["valor"] == "EXITOSO"
        tarjetas.append(html.Div([
            html.Div([html.Span(str(e["orden"]), className="etapa-numero"), html.Span(e["etapa"], className="etapa-nombre")],
                     className="etapa-cabecera"),
            html.Div(e["valor"], className="etapa-valor"),
            html.Div(e["indicador"], className="etapa-indicador"),
            html.P(e["detalle"], className="etapa-detalle"),
            html.Div([html.Span("✓", className="icono"), "Verificado"], className="estado-ok") if verificado else None,
        ], className="etapa"))
    return html.Div([
        tarjeta("Arquitectura del pipeline", "De la API de NYC 311 al tablero (arquitectura lambda)", [
            imagen_diagrama(),
            html.Ul([
                html.Li([html.B("Capa batch: "), "API → zona raw (JSONL + manifiesto) → Kafka → HDFS → MapReduce y Spark → "
                         "zona curada en Parquet → validaciones, marca de agua y carga idempotente en SQLite."]),
                html.Li([html.B("Capa rápida: "), "Spark Structured Streaming agrega ventanas de 15 minutos con marca de agua "
                         "de 1 hora y checkpoint, y las escribe en la misma base de servicio."]),
                html.Li([html.B("Zona de servicio: "), "los indicadores se calculan en el pipeline y se guardan como tablas; "
                         "este tablero solo las lee."]),
            ], className="lista"),
        ]),
        html.H3("Evidencias de cada etapa", className="subtitulo-seccion"),
        html.Div(tarjetas, className="rejilla-etapas"),
    ])


def seccion_capa_rapida():
    fig, df = fig_capa_rapida()
    return tarjeta("Capa rápida: solicitudes por ventana de 15 minutos",
                   "Resultado de Spark Structured Streaming (2 micro-lotes, con reinicio desde el checkpoint)", [
                       dcc.Graph(figure=fig, config={"displayModeBar": False}),
                       tabla(df, {"inicio_ventana": "Inicio", "fin_ventana": "Fin", "total_solicitudes": "Solicitudes",
                                  "problema_principal": "Problema principal"}),
                   ], nota="En la arquitectura lambda esta capa cubre lo más reciente mientras llega el siguiente lote batch.")


def construir_layout():
    """Se evalúa en cada carga de página: si el pipeline se vuelve a ejecutar, el tablero muestra los datos nuevos."""
    if not DB_SERVICIO.exists():
        return html.Main(html.P(f"No se encontró {DB_SERVICIO}. Ejecuta primero el cuaderno Final_Datos_Masivos.ipynb."),
                         className="contenedor")
    meta = leer_metadatos()
    return html.Main([
        html.Header([
            html.P("Solicitudes ciudadanas 311 · Nueva York", className="antetitulo"),
            html.H1(meta["titular"]),
            html.P(meta["pregunta"], className="pregunta"),
            html.P([
                html.Span(["Fuente: ", html.A(f"{meta['fuente']} ({meta['dataset']})", href=meta["url_fuente"], target="_blank")]),
                html.Span(f"Periodo: {meta['fecha_inicio']} a {meta['fecha_corte'][:10]}"),
                html.Span(f"Fecha de corte de las cifras: {meta['fecha_corte'].replace('T', ' ')}"),
            ], className="meta"),
        ], className="encabezado"),
        html.Div([
            kpi(meta["total_solicitudes"], "solicitudes analizadas"),
            kpi(meta["pct_cerradas"], "ya cerradas"),
            kpi(meta["mediana_global"], "mediana hasta el cierre"),
            kpi(meta["num_tipos"], "tipos de problema"),
            kpi(meta["num_agencias"], "agencias responsables"),
        ], className="kpis"),
        dcc.Tabs([
            dcc.Tab(seccion_indicadores(meta), label="Indicadores", value="indicadores",
                    className="pestana", selected_className="pestana-activa"),
            dcc.Tab(seccion_pipeline(), label="Cómo se construyó", value="pipeline",
                    className="pestana", selected_className="pestana-activa"),
            dcc.Tab(seccion_capa_rapida(), label="Capa rápida (streaming)", value="rapida",
                    className="pestana", selected_className="pestana-activa"),
        ], value=os.environ.get("PESTANA_INICIAL", "indicadores"), className="pestanas"),
        html.Footer([
            html.P([f"Fuente: {meta['fuente']}, dataset {meta['dataset']}. Fecha de corte: {meta['fecha_corte'].replace('T', ' ')}. "
                    f"Ingesta: {meta['fecha_ingesta']}. Muestra de {meta['total_solicitudes']} solicitudes repartidas en el periodo."]),
            html.P("Las cifras se leen ya calculadas de la zona de servicio (servicio_nyc311.db); el tablero no realiza cálculos. "
                   "Los tiempos de resolución consideran solo solicitudes cerradas."),
        ], className="pie"),
    ], className="contenedor")


# --------------------------------------------------------------------------- aplicación
app = Dash(__name__, title="Solicitudes 311 NYC",
           meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])
app.layout = construir_layout


@app.callback(Output("grafico-agencias", "figure"), Output("tabla-agencias", "children"), Input("metrica-agencias", "value"))
def actualizar_agencias(metrica):
    fig, df = fig_agencias(metrica)
    return fig, tabla_agencias(df, metrica)


@app.callback(Output("grafico-mapa", "figure"), Input("metrica-mapa", "value"))
def actualizar_mapa(metrica):
    return fig_mapa(metrica)[0]


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PUERTO_TABLERO", 8050)))
