"""Mapa folium de uma `Solution`: uma camada por veículo, ícone por prioridade, popups.

Os trechos são linhas retas entre paradas (a distância usada no GA é haversine x fator de
tortuosidade, ADR 0003); o traçado real das ruas via OSRM é P2.
"""

from __future__ import annotations

from pathlib import Path

import folium

from medroute.domain.models import Instance, Priority, Solution

# Cores aceitas por folium.Icon, usadas também nas linhas para a legenda bater com os marcadores.
ROUTE_COLORS = ["blue", "red", "green", "purple", "orange", "darkblue", "darkred", "cadetblue"]
PRIORITY_ICONS = {
    Priority.CRITICA: "exclamation-triangle",
    Priority.ALTA: "arrow-up",
    Priority.NORMAL: "circle",
}


def _delivery_popup(delivery, ordem: int, vehicle_id: str) -> str:
    refrigerado = "sim" if delivery.refrigerado else "não"
    deadline = f"<br>Prazo: {delivery.deadline_min:.0f} min" if delivery.deadline_min else ""
    return (
        f"<b>{ordem}. {delivery.nome}</b> ({delivery.id})<br>"
        f"Veículo: {vehicle_id}<br>"
        f"Prioridade: {delivery.prioridade.value}{deadline}<br>"
        f"Carga: {delivery.peso_kg:.1f} kg · {delivery.volume_l:.1f} L<br>"
        f"Refrigerado: {refrigerado}"
    )


def build_map(solution: Solution, inst: Instance) -> folium.Map:
    if solution.instance_nome != inst.nome:
        raise ValueError(
            f"solução de '{solution.instance_nome}' não corresponde à instância '{inst.nome}'"
        )
    deliveries = {delivery.id: delivery for delivery in inst.deliveries}
    depot = (inst.depot.lat, inst.depot.lon)

    fmap = folium.Map(location=depot, zoom_start=12, tiles="OpenStreetMap")
    folium.Marker(
        depot,
        tooltip=inst.depot.nome,
        popup=f"<b>{inst.depot.nome}</b><br>Depósito",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(fmap)

    for i, route in enumerate(solution.routes):
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        layer = folium.FeatureGroup(
            name=(
                f"{route.vehicle_id} · {len(route.sequence)} entregas · "
                f"{route.distancia_km:.1f} km · R$ {route.custo:.2f}"
            )
        )
        stops = [deliveries[delivery_id] for delivery_id in route.sequence]
        path = [depot, *((stop.lat, stop.lon) for stop in stops), depot]
        folium.PolyLine(
            path,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=(
                f"{route.vehicle_id}: {route.distancia_km:.1f} km, "
                f"{route.duracao_min:.0f} min, R$ {route.custo:.2f}"
            ),
        ).add_to(layer)
        for ordem, stop in enumerate(stops, start=1):
            folium.Marker(
                (stop.lat, stop.lon),
                tooltip=f"{ordem}. {stop.nome}",
                popup=folium.Popup(_delivery_popup(stop, ordem, route.vehicle_id), max_width=300),
                icon=folium.Icon(color=color, icon=PRIORITY_ICONS[stop.prioridade], prefix="fa"),
            ).add_to(layer)
        layer.add_to(fmap)

    points = [depot, *((d.lat, d.lon) for d in inst.deliveries)]
    fmap.fit_bounds(
        [
            (min(p[0] for p in points), min(p[1] for p in points)),
            (max(p[0] for p in points), max(p[1] for p in points)),
        ]
    )
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def save_map(solution: Solution, inst: Instance, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_map(solution, inst).save(str(path))
    return path
