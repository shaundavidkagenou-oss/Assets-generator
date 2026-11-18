import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph import Vector
from .core import load_mesh


class Viewport(gl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setBackgroundColor('#171b21')
        self.setCameraPosition(distance=4, elevation=20, azimuth=45)
        self.grid = gl.GLGridItem(color=(90, 100, 113, 110))
        self.grid.setSize(8, 8, 1)
        self.grid.setSpacing(0.5, 0.5, 1)
        self.addItem(self.grid)
        self.item = None
        self.mesh = None
        self.wire = False

    def show_mesh(self, path):
        mesh = load_mesh(path)
        vertices = mesh.vertices.copy()
        center = (vertices.max(axis=0) + vertices.min(axis=0)) / 2
        vertices -= center
        extent = np.ptp(vertices, axis=0).max()
        if not np.isfinite(extent) or extent <= 0: raise ValueError('Mesh has zero extent.')
        vertices *= 2 / extent
        self.mesh = (vertices, mesh.faces.copy())
        self.redraw()
        self.reset_camera()
        return mesh

    def redraw(self):
        if self.item is not None: self.removeItem(self.item)
        if self.mesh is not None:
            vertices, faces = self.mesh
            self.item = gl.GLMeshItem(vertexes=vertices, faces=faces, smooth=False, color=(0.68, 0.73, 0.79, 1), drawFaces=not self.wire, drawEdges=self.wire, edgeColor=(0.65, 0.78, 0.86, 1), shader='shaded')
            self.addItem(self.item)

    def reset_camera(self):
        self.opts['center'] = Vector(0, 0, 0)
        self.setCameraPosition(distance=4, elevation=20, azimuth=45)
        self.update()
