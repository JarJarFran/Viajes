# Viajes

Dominio de **nuestra experiencia**: cada viaje es una carpeta con un `README.md` cuyo frontmatter contiene las **paradas** (fecha → lugar → actividades → alojamiento), los gastos reales, la valoración final y la afinidad.

A diferencia de `destinos/` (que guarda el conocimiento objetivo de cada lugar), aquí solo guardamos lo que nos ha pasado a nosotros en cada viaje.

## Relación con `destinos/`

- Cada `lugar` de una parada apunta a un nodo del grafo de destinos (`japon/kanto/tokio`), y cada actividad de `actividades` al id de una ficha de `destinos/.../actividades/`.
- Al registrar una parada, añade el backlink: el id del viaje en el campo `viajes` del nodo destino y en `realizada_en` de cada actividad.

Para crear un viaje nuevo, copia [_plantillas/viaje.md](../_plantillas/viaje.md).

## Índice de viajes

(añadir una línea por viaje: `- [2025-japon](2025-japon/) — Japón, del ... al ... (estado)`)
