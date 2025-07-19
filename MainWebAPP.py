from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, ForeignKey, JSON, Enum as SQLEnum, func
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional, List
import os
import csv
import io
import pandas as pd
from io import BytesIO
import uuid
import logging


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация приложения
app = FastAPI(title="Donor Management System")

# Настройка базы данных
DATABASE_URL = "sqlite:///C:/Users/Иван/PycharmProjects/abobych/donor.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Модели данных
class DonorType(str, Enum):
    STUDENT = "student"
    STAFF = "staff"
    EXTERNAL = "external"

    @classmethod
    def _missing_(cls, value):
        value = value.lower()
        for member in cls:
            if member.value == value:
                return member
        return None

class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    phone = Column(String(20))
    email = Column(String(100))
    name = Column(String(100))
    donor_type = Column(SQLEnum(DonorType))
    group = Column(String(20), nullable=True)
    consent_given = Column(Boolean, default=False)
    consent_date = Column(Date, nullable=True)
    in_bm_registry = Column(Boolean, default=False)
    registered_events = Column(JSON, default=[])
    donations = relationship("Donation", back_populates="user")
    questions = relationship("Question", back_populates="user")
    organizer_requests = relationship("OrganizerRequest", back_populates="user")


class OrganizerRequest(Base):
    __tablename__ = 'organizer_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    status = Column(SQLEnum(RequestStatus), default=RequestStatus.PENDING)
    rejection_reason = Column(String(500), nullable=True)
    request_date = Column(Date, default=datetime.now)
    user = relationship("User", back_populates="organizer_requests")


class Donation(Base):
    __tablename__ = 'donations'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(Date)
    center = Column(String(100))
    successful = Column(Boolean, default=True)
    volume = Column(Integer, nullable=True)
    blood_type = Column(String(5), nullable=True)
    user = relationship("User", back_populates="donations")


class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    date = Column(Date)
    center = Column(String(100))
    address = Column(String(200))
    description = Column(String(1000), nullable=True)
    slots_available = Column(Integer)
    is_active = Column(Boolean, default=True)
    organizer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    registrations = relationship("Registration", back_populates="event")


class Registration(Base):
    __tablename__ = 'registrations'
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    attended = Column(Boolean, default=False)
    event = relationship("Event", back_populates="registrations")
    user = relationship("User")


class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    text = Column(String(1000))
    answered = Column(Boolean, default=False)
    answer = Column(String(1000), nullable=True)
    timestamp = Column(Date, default=datetime.now)
    user = relationship("User", back_populates="questions")


class Mailing(Base):
    __tablename__ = 'mailings'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    text = Column(String(1000))
    recipients = Column(String(50))
    sent_date = Column(Date, default=datetime.now)


class StatsFile(Base):
    __tablename__ = 'stats_files'
    id = Column(Integer, primary_key=True)
    filename = Column(String(100))
    file_path = Column(String(200))
    upload_date = Column(Date, default=datetime.now)
    event_date = Column(Date)


# Удаляем существующую базу и создаем заново с актуальной схемой

# Подключение статических файлов и шаблонов
os.makedirs("static/fonts/Inter", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Зависимости
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Вспомогательные функции
def get_last_donation(db: Session, user_id: int) -> Optional[Donation]:
    return db.query(Donation) \
        .filter(Donation.user_id == user_id) \
        .order_by(Donation.date.desc()) \
        .first()


def get_event_stats(db: Session, event_id: int):
    event = db.query(Event).get(event_id)
    if not event:
        return None

    total_registrations = db.query(Registration).filter_by(event_id=event_id).count()
    attended = db.query(Registration).filter_by(event_id=event_id, attended=True).count()

    return {
        "event": event,
        "total_registrations": total_registrations,
        "attended": attended,
        "attendance_rate": round(attended / total_registrations * 100, 2) if total_registrations else 0
    }


def generate_excel_report(db: Session, start_date: date, end_date: date):
    # Получаем данные о донациях
    donations = db.query(Donation).filter(Donation.date >= start_date, Donation.date <= end_date).all()

    # Получаем данные о мероприятиях
    events = db.query(Event).filter(Event.date >= start_date, Event.date <= end_date).all()

    # Создаем DataFrame для донаций
    donations_data = []
    for d in donations:
        donations_data.append({
            "ID": d.id,
            "Дата": d.date,
            "Центр крови": d.center,
            "Донор": d.user.name,
            "Телефон": d.user.phone,
            "Успешно": "Да" if d.successful else "Нет",
            "Объем": d.volume,
            "Группа крови": d.blood_type
        })

    # Создаем DataFrame для мероприятий
    events_data = []
    for e in events:
        stats = get_event_stats(db, e.id)
        events_data.append({
            "ID мероприятия": e.id,
            "Название": e.name,
            "Дата": e.date,
            "Центр крови": e.center,
            "Адрес": e.address,
            "Всего регистраций": stats["total_registrations"],
            "Присутствовало": stats["attended"],
            "Процент посещаемости": stats["attendance_rate"]
        })

    # Создаем Excel файл в памяти
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if donations_data:
            df_donations = pd.DataFrame(donations_data)
            df_donations.to_excel(writer, sheet_name='Донации', index=False)

        if events_data:
            df_events = pd.DataFrame(events_data)
            df_events.to_excel(writer, sheet_name='Мероприятия', index=False)

    output.seek(0)
    return output


# Маршруты для страниц
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/general_stats")


@app.get("/donors", response_class=HTMLResponse)
async def donors_page(request: Request, db: Session = Depends(get_db)):
    donors = db.query(User).all()
    donor_data = []
    for donor in donors:
        last_donation = get_last_donation(db, donor.id)
        donor_data.append({
            "id": donor.id,
            "name": donor.name,
            "phone": donor.phone,
            "last_donation": last_donation,
            "donor_type": donor.donor_type
        })
    return templates.TemplateResponse("donors.html", {
        "request": request,
        "donors": donor_data,
        "now": datetime.now()
    })


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.date).all()
    events_data = []
    for event in events:
        stats = get_event_stats(db, event.id)
        events_data.append({
            "event": event,
            "stats": stats
        })

    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": events_data,
        "now": datetime.now()
    })


