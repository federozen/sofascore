# 🔬 Scout — Chat de Fútbol

Chat conversacional para consultar datos de fútbol en tiempo real usando **SofaScore** como fuente y **Claude** para interpretar preguntas y generar respuestas.

## ¿Qué puede responder?

| Tipo de consulta | Ejemplo |
|---|---|
| Próximos partidos de un equipo | *¿Cuándo juega River?* |
| Resultados recientes | *Últimos resultados de Boca* |
| Tabla de posiciones | *Tabla de la Liga Profesional* |
| Estadísticas de jugador | *Stats de Messi esta temporada* |
| Plantel de un equipo | *Plantel de Vélez* |
| Goleadores de una liga | *Goleadores de la Champions* |
| Asistidores | *Asistidores de la Premier* |
| Info de equipo | *Info sobre Estudiantes* |
| Stats del equipo en la temporada | *Estadísticas de Racing esta temporada* |

## Instalación local

```bash
git clone https://github.com/TU_USUARIO/scout.git
cd scout
pip install -r requirements.txt
streamlit run scout.py
```

Necesitás una **API Key de Anthropic** ([conseguila acá](https://console.anthropic.com/)).

## Deploy en Streamlit Cloud

1. Subí el repo a GitHub.
2. Entrá a [share.streamlit.io](https://share.streamlit.io) → New app → seleccioná `scout.py`.
3. En **Settings → Secrets** agregá:

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

4. Deploy. Con el secret configurado, la key queda invisible para el usuario.

## Archivos del repo

```
scout/
├── scout.py          ← app principal
├── requirements.txt  ← dependencias
├── .gitignore
└── README.md
```

## Stack

- **Streamlit** — UI y chat
- **Anthropic Claude** — interpretación de preguntas y respuestas conversacionales
- **SofaScore API** — datos en tiempo real (sin API key propia, usa la API pública)
- **curl_cffi** — requests impersonando Chrome para evitar bloqueos
