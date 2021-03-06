import re
import math

from spyce.vector import Vec3
import spyce.physics


class InvalidConstellation(Exception):
    pass


class CelestialBody:
    """Celestial Body

    Minimalistic model of celestial bodies (stars, planets, moons)
    It includes a few handy methods to plan orbital travel.
    """

    def __init__(self, name, gravitational_parameter=0, radius=0,
                 rotational_period=0, north_pole=None, orbit=None, **_):
        """Definition of a celestial body

        Arguments:
        name
        gravitational_parameter  m^3/s^2
        radius                   m, optional
        rotational_period        s, optional, 0 for tidal lock
        orbit                    Orbit, optional
        """
        self.name = name
        self.radius = float(radius)
        self.gravitational_parameter = float(gravitational_parameter)
        self.north_pole = north_pole
        self.orbit = orbit

        self.mass = self.gravitational_parameter/spyce.physics.G

        self.satellites = []
        if self.orbit is not None:
            self.orbit.primary.satellites.append(self)

        # rotational period
        if rotational_period == 0 and orbit is not None:
            self.rotational_period = self.orbit.period
        else:
            self.rotational_period = float(rotational_period)

        # axial tilt
        if north_pole is None:
            self.tilt = 0
        else:
            # from http://www.krysstal.com/sphertrig.html
            # the blue great circle is the ecliptic
            # A is the normal of the ecliptic
            # B is the north pole of the body
            # C is the normal of the orbital plane
            # a is the axial tilt of the body
            # b is the orbital inclination
            # c is the complement of the ecliptic latitude of the north pole
            # B' is the ecliptic longitude of the north pole
            # C' is orthogonal to the line of nodes
            b = orbit.inclination
            c = north_pole.ecliptic_latitude - math.pi/2
            if rotational_period < 0:  # retrograde rotation
                c += math.pi
            A = orbit.longitude_of_ascending_node+math.pi/2 - \
                north_pole.ecliptic_longitude
            ca = math.cos(b)*math.cos(c) + math.sin(b)*math.sin(c)*math.cos(A)
            self.tilt = math.acos(ca)

        # sphere of influence
        if self.orbit is None:
            self.sphere_of_influence = math.inf
        else:
            a = self.orbit.semi_major_axis
            mu_p = self.orbit.primary.gravitational_parameter
            mu_b = self.gravitational_parameter
            self.sphere_of_influence = a * (mu_b / mu_p)**0.4

        # solar day
        if self.orbit is not None:
            sidereal_day = self.rotational_period
            sidereal_year = self.orbit.period
            solar_year = sidereal_year - sidereal_day
            if solar_year == 0:
                self.solar_day = math.inf
            else:
                self.solar_day = sidereal_day * sidereal_year/solar_year
        else:
            self.solar_day = 0

        # surface velocity
        if self.rotational_period == 0:
            self.surface_velocity = math.inf
        else:
            R = self.radius
            self.surface_velocity = 2*math.pi * R / self.rotational_period

    def __repr__(self):
        """Appear as <Name> in a Python interpreter"""
        return "<%s>" % (self.name)

    def __str__(self):
        """Cast to string using the name"""
        return self.name

    def global_position_at_time(self, time):
        """Global position of the celestial body within the stellar system"""
        if self.orbit is None:
            return Vec3([0, 0, 0])
        primary_position = self.orbit.primary.global_position_at_time(time)
        return primary_position + self.orbit.position_at_time(time)

    def gravity(self, distance=None):
        """Gravity at given distance from center

        Defaults to surface gravity
        """
        if distance is None:
            distance = self.radius
        if not distance:
            return 0.
        mu = self.gravitational_parameter
        if distance < self.radius:
            # see https://en.wikipedia.org/wiki/Shell_theorem
            mu *= distance**3/self.radius**3
        return mu / distance**2

    def time2str(self, seconds):
        """Convert a duration (s) to a human-readable string

        The string will use conventional minutes and hours,
        as well as local days (based on rotational period)
        and local years (based on orbital period)

        See str2time()
        """
        sign = "-" if seconds < 0 else "+"
        seconds = abs(float(seconds))
        y, seconds = divmod(seconds, self.orbit.period)
        d, seconds = divmod(seconds, self.rotational_period)
        h, seconds = divmod(seconds, 3600)
        m, seconds = divmod(seconds, 60)
        return sign + "%.5gy,%4ud,%3u:%02u:%04.1f" % (y, d, h, m, seconds)

    def str2time(self, formatted_time):
        """Extract a duration (s) from formated time

        See time2str()
        """
        regex = re.compile(
            r"([-+]?)"  # sign
            r"(?:(\d+)y[\s,]*)?"  # years
            r"(?:(\d+)d[\s,]*)?"  # days
            r"(?:"
            r"(\d+):(\d+)"  # hours:minutes
            r"(?::(\d+(?:\.\d+)?))?"  # :seconds.fraction
            r")?"
        )
        match = regex.match(formatted_time)
        groups = match.groups()
        y, d, h, m, s = (float(group) if group else 0 for group in groups[1:])

        s += y * self.orbit.period
        s += d * self.rotational_period
        s += h * 3600
        s += m * 60
        return -s if groups[0] == "-" else s

    def escape_velocity_at_distance(self, distance):
        """Escape velocity at a given distance (m)"""
        return math.sqrt(2 * self.gravitational_parameter / distance)

    def angular_diameter(self, distance):
        """Angular diameter / apparent size at a given distance (m)"""
        return 2 * math.asin(self.radius/distance)

    def constellation_minimum_size(self, communication_range):
        """Return the minimum size of a circular constellation

        A circular constellation is a group of interconnected satellites evenly
        distributed on the same circular orbit. This brings two constraints:

        * line of sight above the horizon
        * next satellite within communication range
        """
        # derived from constellation_radius() by solving "minimum > maximum"
        return math.ceil(math.pi/math.atan(communication_range/self.radius/2))

    def constellation_radius(self, communication_range, size):
        """Return the range of possible radiuses for a circular constellation

        A circular constellation is a group of interconnected satellites evenly
        distributed on the same circular orbit. This brings two constraints:

        * line of sight above the horizon
        * next satellite within communication range

        The `size` of the constellation refers to the number of satellites (at
        least 3).

        The value returned is of the form `(minimum_radius, maximum_radius)`.
        """
        if size < 3:
            raise InvalidConstellation('need at least 3 satellites')
        return (
            self.radius / math.cos(math.pi/size),  # minimum (line of sight)
            communication_range / math.sin(math.pi/size)/2,  # maximum (range)
        )
