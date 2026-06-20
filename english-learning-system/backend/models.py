from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    exercise_results = relationship("UserExerciseResult", back_populates="user", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    order_num = Column(Integer, default=0)
    level = Column(String(20), default="A1")
    created_at = Column(DateTime, default=datetime.utcnow)

    lessons = relationship("Lesson", back_populates="topic", cascade="all, delete-orphan")

    user_progress = relationship("UserProgress", back_populates="topic", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    order_num = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="lessons")

    exercises = relationship("Exercise", back_populates="lesson", cascade="all, delete-orphan")

    user_progress = relationship("UserProgress", back_populates="lesson", cascade="all, delete-orphan")


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    task = Column(Text, nullable=False)
    answer = Column(String(500), nullable=False)
    explanation = Column(Text)
    exercise_type = Column(String(50), default="fill_blank")
    created_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="exercises")

    results = relationship("UserExerciseResult", back_populates="exercise", cascade="all, delete-orphan")


class UserProgress(Base):
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="SET NULL"))
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="progress")
    topic = relationship("Topic", back_populates="user_progress")
    lesson = relationship("Lesson", back_populates="user_progress")


    __table_args__ = (
    )


class UserExerciseResult(Base):
    __tablename__ = "user_exercise_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_id = Column(Integer, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    is_correct = Column(Boolean, default=False)
    checked_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="exercise_results")
    exercise = relationship("Exercise", back_populates="results")

    __table_args__ = (
        UniqueConstraint('user_id', 'exercise_id', name='uq_user_exercise'),
    )