""" A collection of utility methods and classes used throughout the project. """

from typing import Tuple, List

import numpy as np
from shapely.geometry import LineString, Point


def get_curvature(points: np.ndarray) -> np.ndarray:
    """
    Gets the curvature of a 2D path
    based on https://en.wikipedia.org/wiki/Curvature#In_terms_of_a_general_parametrization

    Args:
        points: nx2 array of points

    Returns:
        curvature
    """
    gamma = np.array(points)
    s = np.concatenate(([0], np.cumsum(np.linalg.norm(np.diff(gamma, axis=0), axis=1))))
    ds = np.gradient(s).reshape((-1, 1))
    with np.errstate(divide='ignore', invalid='ignore'):
        d_gamma_ds = np.true_divide(np.gradient(gamma, axis=0), ds)
        d_2_gamma_ds_2 = np.true_divide(np.gradient(d_gamma_ds, axis=0), ds)
        kappa = np.linalg.det(np.dstack([d_gamma_ds, d_2_gamma_ds_2])) / np.linalg.norm(d_gamma_ds, axis=1) ** 3
        kappa = np.nan_to_num(kappa)
    return kappa


def get_linestring_side(ls: LineString, p: Point) -> str:
    """ Return which side of the LineString is the given point, order by the sequence of the coordinates.

    Args:
        ls: reference LineString
        p: point to check

    Returns:
        Either "left" or "right"
    """
    right = ls.parallel_offset(0.1, side="right")
    left = ls.parallel_offset(0.1, side="left")
    return "left" if left.distance(p) < right.distance(p) else "right"


def get_points_parallel(points: np.ndarray, lane_ls: LineString, lat_distance: float = None) -> np.ndarray:
    """ Find parallel to lane_ls of given points (also on lane_ls) through a given point specified by points[0].

    Args:
        points: Points that lie on lane_ls. The first element - points[0] - may lie elsewhere and specifies which
            location the parallel line must pass through.
        lane_ls: Reference LineString
        lat_distance: Optional latitudinal distance from the linestring. If not specified, it will be infered from the
            first element of points.

    Returns:
        A numpy array, where dim(points) is equal to dim(ret). Furthermore, points[0] == ret[0] is always true.
    """
    current_point = Point(points[0])
    side = get_linestring_side(lane_ls, current_point)
    if lat_distance is None:
        lat_distance = lane_ls.distance(current_point)

    # Add dummy point to be able to construct a linestring
    if len(points) == 2:
        new_point_lon = lane_ls.project(Point((points[0] + points[1]) / 2))
        new_point = lane_ls.interpolate(new_point_lon)

        import matplotlib.pyplot as plt
        plt.plot(*new_point.xy, marker="1")# todo: remove
        points = np.insert(points, 1, new_point, axis=0)

    points_ls = LineString(points[1:])
    points_ls = points_ls.parallel_offset(lat_distance, side=side, join_style=2)
    points_ls = list(points_ls.coords) if side == "left" else list(points_ls.coords[::-1])

    # Drop the dummy point
    if len(points_ls) == 2:
        points_ls = [points_ls[1]]

    return np.array([tuple(current_point.coords[0])] + points_ls)


def calculate_multiple_bboxes(center_points_x: List[float], center_points_y: List[float],
                              length: float, width: float, rotation: float = 0.0) -> np.ndarray:
    """ Calculate bounding box vertices from centroid, width and length.

    Args:
        center_points_x: center x-coord of bbox
        center_points_y: center y-coord of bbox
        length: length of bbox
        width: width of bbox
        rotation: rotation of main bbox axis (along length)

    Returns:
        np.ndarray containing the rotated vertices of each box
    """

    centroid = np.array([center_points_x, center_points_y]).transpose()

    centroid = np.array(centroid)
    if centroid.shape == (2,):
        centroid = np.array([centroid])

    # Preallocate
    data_length = centroid.shape[0]
    rotated_bbox_vertices = np.empty((data_length, 4, 2))

    # Calculate rotated bounding box vertices
    rotated_bbox_vertices[:, 0, 0] = -length / 2
    rotated_bbox_vertices[:, 0, 1] = -width / 2

    rotated_bbox_vertices[:, 1, 0] = length / 2
    rotated_bbox_vertices[:, 1, 1] = -width / 2

    rotated_bbox_vertices[:, 2, 0] = length / 2
    rotated_bbox_vertices[:, 2, 1] = width / 2

    rotated_bbox_vertices[:, 3, 0] = -length / 2
    rotated_bbox_vertices[:, 3, 1] = width / 2

    for i in range(4):
        th, r = cart2pol(rotated_bbox_vertices[:, i, :])
        rotated_bbox_vertices[:, i, :] = pol2cart(th + rotation, r).squeeze()
        rotated_bbox_vertices[:, i, :] = rotated_bbox_vertices[:, i, :] + centroid

    return rotated_bbox_vertices


