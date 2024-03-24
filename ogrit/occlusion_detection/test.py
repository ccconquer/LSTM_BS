from shapely.geometry import Polygon
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from numpy import asarray, concatenate, ones, array

def PolygonPath(polygon):
    """Constructs a compound matplotlib path from a Shapely or GeoJSON-like
    geometric object"""

    def coding(ob):
        # The codes will be all "LINETO" commands, except for "MOVETO"s at the
        # beginning of each subpath
        n = len(getattr(ob, 'coords', None) or ob)
        vals = ones(n, dtype=Path.code_type) * Path.LINETO
        vals[0] = Path.MOVETO
        return vals

    if hasattr(polygon, 'geom_type'):  # Shapely
        ptype = polygon.geom_type
        if ptype == 'Polygon':
            polygon = [Polygon(polygon)]
        elif ptype == 'MultiPolygon':
            polygon = [Polygon(p) for p in polygon]
        else:
            raise ValueError(
                "A polygon or multi-polygon representation is required")
        #print('jin',polygon)

    else:  # GeoJSON
        polygon = getattr(polygon, '__geo_interface__', polygon)
        ptype = polygon["type"]
        if ptype == 'Polygon':
            polygon = [Polygon(polygon)]
        elif ptype == 'MultiPolygon':
            polygon = [Polygon(p) for p in polygon['coordinates']]
        else:
            raise ValueError(
                "A polygon or multi-polygon representation is required")
        
   
   
    for t in polygon:
        print('twaiwei',asarray(t.exterior))
        print('tneibu',asarray(t.interiors))
    
 
    vertices_list = []
    codes_list = []

    for t in polygon:
        vertices_list.append(array(t.exterior.coords))
        codes_list.append(coding(t.exterior))

        for r in t.interiors:
            vertices_list.append(array(r.coords))
            codes_list.append(coding(r))

    vertices = concatenate(vertices_list)
    codes = concatenate(codes_list)


    # vertices = concatenate([
    #     concatenate([asarray(t.exterior)[:, :2]] +
    #                 [asarray(r)[:, :2] for r in t.interiors])
    #     for t in polygon])
    
    # codes = concatenate([
    #     concatenate([coding(t.exterior)[:, :2]] +
    #                 [coding(r)[:, :2] for r in t.interiors]) for t in polygon])

    return Path(vertices, codes)


def main():
    coords = [
        (51.41872446242131, -25.993719268570096),
        (48.21444227346332, -22.233580213159176),
        (46.741615537578696, -23.488680731429902),
        (49.945897726536685, -27.248819786840823),
        (51.41872446242131, -25.993719268570096)
      ]

    polygon = Polygon(coords)
    print(PolygonPath(polygon))


if __name__ == '__main__':
    main()