"""Map page: pan/zoom QGraphicsView built on the pure helpers in map_math.

The widget renders an offline tile grid (``data/tiles/{z}/{x}/{y}.png``) and
overlays node markers. Live position updates come via ``EventBus.position_updated``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Slot
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.pages.map_math import (
    MAX_ZOOM,
    MIN_ZOOM,
    TILE_SIZE,
    TileLoader,
    lonlat_to_pixel,
    visible_tiles,
)

log = logging.getLogger(__name__)


# Where offline tiles live. Each layer is a sub-directory keyed by
# the layer name (matches the web UI: data/tiles/{layer}/{z}/{x}/{y}.png).
TILES_BASE = Path("data/tiles")
LAYER_NAMES = ("osm", "topo", "satellite")


def _layer_root(layer: str) -> Path:
    return TILES_BASE / layer


def _load_pixmap(path: Path) -> QPixmap:
    pm = QPixmap(str(path))
    if pm.isNull():
        log.warning("could not load tile %s", path)
    return pm


class MapView(QGraphicsView):
    """Pan/zoom view that renders tiles + node markers in scene coordinates.

    Scene coords use the Web Mercator pixel space at the current zoom. On
    zoom change the scene is rebuilt; markers are kept in a dict keyed by
    node id so we can update without re-creating.
    """

    DEFAULT_LAT = 41.9
    DEFAULT_LON = 12.5
    DEFAULT_ZOOM = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._zoom = self.DEFAULT_ZOOM
        self._layer = "osm"
        self._tiles = TileLoader(_layer_root(self._layer), reader=_load_pixmap)
        self._tile_items: dict[tuple[int, int, int], QGraphicsPixmapItem] = {}
        self._marker_items: dict[str, QGraphicsEllipseItem] = {}
        self._label_items: dict[str, QGraphicsTextItem] = {}
        self._traceroute_items: dict[str, QGraphicsPathItem] = {}
        self._waypoint_items: dict[int, tuple[QGraphicsEllipseItem, QGraphicsTextItem]] = {}
        self._neighbor_items: list[QGraphicsLineItem] = []
        self._center_lon = self.DEFAULT_LON
        self._center_lat = self.DEFAULT_LAT

        self.set_zoom(self._zoom, recenter=True)

    # ------------------------------------------------------------------

    def zoom(self) -> int:
        return self._zoom

    def set_zoom(self, zoom: int, recenter: bool = False) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if zoom == self._zoom and not recenter:
            return
        self._zoom = zoom
        # Wipe scene and rebuild at the new zoom.
        for item in list(self._tile_items.values()):
            self._scene.removeItem(item)
        self._tile_items.clear()

        if recenter:
            cx, cy = lonlat_to_pixel(self._center_lon, self._center_lat, zoom)
            self.centerOn(cx, cy)

        self._refresh_tiles()
        self._reposition_markers()

    def set_center(self, lon: float, lat: float) -> None:
        self._center_lon = lon
        self._center_lat = lat
        cx, cy = lonlat_to_pixel(lon, lat, self._zoom)
        self.centerOn(cx, cy)
        self._refresh_tiles()

    def set_layer(self, layer: str) -> None:
        if layer == self._layer:
            return
        self._layer = layer
        # Drop the old layer's tiles and switch the loader's tile root.
        for item in list(self._tile_items.values()):
            self._scene.removeItem(item)
        self._tile_items.clear()
        self._tiles = TileLoader(_layer_root(layer), reader=_load_pixmap)
        self._refresh_tiles()

    # ------------------------------------------------------------------
    # Tiles

    def _refresh_tiles(self) -> None:
        vp = self.viewport().size()
        # Center in scene coords:
        scene_center = self.mapToScene(self.viewport().rect().center())
        # Convert back to lon/lat to feed visible_tiles().
        # (We don't strictly need lon/lat: we could compute tile bounds from
        # scene_center directly — but visible_tiles is the API we have.)
        from gui.pages.map_math import pixel_to_lonlat
        lon, lat = pixel_to_lonlat(scene_center.x(), scene_center.y(), self._zoom)

        wanted: set[tuple[int, int, int]] = set()
        for tx, ty in visible_tiles(lon, lat, self._zoom, vp.width(), vp.height()):
            wanted.add((self._zoom, tx, ty))

        # Remove tiles no longer visible.
        for key in list(self._tile_items.keys()):
            if key not in wanted:
                self._scene.removeItem(self._tile_items.pop(key))

        # Add missing tiles.
        for z, tx, ty in wanted:
            key = (z, tx, ty)
            if key in self._tile_items:
                continue
            pm = self._tiles.get(z, tx, ty)
            if pm is None or (hasattr(pm, "isNull") and pm.isNull()):
                continue
            item = QGraphicsPixmapItem(pm)
            item.setPos(tx * TILE_SIZE, ty * TILE_SIZE)
            item.setZValue(-1)
            self._scene.addItem(item)
            self._tile_items[key] = item

    # ------------------------------------------------------------------
    # Markers

    def update_marker(self, node_id: str, lon: float, lat: float, *, label: str | None = None,
                      is_local: bool = False) -> None:
        x, y = lonlat_to_pixel(lon, lat, self._zoom)
        radius = 6 if not is_local else 9
        color = QColor("#4a9eff") if not is_local else QColor("#ff5722")

        if node_id in self._marker_items:
            item = self._marker_items[node_id]
            item.setRect(x - radius, y - radius, radius * 2, radius * 2)
            item.setBrush(QBrush(color))
        else:
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
            item.setBrush(QBrush(color))
            item.setPen(QPen(QColor("#000000"), 1))
            item.setZValue(1)
            self._scene.addItem(item)
            self._marker_items[node_id] = item

        text = label or node_id
        if node_id in self._label_items:
            tlbl = self._label_items[node_id]
            tlbl.setPos(x + radius + 2, y - radius - 4)
            tlbl.setPlainText(text)
        else:
            tlbl = QGraphicsTextItem(text)
            tlbl.setDefaultTextColor(QColor("#ffffff"))
            tlbl.setPos(x + radius + 2, y - radius - 4)
            tlbl.setZValue(2)
            self._scene.addItem(tlbl)
            self._label_items[node_id] = tlbl

    def clear_markers(self) -> None:
        for item in self._marker_items.values():
            self._scene.removeItem(item)
        for item in self._label_items.values():
            self._scene.removeItem(item)
        self._marker_items.clear()
        self._label_items.clear()

    def show_traceroute(self, key: str, points: list[tuple[float, float]]) -> None:
        """Draw a polyline through the given (lon, lat) points.

        ``key`` is an identifier (typically the destination node id) so the
        same path can be replaced when an updated traceroute arrives.
        Existing path with the same key is removed first.
        """
        self.clear_traceroute(key)
        if len(points) < 2:
            return
        path = QPainterPath()
        x, y = lonlat_to_pixel(points[0][0], points[0][1], self._zoom)
        path.moveTo(x, y)
        for lon, lat in points[1:]:
            x, y = lonlat_to_pixel(lon, lat, self._zoom)
            path.lineTo(x, y)
        item = QGraphicsPathItem(path)
        pen = QPen(QColor("#ffeb3b"))
        pen.setWidthF(2.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        item.setPen(pen)
        item.setZValue(0.5)  # above tiles, below markers
        self._scene.addItem(item)
        self._traceroute_items[key] = item

    def clear_traceroute(self, key: str | None = None) -> None:
        if key is None:
            for item in self._traceroute_items.values():
                self._scene.removeItem(item)
            self._traceroute_items.clear()
            return
        item = self._traceroute_items.pop(key, None)
        if item is not None:
            self._scene.removeItem(item)

    # -- waypoints (mesh-shared) -----------------------------------------

    def update_waypoint(self, wp_id: int, lon: float, lat: float, *, name: str = "") -> None:
        x, y = lonlat_to_pixel(lon, lat, self._zoom)
        marker, label = self._waypoint_items.get(wp_id, (None, None))
        radius = 5
        color = QColor("#ffeb3b")
        if marker is None:
            marker = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
            pen = QPen(QColor("#000000"), 1.0)
            marker.setPen(pen)
            marker.setBrush(QBrush(color))
            marker.setZValue(0.7)
            self._scene.addItem(marker)
            label = QGraphicsTextItem(name)
            label.setDefaultTextColor(QColor("#ffeb3b"))
            label.setZValue(0.8)
            self._scene.addItem(label)
        else:
            marker.setRect(x - radius, y - radius, radius * 2, radius * 2)
            label.setPlainText(name)
        label.setPos(x + radius + 2, y - radius - 4)
        self._waypoint_items[wp_id] = (marker, label)

    def remove_waypoint(self, wp_id: int) -> None:
        items = self._waypoint_items.pop(wp_id, None)
        if items is None:
            return
        for it in items:
            self._scene.removeItem(it)

    def clear_waypoints(self) -> None:
        for items in self._waypoint_items.values():
            for it in items:
                self._scene.removeItem(it)
        self._waypoint_items.clear()

    # -- neighbor links (SNR-coloured straight lines) --------------------

    def set_neighbor_links(self, links: list[tuple[float, float, float, float, float]]) -> None:
        """``links`` is a list of (a_lon, a_lat, b_lon, b_lat, snr)."""
        # Wipe old.
        for item in self._neighbor_items:
            self._scene.removeItem(item)
        self._neighbor_items.clear()
        for a_lon, a_lat, b_lon, b_lat, snr in links:
            x1, y1 = lonlat_to_pixel(a_lon, a_lat, self._zoom)
            x2, y2 = lonlat_to_pixel(b_lon, b_lat, self._zoom)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            color = (
                QColor("#4caf50") if snr > 0
                else QColor("#ff9800") if snr > -10
                else QColor("#f44336")
            )
            pen = QPen(color)
            pen.setWidthF(1.2)
            line.setPen(pen)
            line.setZValue(0.4)
            self._scene.addItem(line)
            self._neighbor_items.append(line)

    def _reposition_markers(self) -> None:
        # When zoom changes, redraw markers at their new pixel coords.
        # Marker state is kept on instance so we can rebuild from cache:
        # for now, callers (the page) re-issue update_marker for every node.
        pass

    # ------------------------------------------------------------------
    # Wheel zoom

    def wheelEvent(self, ev: QWheelEvent) -> None:
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        new_zoom = self._zoom + (1 if delta > 0 else -1)
        self.set_zoom(new_zoom, recenter=True)
        ev.accept()


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar (top)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        bar.setSpacing(4)
        self._zoom_in = QPushButton("+")
        self._zoom_out = QPushButton("−")
        self._zoom_in.setFixedWidth(28)
        self._zoom_out.setFixedWidth(28)
        self._zoom_label = QLabel("z5")
        self._zoom_label.setProperty("role", "muted")
        self._zoom_label.setFixedWidth(20)

        # Layer switcher (osm / topo / satellite)
        self._layer_combo = QComboBox(self)
        for name in LAYER_NAMES:
            self._layer_combo.addItem(name)
        self._layer_combo.currentTextChanged.connect(self._on_layer)
        self._layer_combo.setFixedWidth(80)

        # Neighbor links toggle
        self._neighbor_toggle = QToolButton(self)
        self._neighbor_toggle.setText("⌬")
        self._neighbor_toggle.setToolTip("Show neighbor links")
        self._neighbor_toggle.setCheckable(True)
        self._neighbor_toggle.toggled.connect(self._on_toggle_neighbors)

        # Recenter
        recenter = QPushButton("⌖")
        recenter.setToolTip("Center on local node")
        recenter.setFixedWidth(28)

        bar.addWidget(self._zoom_in)
        bar.addWidget(self._zoom_out)
        bar.addWidget(self._zoom_label)
        bar.addWidget(self._layer_combo)
        bar.addWidget(self._neighbor_toggle)
        bar.addStretch(1)
        bar.addWidget(recenter)
        layout.addLayout(bar)

        # Map view
        self._view = MapView(self)
        layout.addWidget(self._view, 1)

        self._zoom_in.clicked.connect(lambda: self._zoom(+1))
        self._zoom_out.clicked.connect(lambda: self._zoom(-1))
        recenter.clicked.connect(self._recenter_local)

        # Initial markers + waypoints
        self._refresh_all()
        self._refresh_waypoints()

        # Periodic refresh — cheap, catches deletes too.
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start()

        # Slower waypoints poll so we don't hammer the API.
        self._wp_timer = QTimer(self)
        self._wp_timer.setInterval(15000)
        self._wp_timer.timeout.connect(self._refresh_waypoints)
        self._wp_timer.start()

        if eventbus is not None:
            eventbus.position_updated.connect(self._on_position)
            eventbus.traceroute_result.connect(self._on_traceroute)
            eventbus.waypoint.connect(lambda _e: self._refresh_waypoints())
            eventbus.neighbor_info.connect(lambda _e: self._refresh_neighbors_if_visible())

    def _zoom(self, delta: int) -> None:
        self._view.set_zoom(self._view.zoom() + delta, recenter=True)
        self._zoom_label.setText(f"z={self._view.zoom()}")

    def _recenter_local(self) -> None:
        try:
            import meshtasticd_client
            local = meshtasticd_client.get_local_node()
        except Exception:
            local = None
        if local and local.get("latitude") is not None:
            self._view.set_center(local["longitude"], local["latitude"])

    def _refresh_all(self) -> None:
        try:
            import meshtasticd_client
            nodes = meshtasticd_client.get_nodes()
        except Exception:
            nodes = []
        for n in nodes:
            lat = n.get("latitude")
            lon = n.get("longitude")
            if lat is None or lon is None:
                continue
            self._view.update_marker(
                n.get("id") or "?",
                float(lon),
                float(lat),
                label=n.get("short_name") or n.get("id"),
                is_local=bool(n.get("is_local")),
            )

    @Slot(dict)
    def _on_position(self, event: dict) -> None:
        node_id = event.get("id")
        lat = event.get("latitude")
        lon = event.get("longitude")
        if not node_id or lat is None or lon is None:
            return
        self._view.update_marker(node_id, float(lon), float(lat))

    def _on_layer(self, name: str) -> None:
        self._view.set_layer(name)

    def _on_toggle_neighbors(self, checked: bool) -> None:
        if checked:
            self._refresh_neighbors_if_visible()
        else:
            self._view.set_neighbor_links([])

    def _refresh_neighbors_if_visible(self) -> None:
        if not self._neighbor_toggle.isChecked():
            return
        loop = __import__("asyncio").get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._fetch_neighbors())

    async def _fetch_neighbors(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/neighbor-info")
            links_raw = r.json() if r.status_code == 200 else []
        except Exception:
            return
        try:
            import meshtasticd_client
            nodes_by_id = {n.get("id"): n for n in meshtasticd_client.get_nodes()}
        except Exception:
            return
        prepared: list[tuple[float, float, float, float, float]] = []
        for l in links_raw:
            a = nodes_by_id.get(l.get("from_id"))
            b = nodes_by_id.get(l.get("neighbor_id"))
            if not a or not b:
                continue
            if a.get("latitude") is None or b.get("latitude") is None:
                continue
            prepared.append((
                float(a["longitude"]), float(a["latitude"]),
                float(b["longitude"]), float(b["latitude"]),
                float(l.get("snr") or 0.0),
            ))
        self._view.set_neighbor_links(prepared)

    def _refresh_waypoints(self) -> None:
        loop = __import__("asyncio").get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._fetch_waypoints())

    async def _fetch_waypoints(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/waypoints")
            wps = r.json() if r.status_code == 200 else []
        except Exception:
            return
        seen = set()
        for wp in wps:
            wid = wp.get("id")
            lat = wp.get("lat") or wp.get("latitude")
            lon = wp.get("lon") or wp.get("longitude")
            if wid is None or lat is None or lon is None:
                continue
            seen.add(wid)
            self._view.update_waypoint(int(wid), float(lon), float(lat),
                                       name=wp.get("name") or "")
        # Drop waypoints that are no longer in the list.
        for wid in list(self._view._waypoint_items.keys()):
            if wid not in seen:
                self._view.remove_waypoint(wid)

    @Slot(dict)
    def _on_traceroute(self, event: dict) -> None:
        """Render the traceroute path from local node through the hop list.

        Uses the position cached in get_nodes() for each hop. Hops without
        a known position are skipped — partial paths still render the
        segments we can place.
        """
        try:
            import meshtasticd_client
            nodes_by_id = {n.get("id"): n for n in meshtasticd_client.get_nodes()}
            local_id = meshtasticd_client.get_local_id()
        except Exception:
            return
        dest = event.get("node_id") or event.get("id")
        hops = event.get("hops") or event.get("route") or []
        path: list[tuple[float, float]] = []

        chain = [local_id, *hops, dest] if dest else [local_id, *hops]
        for nid in chain:
            n = nodes_by_id.get(nid)
            if not n:
                continue
            lat = n.get("latitude")
            lon = n.get("longitude")
            if lat is None or lon is None:
                continue
            path.append((float(lon), float(lat)))

        if dest:
            self._view.show_traceroute(dest, path)
