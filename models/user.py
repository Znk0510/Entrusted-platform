# models/user.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from db import Base  # 你的 async SQLAlchemy Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # "client" 或 "contractor"
    role = Column(String, nullable=False)

    # rating 關聯
    ratings_received = relationship("Rating", foreign_keys="Rating.ratee_id", back_populates="ratee")
    ratings_given = relationship("Rating", foreign_keys="Rating.rater_id", back_populates="rater")
