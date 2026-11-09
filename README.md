# Viajes

Repositorio como **grafo de conocimiento de viajes**: cada país, región, ciudad, actividad y viaje es un nodo, y las relaciones entre ellos (contiene, pertenece a, visitado en, realizado en) son las aristas.

Todo vive en Markdown plano con **frontmatter YAML**, así que es legible por personas, diff-friendly en git y consultable por máquinas (se puede recorrer el grafo con cualquier script sobre los frontmatter).

## Modelo del grafo

```
viaje ──visita──▶ país ──contiene──▶ región ──contiene──▶ ciudad ──tiene──▶ actividad
  ▲                                                            │
  └────────────── actividad realizada en ◀────────────────────┘
```

Tipos de nodo y dónde viven:

| Tipo | Carpeta | Archivo |
|---|---|---|
| País | `paises/<pais>/` | `README.md` |
| Región | `paises/<pais>/regiones/<region>/` | `README.md` |
| Ciudad | `paises/<pais>/regiones/<region>/ciudades/<ciudad>/` | `README.md` |
| Actividad | `.../ciudades/<ciudad>/actividades/<actividad>.md` | archivo suelto |
| Viaje | `viajes/<id-viaje>/` | `README.md` |
| Perfil (nuestros gustos) | raíz | `perfil.yaml` |
| Plantillas | `_plantillas/` | una por tipo de nodo |

## Convenciones

- **id**: slug único y estable en minúsculas (`japon`, `kanto`, `tokio`, `tokio-sensoji`, `2025-japon`). Nunca se reutiliza.
- **ruta**: camino del nodo dentro del grafo, p. ej. `japon/kanto/tokio`. Se usa para enlazar nodos sin depender de la ruta física en disco.
- **Aristas del grafo** (campos de frontmatter):
  - País → `contiene: [regiones]`; Región → `contiene: [ciudades]` y `pais: japon`.
  - Ciudad → `region: kanto`, `pais: japon`.
  - Actividad → `lugar: japon/kanto/tokio` y `realizada_en: [<id-viaje>]`.
  - Viaje → `paradas: [{ fecha, lugar: japon/kanto/tokio, actividades: [tokio-sensoji], ... }]`.
- **Afinidad**: cada nodo geográfico y cada viaje tiene `afinidad: 1-5` (o `null` si aún no lo hemos valorado) y `gustos: [tags]` que encajan con `perfil.yaml`. Así podemos buscar qué destinos tienen más afinidad con nosotros.
- Todo el contenido en español; los nombres propios japoneses conservan su forma habitual.

## Cómo añadir cosas

1. Copia la plantilla correspondiente de `_plantillas/`.
2. Dale un `id` nuevo y rellena el frontmatter obligatorio.
3. Actualiza las aristas en ambos extremos (p. ej. al crear una ciudad, añádela a `contiene` de su región).
4. Guarda el contenido libre (qué ver, cómo llegar, precios, nuestra experiencia) en el cuerpo del Markdown.

## Índice

- [perfil.yaml](perfil.yaml) — qué nos gusta (base para la afinidad)
- [paises/](paises/) — Japón y el resto de países que vayamos añadiendo
- [viajes/](viajes/) — viajes realizados y planificados, con días por lugar
- [_plantillas/](_plantillas/) — plantillas de cada tipo de nodo
