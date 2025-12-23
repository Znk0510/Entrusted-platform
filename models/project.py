# models/project.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db import Base

class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    contractor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="open")  # open / in_progress / completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # relationship
    client = db.relationship("User", foreign_keys=[client_id])
    contractor = db.relationship("User", foreign_keys=[contractor_id])

    ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

