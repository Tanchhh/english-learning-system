from fastapi import FastAPI, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, distinct
from typing import List, Optional
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

import models
import schemas
from database import engine, SessionLocal, get_db, Base
from auth import get_password_hash, verify_password, create_access_token, decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = BASE_DIR / "frontend" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        init_admin(db)
        if db.query(models.Topic).count() == 0:
            add_sample_data(db)
            print("✅ Тестовые данные успешно добавлены!")
        yield
    finally:
        db.close()


app = FastAPI(title="English Learning System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

security = HTTPBearer()
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_admin_user(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user


@app.post("/api/auth/login")
def login(
        username: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db)
):
    username = str(username).strip()
    password = str(password).strip()

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_admin": user.is_admin,
        "username": user.username
    }


@app.post("/api/auth/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    username = str(user.username).strip()
    password = str(user.password).strip()

    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")

    new_user = models.User(
        username=username,
        hashed_password=get_password_hash(password),
        is_admin=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}


@app.get("/api/users")
def get_users(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    users = db.query(models.User).all()
    result = []
    for user in users:
        # Считаем, сколько тем завершил пользователь
        completed = db.query(func.count(distinct(models.UserProgress.topic_id))).filter(
            models.UserProgress.user_id == user.id,
            models.UserProgress.is_completed == True
        ).scalar() or 0
        result.append({
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
            "completed_topics": completed
        })
    return result


@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    stats = db.query(
        models.User.id,
        models.User.username,
        func.count(distinct(models.UserProgress.topic_id)).label("score")
    ).outerjoin(
        models.UserProgress,
        (models.User.id == models.UserProgress.user_id) & (models.UserProgress.is_completed == True)
    ).group_by(models.User.id).order_by(func.count(distinct(models.UserProgress.topic_id)).desc()).all()

    leaderboard = []
    max_score = 1
    if stats:
        max_score = max([s.score for s in stats])

    for stat in stats:
        progress = round((stat.score / max_score) * 100) if max_score > 0 else 0
        leaderboard.append({
            "id": stat.id,
            "name": stat.username,
            "score": stat.score * 100,
            "progress": progress,
            "isOnline": False
        })
    return leaderboard


@app.post("/api/exercises/{exercise_id}/check")
def check_exercise(
        exercise_id: int,
        answer: str,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    is_correct = answer.strip().lower() == exercise.answer.strip().lower()

    result = db.query(models.UserExerciseResult).filter(
        models.UserExerciseResult.user_id == current_user.id,
        models.UserExerciseResult.exercise_id == exercise_id
    ).first()

    if not result:
        result = models.UserExerciseResult(
            user_id=current_user.id,
            exercise_id=exercise_id,
            topic_id=exercise.lesson.topic_id,
            is_correct=is_correct,
            checked_at=datetime.utcnow()
        )
        db.add(result)
    else:
        result.is_correct = is_correct
        result.checked_at = datetime.utcnow()

    db.commit()
    return {"is_correct": is_correct, "correct_answer": exercise.answer}


@app.post("/api/topics/{topic_id}/complete")
def complete_topic(
        topic_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    lessons = db.query(models.Lesson).filter(models.Lesson.topic_id == topic_id).all()

    all_exercise_ids = []
    for lesson in lessons:
        exercises = db.query(models.Exercise).filter(models.Exercise.lesson_id == lesson.id).all()
        all_exercise_ids.extend([ex.id for ex in exercises])

    if not all_exercise_ids:
        pass
    else:
        results = db.query(models.UserExerciseResult).filter(
            models.UserExerciseResult.user_id == current_user.id,
            models.UserExerciseResult.exercise_id.in_(all_exercise_ids)
        ).all()

        correct_count = sum(1 for r in results if r.is_correct)

        if correct_count < len(all_exercise_ids):
            raise HTTPException(
                status_code=400,
                detail=f"Выполнены верно только {correct_count} из {len(all_exercise_ids)}. Исправьте ошибки."
            )

    for lesson in lessons:
        progress = db.query(models.UserProgress).filter(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.lesson_id == lesson.id
        ).first()

        if not progress:
            progress = models.UserProgress(
                user_id=current_user.id,
                topic_id=topic_id,
                lesson_id=lesson.id,
                is_completed=True,
                completed_at=datetime.utcnow()
            )
            db.add(progress)
        else:
            progress.is_completed = True
            progress.completed_at = datetime.utcnow()

    db.commit()
    return {"message": "Topic completed successfully"}


@app.get("/api/profile/stats")
def get_profile_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    total_topics = db.query(models.Topic).count()

    completed_records = db.query(models.UserProgress).filter(
        models.UserProgress.user_id == current_user.id,
        models.UserProgress.is_completed == True
    ).all()

    unique_topic_ids = set(r.topic_id for r in completed_records)
    completed_count = len(unique_topic_ids)
    progress_percent = round((completed_count / total_topics) * 100, 1) if total_topics > 0 else 0

    completed_topics_list = []
    if unique_topic_ids:
        topics = db.query(models.Topic).filter(models.Topic.id.in_(unique_topic_ids)).all()
        completed_topics_list = [t.title for t in topics]

    return {
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "completed_topics": completed_count,
        "total_topics": total_topics,
        "progress_percent": progress_percent,
        "completed_topics_list": completed_topics_list
    }


@app.get("/api/topics", response_model=List[schemas.Topic])
def get_topics(db: Session = Depends(get_db)):
    return db.query(models.Topic).order_by(models.Topic.order_num).all()


@app.get("/api/topics/{topic_id}", response_model=schemas.Topic)
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(models.Topic) \
        .options(joinedload(models.Topic.lessons).joinedload(models.Lesson.exercises)) \
        .filter(models.Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@app.post("/api/topics", response_model=schemas.Topic)
def create_topic(topic: schemas.TopicCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_admin_user)):
    db_topic = models.Topic(**topic.dict())
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    return db_topic


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_admin_user)):
    db.query(models.UserProgress).filter(models.UserProgress.topic_id == topic_id).delete(synchronize_session=False)
    db.query(models.UserExerciseResult).filter(models.UserExerciseResult.topic_id == topic_id).delete(
        synchronize_session=False)
    db.commit()

    db_topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    db.delete(db_topic)
    db.commit()
    return {"message": "Topic deleted"}


@app.post("/api/lessons", response_model=schemas.Lesson)
def create_lesson(lesson: schemas.LessonCreate, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_admin_user)):
    db_lesson = models.Lesson(**lesson.dict())
    db.add(db_lesson)
    db.commit()
    db.refresh(db_lesson)
    return db_lesson


@app.delete("/api/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_admin_user)):
    db_lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not db_lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    db.delete(db_lesson)
    db.commit()
    return {"message": "Lesson deleted"}


@app.post("/api/exercises", response_model=schemas.Exercise)
def create_exercise(exercise: schemas.ExerciseCreate, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_admin_user)):
    db_exercise = models.Exercise(**exercise.dict())
    db.add(db_exercise)
    db.commit()
    db.refresh(db_exercise)
    return db_exercise


@app.delete("/api/exercises/{exercise_id}")
def delete_exercise(exercise_id: int, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_admin_user)):
    db_exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not db_exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    db.delete(db_exercise)
    db.commit()
    return {"message": "Exercise deleted"}


