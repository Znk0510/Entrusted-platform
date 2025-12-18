#models/rating.py
from sqlalchemy import Column, Integer, Text, String, TIMESTAMP
from db import Base

class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer)
    rater_id = Column(Integer)
    ratee_id = Column(Integer)

    rating_direction = Column(String)
    overall_comment = Column(Text)
