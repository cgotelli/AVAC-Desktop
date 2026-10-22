"""One snow-on-land / water-displacement animation on WAVE's native timeline."""
from types import SimpleNamespace
import numpy as np

class CombinedResults:
    def __init__(self, avalanche, water):
        if avalanche.discovery.crs_authid != water.discovery.crs_authid:
            raise ValueError("Avalanche and WAVE results must have the same CRS.")
        self.avalanche, self.water = avalanche, water
        self.root = water.root
        # Keep every native water frame/time, including waves after AVAC ends.
        # Snow holds the most recent native land state without interpolation.
        snow_times = np.array([f.time_seconds for f in avalanche.discovery.frames])
        water_times = np.array([f.time_seconds for f in water.discovery.frames])
        self.indices = np.clip(np.searchsorted(snow_times, water_times+1e-6, side="right")-1,
                               0, len(snow_times)-1)
        self.discovery = SimpleNamespace(frames=water.discovery.frames, crs_authid=water.discovery.crs_authid,
                                        run_root=self.root, fgmax_path=None, fgmax_optional_quantities=())

    def raster(self, variable, index):
        if variable != "surface_displacement":
            raise ValueError("The combined view displays water surface displacement with snow depth on land.")
        return self.water.raster(variable, index)

    def overlays(self, variable, index):
        water = self.raster(variable, index)
        return self.avalanche.raster("depth", int(self.indices[index])), water

    def gauge(self, x, y, variable, task=None):
        if variable != "surface_displacement":
            raise ValueError("Use Avalanche or Waves to inspect other result fields.")
        return self.water.gauge(x, y, variable, task)
