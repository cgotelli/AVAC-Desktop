"""One batched scene item per mesh, clipped and limited in screen space."""
import math
import numpy as np
from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem


class MeshItem(QGraphicsItem):
    CELL_PIXELS = 7
    LINE_BUDGET = 4000
    PATCH_BUDGET = 10_000

    def __init__(self, layer, origin):
        super().__init__()
        self.origin = origin
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setZValue(2.7)
        self.layout_id = None
        self.rect = QRectF()
        self.geometry_cache = None
        self.too_dense = False
        self.set_layer(layer)

    def set_layer(self, layer):
        self.layer = layer
        if self.layout_id == layer.layout_id:
            return
        self.prepareGeometryChange()
        self.layout_id = layer.layout_id
        p = layer.patches
        x, y = p[:, 0]-self.origin[0], self.origin[1]-p[:, 1]-p[:, 3]*p[:, 5]
        self.bounds = np.column_stack((x, y, x+p[:, 2]*p[:, 4], y+p[:, 3]*p[:, 5]))
        self.rect = QRectF(float(x.min()), float(y.min()), float(self.bounds[:, 2].max()-x.min()),
                           float(self.bounds[:, 3].max()-y.min()))
        self.geometry_cache = None
        self.update()

    def boundingRect(self):
        return self.rect

    def _geometry(self, exposed, sx, sy):
        b, p = self.bounds, self.layer.patches
        selected = np.flatnonzero((b[:, 0] <= exposed.right()) & (b[:, 2] >= exposed.left()) &
                                  (b[:, 1] <= exposed.bottom()) & (b[:, 3] >= exposed.top()))
        self.too_dense = len(selected) > self.PATCH_BUDGET
        if self.too_dense:
            return {}
        groups = {}
        remaining = self.LINE_BUDGET
        # Draw finer patch boundaries over coarser levels; cells are never faked
        # with a coarser spacing when their true spacing is subpixel.
        for i in selected[np.argsort(p[selected, 6], kind='stable')]:
            left, top, right, bottom = b[i]
            _, _, nx, ny, dx, dy, level = p[i]
            outlines, lines = groups.setdefault(int(level), ([], []))
            outlines.append(QRectF(left, top, right-left, bottom-top))
            if dx*sx < self.CELL_PIXELS or dy*sy < self.CELL_PIXELS:
                continue
            x0 = max(1, math.ceil((exposed.left()-left)/dx))
            x1 = min(int(nx)-1, math.floor((exposed.right()-left)/dx))
            y0 = max(1, math.ceil((exposed.top()-top)/dy))
            y1 = min(int(ny)-1, math.floor((exposed.bottom()-top)/dy))
            count = max(0, x1-x0+1)+max(0, y1-y0+1)
            if count > remaining:
                continue
            lines.extend(QLineF(left+j*dx, max(top, exposed.top()), left+j*dx, min(bottom, exposed.bottom()))
                         for j in range(x0, x1+1))
            lines.extend(QLineF(max(left, exposed.left()), top+j*dy, min(right, exposed.right()), top+j*dy)
                         for j in range(y0, y1+1))
            remaining -= count
        return groups

    def paint(self, painter, option, widget=None):
        transform = painter.worldTransform()
        sx, sy = abs(transform.m11()), abs(transform.m22())
        exposed = option.exposedRect.intersected(self.rect)
        key = (exposed.x(), exposed.y(), exposed.width(), exposed.height(), sx, sy)
        if self.geometry_cache is None or self.geometry_cache[0] != key:
            self.geometry_cache = key, self._geometry(exposed, sx, sy)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        colours = ('#2681b0', '#14a1ad', '#855ccc', '#d35b85') if self.layer.name == 'AVAC' else ('#db8d24', '#c55b33', '#c63872', '#8859b4')
        for level, (outlines, lines) in self.geometry_cache[1].items():
            colour = QColor(colours[(level-1) % len(colours)])
            colour.setAlpha(135)
            pen = QPen(colour, .7)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if lines:
                painter.drawLines(lines)
            colour.setAlpha(230)
            pen.setColor(colour)
            pen.setWidthF(1.15)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRects(outlines)
        painter.restore()
