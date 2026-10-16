"""Persistencia de perfiles de reglamento."""

from typing import Any

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class ProfileModel(Base):
    __tablename__ = "profile"
    __table_args__ = (CheckConstraint("jsonb_typeof(rules) = 'object'", name="ck_profile_rules"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    competition: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(120))
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
