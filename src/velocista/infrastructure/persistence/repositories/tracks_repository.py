"""Repositorio SQLAlchemy del contexto `tracks`. Implementa el port `TracksRepository`."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from velocista.domain.tracks.entities import Board, Point, Start, Track, Zone
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.tracks import TrackModel


def _to_entity(row: TrackModel) -> Track:
    return Track(
        id=row.id,
        name=row.name,
        board=Board(width_cm=row.board_width_cm, height_cm=row.board_height_cm),
        closed=row.closed,
        points=tuple(
            Point(x=p["x"], y=p["y"], radius=p["radius"], gap=p["gap"]) for p in row.points
        ),
        zones=tuple(
            Zone(x=z["x"], y=z["y"], width=z["width"], height=z["height"], name=z["name"])
            for z in row.zones
        ),
        start=Start(edge=row.start_edge, t=row.start_t),
        profile_id=row.profile_id,
        length_cm=row.length_cm,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _fields(track: Track) -> dict:
    return {
        "name": track.name,
        "board_width_cm": track.board.width_cm,
        "board_height_cm": track.board.height_cm,
        "closed": track.closed,
        "points": [{"x": p.x, "y": p.y, "radius": p.radius, "gap": p.gap} for p in track.points],
        "zones": [
            {"x": z.x, "y": z.y, "width": z.width, "height": z.height, "name": z.name}
            for z in track.zones
        ],
        "start_edge": track.start.edge,
        "start_t": track.start.t,
        "profile_id": track.profile_id,
        "length_cm": track.length_cm,
    }


class SqlAlchemyTracksRepository:
    def __init__(self, session):
        self.session = session

    def list_tracks(self, *, limit, offset):
        total = self.session.scalar(select(func.count()).select_from(TrackModel))
        rows = self.session.scalars(
            select(TrackModel)
            .order_by(TrackModel.updated_at.desc(), TrackModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_entity(row) for row in rows], total

    def get_track(self, track_id):
        row = self.session.get(TrackModel, track_id)
        return _to_entity(row) if row else None

    def add_track(self, track):
        now = datetime.now(UTC)
        row = TrackModel(**_fields(track), created_at=now, updated_at=now)
        self.session.add(row)
        self.session.commit()
        return _to_entity(row)

    def update_track(self, track_id, track):
        row = self.session.get(TrackModel, track_id)
        if row is None:
            return None
        for name, value in _fields(track).items():
            setattr(row, name, value)
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        return _to_entity(row)

    def delete_track(self, track_id):
        row = self.session.get(TrackModel, track_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def profile_exists(self, profile_id):
        return self.session.get(ProfileModel, profile_id) is not None