def cart2pol(cart: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """ Transform cartesian to polar coordinates.

    Args:
        cart: Nx2 np.ndarray

    Returns:
        Pair of Nx1 np.ndarrays
    """
    if cart.shape == (2,):
        cart = np.array([cart])

    x = cart[:, 0]
    y = cart[:, 1]

    th = np.arctan2(y, x)
    r = np.sqrt(np.power(x, 2) + np.power(y, 2))
    return th, r


def pol2cart(theta, r) -> np.ndarray:
    """ Transform polar to cartesian coordinates.

    Args:
        theta: Nx1 ndarray
        r: Nx1 ndarray

    Returns:
        Nx2 ndarray
    """

    x = np.multiply(r, np.cos(theta))
    y = np.multiply(r, np.sin(theta))

    cart = np.array([x, y]).transpose()
    return cart


def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])


def add_offset_point(trajectory: "Trajectory", offset: float):
    """ Add in-place a small step at the end of the trajectory to reach within the boundary of the next lane. """
    heading = trajectory.heading[-1]
    direction = np.array([np.cos(heading), np.sin(heading)])
    point = trajectory.path[-1] + offset * direction
    velocity = trajectory.velocity[-1]
    trajectory.extend((np.array([point]), np.array([velocity])))
    return trajectory


class Box:
    """ A class representing a 2D, rotated box in Euclidean space. """
    def __init__(self, center: np.ndarray, length: float, width: float, heading: float):
        """ Create a new 2D Box.

        Args:
            center: The mid-point of the box.
            length: The horizontal length of the box from right side to the left.
            width: The vertical height of the box from top side to the bottom.
            heading: Rotation (radians) of the box from the reference frame of the box's center using counter-clockwise
                orientation.
        """
        self.center = np.array(center)
        self.length = length
        self.width = width
        self.heading = heading

        self._boundary = None
        self.calculate_boundary()

    def overlaps(self, other: "Box") -> bool:
        """ Check whether self overlaps with another Box.

        Ref: https://stackoverflow.com/questions/306316/determine-if-two-rectangles-overlap-each-other

        Args:
            other: Other box to check

        Returns:
            true iff the two boxes overlap in some region
        """
        if np.linalg.norm(self.center - other.center) > (self.diagonal + other.diagonal) / 2:
            return False
        self_intersects = any([self.inside(p) for p in other.boundary])
        other_intersects = any([other.inside(p) for p in self.boundary])
        return self_intersects or other_intersects

    def inside(self, p: np.ndarray) -> bool:
        """ Check whether a point lies within the rectangle.

        Ref: https://math.stackexchange.com/questions/190111/how-to-check-if-a-point-is-inside-a-rectangle

        Args:
            p: The point to check

        Returns:
            true iff the point lies in or on the rectangle
        """
        a, b, c, d = self._boundary
        am = p - a
        ab = b - a
        ad = d - a
        return (0 <= np.dot(am, ab) <= np.dot(ab, ab)) and (0 <= np.dot(am, ad) <= np.dot(ad, ad))

    def calculate_boundary(self):
        """ Calculate bounding box vertices from centroid, width and length """
        bbox = calculate_multiple_bboxes([self.center[0]], [self.center[1]], self.length, self.width, self.heading)[0]
        self._boundary = bbox

    @property
    def boundary(self) -> np.ndarray:
        """ Returns the bounding Polygon of the Box. """
        return self._boundary

    @property
    def diagonal(self) -> float:
        """ Length of the Box diagonal. """
        return np.sqrt(self.length * self.length + self.width * self.width)


class Circle:
    """ Class implementing a circle """

    def __init__(self, centre: np.ndarray, radius: float):
        self.centre = centre
        self.radius = radius

    def contains(self, point: np.ndarray):
        """ checks whether a 2d point is contained in a circle """
        dist_from_centre = np.linalg.norm(self.centre - point)
        return dist_from_centre <= self.radius
