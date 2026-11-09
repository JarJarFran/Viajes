# Viajes

Repositorio con **dos dominios de conocimiento separados pero relacionados**:

- **`destinos/`** — el grafo de conocimiento de los lugares: país → región → ciudad → actividad. Aquí guardamos información objetiva y acumulativa de cada lugar (qué es, cómo llegar, qué se puede hacer, precios, horarios). No depende de cuándo vayamos.
- **`viajes/`** — nuestros viajes concretos: fechas, paradas por día, lo que hicimos, dónde dormimos, gastos reales, valoraciones y afinidad. Información subjetiva y temporal.

Los dos dominios se conectan solo por **referencias entre ids**: un viaje apunta a nodos de `destinos/` (`paradas[].lugar`, `paradas[].actividades`), y los nodos de `destinos/` apuntan de vuelta a los viajes (`viajes`, `realizada_en`). Nunca se mezcla contenido de uno en el otro.

Todo vive en Markdown plano con **frontmatter YAML**: legible por personas, diff-friendly en git y consultable por máquinas (se puede recorrer el grafo con cualquier script sobre los frontmatter).

## Los dos grafos y sus aristas

```
DOMINIO DESTINOS (conocimiento del lugar)          DOMINIO VIAJES (nuestra experiencia)

país ──contiene──▶ región ──contiene──▶ ciudad ──tiene──▶ actividad
                                                              ▲
viaje ──paradas.lugar────────────────────▶ nodo de destinos ──┘
viaje ──paradas.actividades──────────────▶ ficha de actividad
       ◀── viajes (backlink) ─── nodo de destinos
       ◀── realizada_en (backlink) ─── ficha de actividad
```

| | `destinos/` | `viajes/` |
|---|---|---|
| Qué guarda | Qué existe en cada lugar, datos objetivos | Qué hicimos nosotros, datos subjetivos |
| Ejemplos | "En Kioto está el templo Kinkaku-ji, entrada 500 ¥" | "El 12/04/2025 visitamos Kinkaku-ji, nos encantó, 5/5" |
| Cambia con el tiempo | Poco (horarios, precios) | Cada viaje nuevo |
| Campos típicos | `id`, `ruta`, `contiene`, `categoria`, `coste_aprox` | `inicio`, `fin`, `paradas`, `gastos_total`, `valoracion`, `afinidad` |

## Tipos de nodo y dónde viven

| Tipo | Carpeta | Archivo |
|---|---|---|
| País | `destinos/<pais>/` | `README.md` |
| Región | `destinos/<pais>/regiones/<region>/` | `README.md` |
| Ciudad | `destinos/<pais>/regiones/<region>/ciudades/<ciudad>/` | `README.md` |
| Actividad | `.../ciudades/<ciudad>/actividades/<actividad>.md` | archivo suelto |
| Viaje | `viajes/<id-viaje>/` | `README.md` |
| Perfil (nuestros gustos) | raíz | `perfil.yaml` |
| Plantillas | `_plantillas/` | una por tipo de nodo |

## Convenciones

- **id**: slug único y estable en minúsculas (`japon`, `kanto`, `tokio`, `tokio-sensoji`, `2025-japon`). Nunca se reutiliza.
- **ruta**: camino del nodo dentro del grafo de destinos, p. ej. `japon/kanto/tokio`. Es independiente de la carpeta física y se usa para enlazar dominios.
- **Aristas dentro de `destinos/`**:
  - País → `contiene: [regiones]`; Región → `contiene: [ciudades]` y `pais: japon`; Ciudad → `region: kanto`.
  - Actividad → `lugar: japon/kanto/tokio`.
- **Aristas entre dominios**:
  - Viaje → `paradas: [{ fecha, lugar: japon/kanto/tokio, actividades: [tokio-sensoji], alojamiento, notas }]`.
  - Backlinks: en el nodo de destino `viajes: [2025-japon]`; en la actividad `realizada_en: [2025-japon]`.
- **Afinidad**: en `viajes/` cada viaje y sus paradas llevan `afinidad: 1-5` y `gustos: [tags]` (nuestra valoración subjetiva). En `destinos/` los nodos pueden llevar `afinidad` como resumen acumulado de los viajes. Los tags salen de `perfil.yaml`.
- La valoración de una actividad hecha en un viaje se anota en el día correspondiente del viaje; en la ficha de actividad se puede dejar un `valoracion` resumen.
- Todo el contenido en español; los nombres propios japoneses conservan su forma habitual.

## Cómo añadir cosas

1. **¿Es conocimiento de un lugar?** → va en `destinos/`, usando la plantilla de `_plantillas/` (pais, region, ciudad o actividad). Dale `id` nuevo, rellena el frontmatter y actualiza `contiene`/`lugar` en el nodo padre.
2. **¿Es algo que hemos hecho o vamos a hacer?** → va en `viajes/<id-viaje>/`, usando `_plantillas/viaje.md`. Cada parada referencia nodos de `destinos/` por su `ruta`/id y, al registrar la parada, añade el backlink (`viajes` en el nodo destino, `realizada_en` en la actividad).

## Índice

- [perfil.yaml](perfil.yaml) — qué nos gusta (base para la afinidad)
- [destinos/](destinos/) — grafo de conocimiento de países, regiones, ciudades y actividades
- [viajes/](viajes/) — viajes realizados y planificados, con días por lugar
- [_plantillas/](_plantillas/) — plantillas de cada tipo de nodo
