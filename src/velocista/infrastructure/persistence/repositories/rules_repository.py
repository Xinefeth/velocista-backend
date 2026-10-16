from sqlalchemy import select

from velocista.infrastructure.persistence.models.rules import ProfileModel


def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


class SqlAlchemyRulesRepository:
    def __init__(self, session):
        self.session = session

    def list_profiles(self):
        return [
            as_dict(row)
            for row in self.session.scalars(select(ProfileModel).order_by(ProfileModel.id))
        ]

    def get_profile(self, profile_id):
        row = self.session.get(ProfileModel, profile_id)
        return as_dict(row) if row else None
