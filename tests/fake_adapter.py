"""Records every geometry call a strategy makes; stands in for fusion/adapter.py."""
from MoldMaker.core.model import BBox


class FakeBody:
    def __init__(self, kind, **info):
        self.kind = kind
        self.info = info
        self.ops = []  # (op, tool_kind)


class FakeAdapter:
    def __init__(self, plan, removed_fraction=1.0):
        self.plan = plan
        self.removed_fraction = removed_fraction
        self.warnings = []
        self.committed = None
        self.flat = []
        self.offsets = []
        self.draft = []  # samples returned by draft_samples()
        self.bodies = []

    def _new(self, kind, **info):
        b = FakeBody(kind, **info)
        self.bodies.append(b)
        return b

    def master(self):
        return self._new("master")

    def box(self, bb):
        assert isinstance(bb, BBox)
        return self._new("box", bbox=bb)

    def cylinder(self, p0, p1, r0, r1=None):
        return self._new("cyl", p0=p0, p1=p1, r0=r0, r1=r0 if r1 is None else r1)

    def sphere(self, c, r):
        return self._new("sphere", c=c, r=r)

    def hex_prism(self, x, y, z0, z1, af):
        return self._new("hex", x=x, y=y, z0=z0, z1=z1, af=af)

    def offset(self, body, distance_mm):
        o = self._new("offset", source=body, distance=distance_mm, bbox=body.info.get("bbox"))
        self.offsets.append(o)
        return o

    def slot(self, p0, p1, width, z0, z1):
        return self._new("slot", p0=p0, p1=p1, width=width, z0=z0, z1=z1)

    def apply_draft(self, plan):
        self.draft_applied = True

    def copy(self, body):
        c = self._new(body.kind, **body.info)
        c.ops = list(body.ops)
        return c

    def union(self, target, tool):
        target.ops.append(("union", tool.kind))

    def cut(self, target, tool):
        target.ops.append(("cut", tool.kind))

    def intersect(self, target, tool):
        target.ops.append(("intersect", tool.kind))

    def volume(self, body):
        if body.kind == "offset":
            return 1000.0 * (1 + (1 if body.info["distance"] > 0 else -1) * 0.1)
        if body.kind == "master":
            return 1000.0
        cut_master = ("cut", "master") in body.ops
        removed = self.plan.metrics.get("Expected cavity volume (cm3)", 1.0) * 1000 * self.removed_fraction if cut_master else 0
        return body.info["bbox"].volume - removed

    def lay_flat(self, body, plan):
        self.flat.append(body)

    def draft_samples(self):
        return self.draft

    def warn(self, msg):
        self.warnings.append(msg)

    def commit(self, parts):
        self.committed = parts

    @staticmethod
    def count(body, op, kind):
        return sum(1 for o in body.ops if o == (op, kind))