@app.get("/mailings", response_class=HTMLResponse)
async def mailings_page(request: Request, db: Session = Depends(get_db)):
    mailings = db.query(Mailing).all()
    return templates.TemplateResponse("mailings.html", {
        "request": request,
        "mailings": mailings
    })


@app.get("/upload_stats", response_class=HTMLResponse)
async def upload_stats_page(request: Request, db: Session = Depends(get_db)):
    stats_files = db.query(StatsFile).all()
    return templates.TemplateResponse("upload_stats.html", {
        "request": request,
        "stats_files": stats_files
    })


@app.get("/download_stats", response_class=HTMLResponse)
async def download_stats_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("download_stats.html", {
        "request": request
    })


@app.get("/general_stats", response_class=HTMLResponse)
async def general_stats_page(request: Request, db: Session = Depends(get_db)):
    # Общая статистика
    total_donors = db.query(User).count()
    total_donations = db.query(Donation).count()
    active_events = db.query(Event).filter(Event.is_active == True).count()

    # Статистика по мероприятиям
    event_stats = []
    events = db.query(Event).filter(Event.date >= date.today() - timedelta(days=30)).all()
    for event in events:
        stats = get_event_stats(db, event.id)
        event_stats.append(stats)

    return templates.TemplateResponse("general_stats.html", {
        "request": request,
        "stats": {
            "total_donors": total_donors,
            "total_donations": total_donations,
            "active_events": active_events
        },
        "event_stats": event_stats,
        "now": datetime.now()
    })


# API для обработки форм
@app.post("/api/mailing/")
async def create_mailing(
        request: Request,
        name: str = Form(...),
        text: str = Form(...),
        recipients: str = Form(...),
        db: Session = Depends(get_db)
):
    try:
        logger.info(f"Creating mailing: name={name}, recipients={recipients}")

        mailing = Mailing(
            name=name,
            text=text,
            recipients=recipients
        )
        db.add(mailing)
        db.commit()
        logger.info(f"Mailing created with ID: {mailing.id}")
        return RedirectResponse(url="/mailings", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating mailing: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка при создании рассылки: {str(e)}"
        })


@app.post("/api/event/")
async def create_event(
        request: Request,
        name: str = Form(...),
        center: str = Form(...),
        address: str = Form(...),
        event_date: date = Form(...),
        slots: int = Form(...),
        description: str = Form(...),
        db: Session = Depends(get_db)
):
    try:
        logger.info(f"Creating event: name={name}, center={center}, date={event_date}")

        event = Event(
            name=name,
            center=center,
            address=address,
            date=event_date,
            slots_available=slots,
            description=description,
            is_active=True
        )
        db.add(event)
        db.commit()
        logger.info(f"Event created with ID: {event.id}")
        return RedirectResponse(url="/events", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating event: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка при создании мероприятия: {str(e)}"
        })


@app.post("/api/upload_stats/")
async def upload_stats(
        request: Request,
        file: UploadFile = File(...),
        event_date: date = Form(...),
        db: Session = Depends(get_db)
):
    try:
        logger.info(f"Uploading stats file: {file.filename}, event_date={event_date}")

        # Сохраняем файл на диск
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = f"static/uploads/{unique_filename}"

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        logger.info(f"File saved to: {file_path}")

        # Сохраняем информацию о файле в БД
        stats_file = StatsFile(
            filename=file.filename,
            file_path=file_path,
            event_date=event_date
        )
        db.add(stats_file)
        db.commit()
        logger.info(f"StatsFile created with ID: {stats_file.id}")

        return RedirectResponse(url="/upload_stats", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading stats: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка при загрузке файла: {str(e)}"
        })


@app.post("/api/download_stats/")
async def download_stats(
        start_date: date = Form(...),
        end_date: date = Form(...),
        db: Session = Depends(get_db)
):
    try:
        logger.info(f"Generating report for period: {start_date} to {end_date}")
        excel_file = generate_excel_report(db, start_date, end_date)
        filename = f"report_{start_date}_{end_date}.xlsx"

        return StreamingResponse(
            io.BytesIO(excel_file.getvalue()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return Response(content=f"Ошибка генерации отчета: {str(e)}", status_code=500)


# Маршрут для шрифтов
@app.get("/static/fonts/Inter/{font_file}")
async def get_font(font_file: str):
    font_path = f"static/fonts/Inter/{font_file}"
    if os.path.exists(font_path):
        return FileResponse(font_path)
    raise HTTPException(status_code=404, detail="Font not found")


# Страница ошибки
@app.get("/error")
async def error_page(request: Request, error: str = "Неизвестная ошибка"):
    return templates.TemplateResponse("error.html", {"request": request, "error": error})


# Запуск приложения
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)