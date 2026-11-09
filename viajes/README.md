# Viajes

Cada viaje es una carpeta con un `README.md` cuyo frontmatter contiene las **paradas** (fecha → lugar → actividades → alojamiento), la valoración final y la afinidad.

Los `lugar` de cada parada apuntan a nodos del grafo (`japon/kanto/tokio`), y las `actividades` a fichas de `actividades/` de la ciudad correspondiente. Al registrar una parada, añade también el id del viaje en el campo `viajes` del nodo visitado y en `realizada_en` de cada actividad.

Para crear un viaje nuevo, copia [_plantillas/viaje.md](../_plantillas/viaje.md).

## Índice de viajes

(añadir una línea por viaje: `- [2025-japon](2025-japon/) — Japón, del ... al ... (estado)`)