@app.get("/")
def read_root(): return FileResponse(BASE_DIR / "frontend" / "index.html")


@app.get("/topic/{topic_id}")
def read_topic(topic_id: int): return FileResponse(BASE_DIR / "frontend" / "topic.html")


@app.get("/admin")
def read_admin(): return FileResponse(BASE_DIR / "frontend" / "admin.html")


@app.get("/login")
def read_login(): return FileResponse(BASE_DIR / "frontend" / "login.html")


@app.get("/register")
def read_register(): return FileResponse(BASE_DIR / "frontend" / "register.html")


@app.get("/leaderboard")
def read_leaderboard(): return FileResponse(BASE_DIR / "frontend" / "leaderboard.html")


@app.get("/profile")
def read_profile(): return FileResponse(BASE_DIR / "frontend" / "profile.html")


@app.get("/contacts")
def read_contacts(): return FileResponse(BASE_DIR / "frontend" / "contacts.html")


def init_admin(db: Session):
    admin = db.query(models.User).filter(models.User.username == "admin").first()
    if not admin:
        admin = models.User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            is_admin=True
        )
        db.add(admin)
        db.commit()


def add_sample_data(db: Session):
    topics_data = [
        {
            "title": "Present Simple", "desc": "Настоящее простое время.", "level": "A1",
            "lessons": [{
                "title": "Образование Present Simple",
                "content": "**Утверждение:**\nI/You/We/They + V\nHe/She/It + V+s/es\n\n**Отрицание:**\ndon't / doesn't + V\n\n**Вопрос:**\nDo / Does + подлежащее + V?",
                "exercises": [
                    {"task": "He ___ (work) in a bank.", "answer": "works", "expl": "3-е лицо ед.ч. → +s/es",
                     "type": "fill_blank"},
                    {"task": "They ___ (not/like) pizza.", "answer": "don't like", "expl": "Отрицание для they",
                     "type": "fill_blank"},
                    {"task": "___ she speak English?", "answer": "Does", "expl": "Вопрос для she/he/it",
                     "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Past Simple", "desc": "Прошедшее простое время.", "level": "A1",
            "lessons": [{
                "title": "Правильные глаголы",
                "content": "**Правильные глаголы:**\nГлагол + ed\n\nwork → worked\nlive → lived\nstop → stopped\nstudy → studied",
                "exercises": [
                    {"task": "I ___ (watch) TV yesterday.", "answer": "watched", "expl": "Правильный глагол + ed",
                     "type": "fill_blank"},
                    {"task": "She ___ (play) tennis last Sunday.", "answer": "played", "expl": "play → played",
                     "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Articles (a/an/the)", "desc": "Артикли в английском языке.", "level": "A1",
            "lessons": [{
                "title": "Неопределённый артикль",
                "content": "**a** – перед согласным звуком (a book, a university)\n**an** – перед гласным звуком (an apple, an hour)",
                "exercises": [
                    {"task": "She is ___ doctor.", "answer": "a", "expl": "Профессия → a", "type": "fill_blank"},
                    {"task": "I have ___ umbrella.", "answer": "an", "expl": "Гласный звук → an", "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Present Continuous", "desc": "Настоящее длительное время.", "level": "A2",
            "lessons": [{
                "title": "Образование",
                "content": "**Формула:**\nam/is/are + V-ing\n\n**Примеры:**\n- I am reading\n- He is working\n- They are playing",
                "exercises": [
                    {"task": "I ___ (read) a book now.", "answer": "am reading", "expl": "am + V-ing",
                     "type": "fill_blank"},
                    {"task": "They ___ (play) football at the moment.", "answer": "are playing", "expl": "are + V-ing",
                     "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Future Simple", "desc": "Будущее простое время с will.", "level": "A2",
            "lessons": [{
                "title": "Образование",
                "content": "**Формула:**\nwill + глагол (для всех лиц)\n\n**Примеры:**\n- I will travel next year.\n- She will call you tomorrow.\n\n**Сокращение:**\nwill not = won't",
                "exercises": [
                    {"task": "I ___ (visit) my grandparents next week.", "answer": "will visit",
                     "expl": "Future: will + глагол", "type": "fill_blank"},
                    {"task": "He ___ (not/come) to the party.", "answer": "won't come", "expl": "won't = will not",
                     "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Лексика: Семья", "desc": "Основные слова по теме «Семья».", "level": "A1",
            "lessons": [{
                "title": "Члены семьи",
                "content": "**Родители:**\n- mother / mom — мама\n- father / dad — папа\n\n**Дети:**\n- son — сын\n- daughter — дочь\n\n**Другие:**\n- brother — брат\n- sister — сестра",
                "exercises": [
                    {"task": "Переведите: «моя сестра»", "answer": "my sister", "expl": "sister = сестра",
                     "type": "translation"},
                    {"task": "Переведите: «родители»", "answer": "parents", "expl": "parents = родители",
                     "type": "translation"}
                ]
            }]
        },
        {
            "title": "Модальные глаголы", "desc": "Can, must, should и другие.", "level": "A2",
            "lessons": [{
                "title": "Can / Could",
                "content": "**Can** — мочь, уметь (настоящее)\n**Could** — мочь (прошедшее) / вежливая просьба\n\n**Примеры:**\n- I can swim.\n- Could you help me?",
                "exercises": [
                    {"task": "I ___ speak English.", "answer": "can", "expl": "Умение в настоящем",
                     "type": "fill_blank"},
                    {"task": "___ you open the window, please?", "answer": "Could", "expl": "Вежливая просьба",
                     "type": "fill_blank"}
                ]
            }]
        },
        {
            "title": "Местоимения", "desc": "Личные, притяжательные, указательные.", "level": "A1",
            "lessons": [{
                "title": "Личные местоимения",
                "content": "**Подлежащее:**\nI, you, he, she, it, we, they\n\n**Дополнение:**\nme, you, him, her, it, us, them\n\n**Примеры:**\n- She loves me.\n- We know them.",
                "exercises": [
                    {"task": "Переведите: «он»", "answer": "he", "expl": "Личное местоимение", "type": "translation"},
                    {"task": "Переведите: «мы»", "answer": "we", "expl": "Личное местоимение", "type": "translation"}
                ]
            }]
        },
        {
            "title": "Степени сравнения прилагательных", "desc": "Comparative и Superlative.", "level": "A2",
            "lessons": [{
                "title": "Образование степеней сравнения",
                "content": "**Сравнительная:**\n- Короткие: adj + er (tall → taller)\n- Длинные: more + adj (beautiful → more beautiful)\n\n**Превосходная:**\n- Короткие: the + adj + est (tall → the tallest)\n- Длинные: the most + adj",
                "exercises": [
                    {"task": "big (сравнительная степень)", "answer": "bigger", "expl": "big → bigger",
                     "type": "fill_blank"},
                    {"task": "beautiful (превосходная степень)", "answer": "the most beautiful",
                     "expl": "длинное прилагательное", "type": "fill_blank"}
                ]
            }]
        }
    ]

    for idx, t_data in enumerate(topics_data, 1):
        topic = models.Topic(title=t_data["title"], description=t_data["desc"], order_num=idx, level=t_data["level"])
        db.add(topic)
        db.commit()

        for l_idx, l_data in enumerate(t_data["lessons"], 1):
            lesson = models.Lesson(topic_id=topic.id, title=l_data["title"], content=l_data["content"], order_num=l_idx)
            db.add(lesson)
            db.commit()

            exercises = [models.Exercise(lesson_id=lesson.id, task=e["task"], answer=e["answer"], explanation=e["expl"],
                                         exercise_type=e["type"]) for e in l_data["exercises"]]
            db.add_all(exercises)
            db.commit()



@app.put("/api/topics/{topic_id}", response_model=schemas.Topic)
def update_topic(
        topic_id: int,
        topic: schemas.TopicCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_admin_user)
):
    db_topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    db_topic.title = topic.title
    db_topic.description = topic.description
    db_topic.level = topic.level
    db_topic.order_num = topic.order_num

    db.commit()
    db.refresh(db_topic)
    return db_topic


@app.put("/api/lessons/{lesson_id}", response_model=schemas.Lesson)
def update_lesson(
        lesson_id: int,
        lesson: schemas.LessonCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_admin_user)
):
    db_lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not db_lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    db_lesson.title = lesson.title
    db_lesson.content = lesson.content
    db_lesson.order_num = lesson.order_num
    db_lesson.topic_id = lesson.topic_id

    db.commit()
    db.refresh(db_lesson)
    return db_lesson


@app.put("/api/exercises/{exercise_id}", response_model=schemas.Exercise)
def update_exercise(
        exercise_id: int,
        exercise: schemas.ExerciseCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_admin_user)
):
    db_exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not db_exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    db_exercise.task = exercise.task
    db_exercise.answer = exercise.answer
    db_exercise.explanation = exercise.explanation
    db_exercise.exercise_type = exercise.exercise_type
    db_exercise.lesson_id = exercise.lesson_id

    db.commit()
    db.refresh(db_exercise)
    return db_exercise

@app.get("/api/search")
def search_topics(
    q: str,  # поисковый запрос
    db: Session = Depends(get_db)
):
    results = db.query(models.Topic).filter(
        (models.Topic.title.ilike(f"%{q}%")) |
        (models.Topic.description.ilike(f"%{q}%"))
    ).all()
    return results

@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_admin_user)):
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson

@app.get("/api/exercises/{exercise_id}")
def get_exercise(exercise_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_admin_user)):
    exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise

@app.get("/api/lessons", response_model=List[schemas.Lesson])
def get_all_lessons(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    return db.query(models.Lesson).order_by(models.Lesson.order_num).all()

@app.get("/api/exercises", response_model=List[schemas.Exercise])
def get_all_exercises(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    return db.query(models.Exercise).all()

@app.get("/api/lessons/{lesson_id}", response_model=schemas.Lesson)
def get_lesson(lesson_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson

@app.get("/api/exercises/{exercise_id}", response_model=schemas.Exercise)
def get_exercise(exercise_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)