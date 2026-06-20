from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class TopicBase(BaseModel):
    title: str
    description: Optional[str] = None
    order_num: int = 0
    level: Optional[str] = None

class TopicCreate(TopicBase):
    pass

class Topic(TopicBase):
    id: int
    lessons: List["Lesson"] = []

    class Config:
        from_attributes = True

class LessonBase(BaseModel):
    title: str
    content: Optional[str] = None
    order_num: int = 0

class LessonCreate(LessonBase):
    topic_id: int

class Lesson(LessonBase):
    id: int
    topic_id: int
    exercises: List["Exercise"] = []

    class Config:
        from_attributes = True

class ExerciseBase(BaseModel):
    task: str
    answer: str
    explanation: Optional[str] = None
    exercise_type: Optional[str] = None

class ExerciseCreate(ExerciseBase):
    lesson_id: int

class Exercise(ExerciseBase):
    id: int
    lesson_id: int

    class Config:
        from_attributes = True

class ProgressBase(BaseModel):
    topic_id: int
    lesson_id: int
    is_completed: bool = False

class Progress(ProgressBase):
    id: int
    user_id: int
    completed_at: datetime

    class Config:
        from_attributes = True