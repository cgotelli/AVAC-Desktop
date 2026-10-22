"""Persistent, interoperable sampling geometries; samples never modify results."""
from pathlib import Path
import uuid

import numpy as np
from osgeo import ogr

from .geo import spatial_reference


def validate(kind, coords):
    points = np.asarray(coords, dtype=float)
    minimum = 1 if kind == "gauge" else 2
    if kind not in ("profile", "gauge") or points.ndim != 2 or points.shape[1] != 2 or len(points) < minimum or not np.isfinite(points).all():
        raise ValueError("Invalid profile or gauge geometry.")
    if kind == "gauge" and len(points) != 1:
        raise ValueError("A gauge must be a single point.")
    if kind == "profile" and not np.any(np.diff(points, axis=0)):
        raise ValueError("A profile needs two distinct points.")
    return points.tolist()


def write_shapes(path, features, crs):
    """Write a new shapefile, preserving existing external datasets on error."""
    path = Path(path).with_suffix(".shp")
    if not features or len({feature["kind"] for feature in features}) != 1:
        raise ValueError("Save profiles and gauges in separate shapefiles.")
    kind = features[0]["kind"]
    checked = [(feature, validate(kind, feature["coords"])) for feature in features]
    if any(path.with_suffix(ext).exists() for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")):
        raise ValueError("This shapefile already exists. Choose a new filename to preserve it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(path))
    geometry_type = ogr.wkbPoint if kind == "gauge" else ogr.wkbLineString
    try:
        layer = dataset.CreateLayer(path.stem, spatial_reference(crs), geometry_type, options=["ENCODING=UTF-8"])
        field = ogr.FieldDefn("name", ogr.OFTString)
        field.SetWidth(100)
        layer.CreateField(field)
        for feature, coords in checked:
            geometry = ogr.Geometry(geometry_type)
            for x, y in coords:
                geometry.AddPoint_2D(x, y)
            item = ogr.Feature(layer.GetLayerDefn())
            item.SetField("name", feature["name"])
            item.SetGeometry(geometry)
            if layer.CreateFeature(item) != ogr.OGRERR_NONE:
                raise ValueError("Cannot write sampling shapefile.")
    finally:
        dataset = None
    return path


def store_feature(workspace, kind, coords, name, crs):
    feature = dict(kind=kind, name=name, coords=validate(kind, coords))
    path = Path(workspace)/"analysis_inputs"/f"{kind}-{uuid.uuid4().hex[:12]}.shp"
    write_shapes(path, [feature], crs)
    feature["path"] = path
    feature["fid"] = 0
    return feature


def read_shapes(path, crs):
    path = Path(path).resolve(strict=True)
    dataset = ogr.Open(str(path), 0)
    if dataset is None:
        raise ValueError("Cannot open sampling shapefile.")
    features = []
    try:
        layer = dataset.GetLayer(0)
        source = layer.GetSpatialRef()
        if source is None:
            raise ValueError("Sampling shapefile has no CRS. Provide its .prj file.")
        target = spatial_reference(crs)
        source = spatial_reference(source.ExportToWkt())
        from osgeo import osr
        transform = None if source.IsSame(target) else osr.CoordinateTransformation(source, target)
        for item in layer:
            geometry = item.GetGeometryRef()
            if geometry is None or geometry.IsEmpty():
                raise ValueError("Sampling shapefile contains an empty geometry.")
            geometry = geometry.Clone()
            if transform and geometry.Transform(transform) != ogr.OGRERR_NONE:
                raise ValueError("Cannot transform sampling geometry into the project CRS.")
            kind = {ogr.wkbPoint: "gauge", ogr.wkbLineString: "profile"}.get(ogr.GT_Flatten(geometry.GetGeometryType()))
            if kind is None:
                raise ValueError("Load single point gauges or single line profiles. Split multipart features first.")
            coords = validate(kind, [[p[0], p[1]] for p in geometry.GetPoints()])
            name = item.GetField("name") if item.GetFieldIndex("name") >= 0 else None
            features.append(dict(kind=kind, name=str(name or f"{path.stem} {item.GetFID()+1}"), coords=coords, path=path, fid=item.GetFID()))
            if len(features) > 10000:
                raise ValueError("Sampling shapefile exceeds the 10,000 feature limit.")
    finally:
        dataset = None
    if not features:
        raise ValueError("Sampling shapefile contains no features.")
    return features
