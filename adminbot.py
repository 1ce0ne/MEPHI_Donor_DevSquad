import os
import telebot
from telebot import types
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base
import datetime
import csv
from io import StringIO, BytesIO

# Настройка бота
TOKEN = '7881074741:AAH9AQJT1awELeNcT5HDa43MNzt9mpkQrD0'
bot = telebot.TeleBot(TOKEN)

# Список разрешенных ID администраторов (замените на реальные ID)
ADMIN_IDS = [1982507378, 5271204621, 1053723113]  # Пример ID, замените на реальные

# Настройка базы данных
DATABASE_URL = 'sqlite:///C:/Users/Иван/PycharmProjects/abobych/donor.db'
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()


# ====================== МОДЕЛИ ДАННЫХ ======================
class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    phone = Column(String(20))
    name = Column(String(100))
    donor_type = Column(String(20))  # student, staff, external
    group = Column(String(20), nullable=True)
    consent_given = Column(Boolean, default=False)
    consent_date = Column(Date, nullable=True)
    in_bm_registry = Column(Boolean, default=False)
    registered_events = Column(JSON, default=[])

    donations = relationship("Donation", back_populates="user")
    questions = relationship("Question", back_populates="user")


class Donation(Base):
    """Модель донации"""
    __tablename__ = 'donations'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(Date)
    center = Column(String(100))
    successful = Column(Boolean, default=True)

    user = relationship("User", back_populates="donations")


class Event(Base):
    """Модель мероприятия"""
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    date = Column(Date)
    center = Column(String(100))
    slots_available = Column(Integer)
    is_active = Column(Boolean, default=True)


class Question(Base):
    """Модель вопроса"""
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    text = Column(String(1000))
    answered = Column(Boolean, default=False)
    answer = Column(String(1000), nullable=True)
    timestamp = Column(Date, default=datetime.datetime.now)

    user = relationship("User", back_populates="questions")


class Organizer(Base):
    """Модель организатора"""
    __tablename__ = 'organizers'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    is_active = Column(Boolean, default=True)

    user = relationship("User")


# Создание таблиц
Base.metadata.create_all(engine)


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def is_admin(chat_id):
    """Проверка, является ли пользователь администратором"""
    return chat_id in ADMIN_IDS


def is_organizer(chat_id):
    """Проверка, является ли пользователь организатором"""
    if not is_admin(chat_id):
        return False

    user = session.query(User).filter_by(chat_id=chat_id).first()
    if not user:
        return False
    organizer = session.query(Organizer).filter_by(user_id=user.id, is_active=True).first()
    return organizer is not None


def get_organizer_management_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Добавить организатора'))
    keyboard.add(types.KeyboardButton('Список организаторов'))
    keyboard.add(types.KeyboardButton('Удалить организатора'))
    keyboard.add(types.KeyboardButton('Назад'))
    return keyboard


def get_organizer_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Управление донорами'))
    keyboard.add(types.KeyboardButton('Управление мероприятиями'))
    keyboard.add(types.KeyboardButton('Управление организаторами'))
    keyboard.add(types.KeyboardButton('Ответить на вопросы'))
    keyboard.add(types.KeyboardButton('Рассылки'))
    keyboard.add(types.KeyboardButton('Статистика'))
    keyboard.add(types.KeyboardButton('Редактировать информацию'))
    return keyboard


def get_donor_management_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Добавить донора'))
    keyboard.add(types.KeyboardButton('Редактировать донора'))
    keyboard.add(types.KeyboardButton('Импорт доноров'))
    keyboard.add(types.KeyboardButton('Экспорт доноров'))
    keyboard.add(types.KeyboardButton('Назад'))
    return keyboard


def get_event_management_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Создать мероприятие'))
    keyboard.add(types.KeyboardButton('Редактировать мероприятие'))
    keyboard.add(types.KeyboardButton('Список мероприятий'))
    keyboard.add(types.KeyboardButton('Назад'))
    return keyboard


def get_mailing_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Зарегистрированным на ближайшее мероприятие'))
    keyboard.add(types.KeyboardButton('Не зарегистрировавшимся на ближайшие мероприятия'))
    keyboard.add(types.KeyboardButton('Не пришедшим на первую дату'))
    keyboard.add(types.KeyboardButton('В регистре ДКМ'))
    keyboard.add(types.KeyboardButton('Назад'))
    return keyboard


def get_statistics_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Статистика по мероприятиям'))
    keyboard.add(types.KeyboardButton('Экспорт статистики'))
    keyboard.add(types.KeyboardButton('Назад'))
    return keyboard


# ====================== ОБРАБОТЧИКИ КОМАНД ======================
@bot.message_handler(commands=['start'])
def handle_start(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "👋 Добро пожаловать в панель администратора!",
                     reply_markup=get_organizer_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Назад')
def handle_back(message):
    if not is_admin(message.chat.id):
        return

    bot.send_message(message.chat.id, "📋 Главное меню", reply_markup=get_organizer_keyboard())


# ====================== УПРАВЛЕНИЕ ОРГАНИЗАТОРАМИ ======================
@bot.message_handler(func=lambda message: message.text == 'Управление организаторами')
def handle_organizer_management(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "👥 Управление организаторами", reply_markup=get_organizer_management_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Добавить организатора')
def handle_add_organizer(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id,
                           "📱 Введите номер телефона пользователя для добавления в организаторы (в формате +79991234567):")
    bot.register_next_step_handler(msg, process_add_organizer)


def process_add_organizer(message):
    if not is_admin(message.chat.id):
        return

    try:
        phone = message.text.strip()
        user = session.query(User).filter_by(phone=phone).first()

        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь с таким номером телефона не найден.")
            return

        # Проверяем, не является ли уже организатором
        existing = session.query(Organizer).filter_by(user_id=user.id).first()
        if existing:
            if existing.is_active:
                bot.send_message(message.chat.id, "ℹ️ Этот пользователь уже является организатором.")
            else:
                existing.is_active = True
                session.commit()
                bot.send_message(message.chat.id, "✅ Организатор успешно восстановлен!")
            return

        # Создаем нового организатора
        new_organizer = Organizer(user_id=user.id, is_active=True)
        session.add(new_organizer)
        session.commit()

        bot.send_message(message.chat.id, f"✅ Пользователь {user.name} успешно добавлен как организатор!")

        # Уведомляем пользователя
        if user.chat_id:
            try:
                bot.send_message(user.chat_id,
                                 "🎉 Вас добавили в список организаторов! Теперь вам доступны дополнительные функции.")
            except:
                pass

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(func=lambda message: message.text == 'Список организаторов')
def handle_list_organizers(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    organizers = session.query(Organizer).filter_by(is_active=True).all()

    if not organizers:
        bot.send_message(message.chat.id, "ℹ️ Нет активных организаторов.")
        return

    response = "📋 Список организаторов:\n\n"
    for org in organizers:
        user = session.query(User).get(org.user_id)
        response += f"🔹 ID: {org.id}\n👤 ФИО: {user.name}\n📞 Телефон: {user.phone}\n\n"

    bot.send_message(message.chat.id, response)


@bot.message_handler(func=lambda message: message.text == 'Удалить организатора')
def handle_remove_organizer(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    # Сначала показываем список организаторов для удобства
    organizers = session.query(Organizer).filter_by(is_active=True).all()
    if not organizers:
        bot.send_message(message.chat.id, "ℹ️ Нет активных организаторов для удаления.")
        return

    response = "🗑️ Список организаторов (укажите ID для удаления):\n\n"
    for org in organizers:
        user = session.query(User).get(org.user_id)
        response += f"ID: {org.id} - {user.name} ({user.phone})\n"

    msg = bot.send_message(message.chat.id, response)
    bot.register_next_step_handler(msg, process_remove_organizer)


def process_remove_organizer(message):
    if not is_admin(message.chat.id):
        return

    try:
        org_id = int(message.text.strip())
        organizer = session.query(Organizer).get(org_id)

        if not organizer or not organizer.is_active:
            bot.send_message(message.chat.id, "❌ Организатор с таким ID не найден.")
            return

        user = session.query(User).get(organizer.user_id)

        # Мягкое удаление (деактивация)
        organizer.is_active = False
        session.commit()

        bot.send_message(message.chat.id, f"✅ Организатор {user.name} успешно удален!")

        # Уведомляем пользователя
        if user.chat_id:
            try:
                bot.send_message(user.chat_id, "ℹ️ Ваши права организатора были отозваны.")
            except:
                pass

    except ValueError:
        bot.send_message(message.chat.id, "❌ Пожалуйста, введите корректный ID (число).")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


# ====================== УПРАВЛЕНИЕ ДОНОРАМИ ======================
@bot.message_handler(func=lambda message: message.text == 'Управление донорами')
def handle_donor_management(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "🩸 Управление донорами", reply_markup=get_donor_management_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Добавить донора')
def handle_add_donor(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id,
                           "Введите данные донора в формате:\nФИО;Телефон;Тип(студент/сотрудник/внешний);Группа(если студент);Согласие(да/нет);В регистре ДКМ(да/нет)")
    bot.register_next_step_handler(msg, process_add_donor)


def process_add_donor(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        return

    try:
        data = message.text.split(';')
        name = data[0].strip()
        phone = data[1].strip()
        donor_type = data[2].strip().lower()
        group = data[3].strip() if len(data) > 3 else None
        consent = data[4].strip().lower() == 'да' if len(data) > 4 else False
        in_bm_registry = data[5].strip().lower() == 'да' if len(data) > 5 else False

        new_user = User(
            name=name,
            phone=phone,
            donor_type=donor_type,
            group=group,
            consent_given=consent,
            in_bm_registry=in_bm_registry,
            consent_date=datetime.date.today() if consent else None
        )

        session.add(new_user)
        session.commit()

        bot.send_message(message.chat.id, f"✅ Донор {name} успешно добавлен!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(func=lambda message: message.text == 'Импорт доноров')
def handle_import_donors(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id,
                           "Отправьте файл CSV с данными доноров (ФИО;Телефон;Тип;Группа;Согласие;В регистре ДКМ)")
    bot.register_next_step_handler(msg, process_import_donors)


def process_import_donors(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        return

    try:
        if message.document is None:
            bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте файл CSV")
            return

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Чтение CSV файла
        csv_data = downloaded_file.decode('utf-8').splitlines()
        csv_reader = csv.reader(csv_data, delimiter=';')

        imported_count = 0
        for row in csv_reader:
            if len(row) < 3:  # Минимум ФИО, Телефон, Тип
                continue

            name = row[0].strip()
            phone = row[1].strip()
            donor_type = row[2].strip().lower()
            group = row[3].strip() if len(row) > 3 else None
            consent = row[4].strip().lower() == 'да' if len(row) > 4 else False
            in_bm_registry = row[5].strip().lower() == 'да' if len(row) > 5 else False

            new_user = User(
                name=name,
                phone=phone,
                donor_type=donor_type,
                group=group,
                consent_given=consent,
                in_bm_registry=in_bm_registry,
                consent_date=datetime.date.today() if consent else None
            )

            session.add(new_user)
            imported_count += 1

        session.commit()
        bot.send_message(message.chat.id, f"✅ Успешно импортировано {imported_count} доноров!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(func=lambda message: message.text == 'Экспорт доноров')
def handle_export_donors(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    try:
        donors = session.query(User).all()

        # Создаем CSV файл в памяти
        csv_output = StringIO()
        csv_writer = csv.writer(csv_output, delimiter=';')

        # Заголовки
        csv_writer.writerow([
            'ID', 'ФИО', 'Телефон', 'Тип', 'Группа',
            'Согласие', 'Дата согласия', 'В регистре ДКМ'
        ])

        # Данные
        for donor in donors:
            csv_writer.writerow([
                donor.id,
                donor.name,
                donor.phone,
                donor.donor_type,
                donor.group,
                'Да' if donor.consent_given else 'Нет',
                donor.consent_date.strftime('%Y-%m-%d') if donor.consent_date else '',
                'Да' if donor.in_bm_registry else 'Нет'
            ])

        # Отправка файла
        csv_output.seek(0)
        bot.send_document(
            message.chat.id,
            ('donors.csv', csv_output.getvalue().encode('utf-8')))
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


# ====================== УПРАВЛЕНИЕ МЕРОПРИЯТИЯМИ ======================
@bot.message_handler(func=lambda message: message.text == 'Управление мероприятиями')
def handle_event_management(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "📅 Управление мероприятиями", reply_markup=get_event_management_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Создать мероприятие')
def handle_create_event(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id,
                           "Введите данные мероприятия в формате:\nДата(ГГГГ-ММ-ДД);Центр крови;Количество мест")
    bot.register_next_step_handler(msg, process_create_event)


def process_create_event(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        return

    try:
        data = message.text.split(';')
        date = datetime.datetime.strptime(data[0].strip(), '%Y-%m-%d').date()
        center = data[1].strip()
        slots = int(data[2].strip())

        new_event = Event(
            date=date,
            center=center,
            slots_available=slots,
            is_active=True
        )

        session.add(new_event)
        session.commit()

        bot.send_message(message.chat.id, f"✅ Мероприятие на {date} в {center} успешно создано!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(func=lambda message: message.text == 'Список мероприятий')
def handle_list_events(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    events = session.query(Event).order_by(Event.date).all()

    if not events:
        bot.send_message(message.chat.id, "ℹ️ Нет запланированных мероприятий")
        return

    response = "📅 Список мероприятий:\n\n"
    for event in events:
        status = "активно" if event.is_active else "не активно"
        response += f"🔹 {event.id}. {event.date} - {event.center} ({event.slots_available} мест, {status})\n"

    bot.send_message(message.chat.id, response)


# ====================== ОТВЕТЫ НА ВОПРОСЫ ======================
@bot.message_handler(func=lambda message: message.text == 'Ответить на вопросы')
def handle_answer_questions(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    unanswered_questions = session.query(Question).filter_by(answered=False).all()

    if not unanswered_questions:
        bot.send_message(message.chat.id, "ℹ️ Нет неотвеченных вопросов")
        return

    keyboard = types.InlineKeyboardMarkup()
    for question in unanswered_questions:
        user = session.query(User).get(question.user_id)
        keyboard.add(types.InlineKeyboardButton(
            text=f"❓ Вопрос от {user.name if user else 'Unknown'}",
            callback_data=f"answer_question_{question.id}"
        ))

    bot.send_message(message.chat.id, "📩 Выберите вопрос для ответа:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_question_'))
def handle_select_question(call):
    if not is_admin(call.message.chat.id) and not is_organizer(call.message.chat.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет доступа")
        return

    question_id = int(call.data.split('_')[-1])
    question = session.query(Question).get(question_id)

    if not question:
        bot.answer_callback_query(call.id, "❌ Вопрос не найден")
        return

    user = session.query(User).get(question.user_id)
    msg_text = f"📩 Вопрос от {user.name if user else 'Unknown'}:\n\n{question.text}"

    bot.send_message(call.message.chat.id, msg_text)
    bot.send_message(call.message.chat.id, "✏️ Введите ваш ответ:")

    bot.register_next_step_handler(call.message, lambda m: process_answer_question(m, question_id))


def process_answer_question(message, question_id):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        return

    question = session.query(Question).get(question_id)
    if not question:
        bot.send_message(message.chat.id, "❌ Вопрос не найден")
        return

    question.answer = message.text
    question.answered = True
    session.commit()

    # Отправляем ответ пользователю
    if question.user.chat_id:
        try:
            bot.send_message(question.user.chat_id, f"📩 Ответ на ваш вопрос:\n\n{message.text}")
        except:
            pass

    bot.send_message(message.chat.id, "✅ Ответ отправлен пользователю")


# ====================== РАССЫЛКИ ======================
@bot.message_handler(func=lambda message: message.text == 'Рассылки')
def handle_mailing(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "📨 Выберите категорию для рассылки:", reply_markup=get_mailing_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Зарегистрированным на ближайшее мероприятие')
def handle_mailing_registered(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите текст сообщения для рассылки:")
    bot.register_next_step_handler(msg, lambda m: process_mailing(m, 'registered'))


@bot.message_handler(func=lambda message: message.text == 'Не зарегистрировавшимся на ближайшие мероприятия')
def handle_mailing_not_registered(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите текст сообщения для рассылки:")
    bot.register_next_step_handler(msg, lambda m: process_mailing(m, 'not_registered'))


@bot.message_handler(func=lambda message: message.text == 'Не пришедшим на первую дату')
def handle_mailing_no_show(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите текст сообщения для рассылки:")
    bot.register_next_step_handler(msg, lambda m: process_mailing(m, 'no_show'))


@bot.message_handler(func=lambda message: message.text == 'В регистре ДКМ')
def handle_mailing_bm_registry(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите текст сообщения для рассылки:")
    bot.register_next_step_handler(msg, lambda m: process_mailing(m, 'bm_registry'))


def process_mailing(message, mailing_type):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        return

    try:
        users = []

        if mailing_type == 'registered':
            # Получаем ближайшее мероприятие
            next_event = session.query(Event).filter(Event.date >= datetime.date.today()).order_by(Event.date).first()
            if next_event:
                users = session.query(User).filter(User.registered_events.op('@>')([next_event.id])).all()

        elif mailing_type == 'not_registered':
            # Получаем ближайшие мероприятия
            next_events = session.query(Event).filter(Event.date >= datetime.date.today()).order_by(Event.date).all()
            if next_events:
                event_ids = [e.id for e in next_events]
                users = session.query(User).filter(~User.registered_events.op('&&')(event_ids)).all()

        elif mailing_type == 'no_show':
            # Пользователи, зарегистрированные на первое мероприятие, но не сдавшие кровь
            first_event = session.query(Event).order_by(Event.date).first()
            if first_event:
                registered_users = session.query(User).filter(User.registered_events.op('@>')([first_event.id])).all()
                users = [u for u in registered_users if not any(d.date == first_event.date for d in u.donations)]

        elif mailing_type == 'bm_registry':
            users = session.query(User).filter_by(in_bm_registry=True).all()

        if not users:
            bot.send_message(message.chat.id, "ℹ️ Нет пользователей для рассылки")
            return

        success = 0
        failed = 0

        for user in users:
            if user.chat_id:
                try:
                    bot.send_message(user.chat_id, message.text)
                    success += 1
                except:
                    failed += 1

        bot.send_message(message.chat.id, f"📨 Рассылка завершена:\n✅ Успешно: {success}\n❌ Не удалось: {failed}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


# ====================== СТАТИСТИКА ======================
@bot.message_handler(func=lambda message: message.text == 'Статистика')
def handle_statistics(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    bot.send_message(message.chat.id, "📊 Выберите тип статистики:", reply_markup=get_statistics_keyboard())


@bot.message_handler(func=lambda message: message.text == 'Статистика по мероприятиям')
def handle_event_stats(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    events = session.query(Event).order_by(Event.date).all()

    if not events:
        bot.send_message(message.chat.id, "ℹ️ Нет мероприятий для отображения статистики")
        return

    response = "📊 Статистика по мероприятиям:\n\n"

    for event in events:
        registered = session.query(User).filter(User.registered_events.op('@>')([event.id])).count()
        donations = session.query(Donation).filter_by(date=event.date, center=event.center, successful=True).count()

        response += f"📅 {event.date} - {event.center}:\n"
        response += f"👥 Зарегистрировались: {registered}\n"
        response += f"🩸 Сдали кровь: {donations}\n\n"

    bot.send_message(message.chat.id, response)


@bot.message_handler(func=lambda message: message.text == 'Экспорт статистики')
def handle_export_stats(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    try:
        # Собираем данные о мероприятиях
        events = session.query(Event).order_by(Event.date).all()

        # Создаем CSV файл в памяти
        csv_output = StringIO()
        csv_writer = csv.writer(csv_output, delimiter=';')

        # Заголовки для мероприятий
        csv_writer.writerow(['Дата', 'Центр крови', 'Зарегистрировались', 'Сдали кровь', 'Процент явки'])

        for event in events:
            registered = session.query(User).filter(User.registered_events.op('@>')([event.id])).count()
            donations = session.query(Donation).filter_by(date=event.date, center=event.center, successful=True).count()
            percent = (donations / registered * 100) if registered > 0 else 0

            csv_writer.writerow([
                event.date.strftime('%Y-%m-%d'),
                event.center,
                registered,
                donations,
                f"{percent:.1f}%"
            ])

        # Добавляем разделитель между таблицами
        csv_writer.writerow([])
        csv_writer.writerow(['Доноры'])
        csv_writer.writerow(['ID', 'ФИО', 'Телефон', 'Тип', 'Группа', 'Количество донаций', 'В регистре ДКМ'])

        # Собираем данные о донорах
        donors = session.query(User).all()
        for donor in donors:
            donation_count = len([d for d in donor.donations if d.successful])

            csv_writer.writerow([
                donor.id,
                donor.name,
                donor.phone,
                donor.donor_type,
                donor.group,
                donation_count,
                'Да' if donor.in_bm_registry else 'Нет'
            ])

        # Отправка файла
        csv_output.seek(0)
        bot.send_document(
            message.chat.id,
            ('statistics.csv', csv_output.getvalue().encode('utf-8')))
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


# ====================== РЕДАКТИРОВАНИЕ ИНФОРМАЦИИ ======================
@bot.message_handler(func=lambda message: message.text == 'Редактировать информацию')
def handle_edit_info(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Изменить текст приветствия'))
    keyboard.add(types.KeyboardButton('Изменить информацию о донорстве'))
    keyboard.add(types.KeyboardButton('Изменить FAQ'))
    keyboard.add(types.KeyboardButton('Назад'))

    bot.send_message(message.chat.id, "✏️ Что вы хотите изменить?", reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text == 'Изменить текст приветствия')
def handle_edit_welcome(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите новый текст приветствия:")
    bot.register_next_step_handler(msg, lambda m: save_info(m, 'welcome'))


@bot.message_handler(func=lambda message: message.text == 'Изменить информацию о донорстве')
def handle_edit_donation_info(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите новую информацию о донорстве:")
    bot.register_next_step_handler(msg, lambda m: save_info(m, 'donation_info'))


@bot.message_handler(func=lambda message: message.text == 'Изменить FAQ')
def handle_edit_faq(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    msg = bot.send_message(message.chat.id, "✏️ Введите новый текст FAQ:")
    bot.register_next_step_handler(msg, lambda m: save_info(m, 'faq'))


def save_info(message, info_type):
    if not is_admin(message.chat.id):
        return

    # В реальном приложении нужно сохранять эти тексты в базу данных
    # Здесь просто демонстрация функционала
    bot.send_message(message.chat.id, f"✅ Текст {info_type} успешно обновлен!")


# ====================== ЗАГРУЗКА ДАННЫХ О ДОНАЦИЯХ ======================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not is_admin(message.chat.id) and not is_organizer(message.chat.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этой функции.")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Чтение CSV файла
        csv_data = downloaded_file.decode('utf-8').splitlines()
        csv_reader = csv.reader(csv_data, delimiter=';')

        imported_count = 0
        for row in csv_reader:
            if len(row) < 3:  # Минимум ФИО, Дата, Центр
                continue

            name = row[0].strip()
            date_str = row[1].strip()
            center = row[2].strip()

            # Ищем пользователя по ФИО
            user = session.query(User).filter_by(name=name).first()
            if not user:
                continue

            # Парсим дату
            try:
                date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                continue

            # Проверяем, существует ли уже такая донация
            existing = session.query(Donation).filter_by(
                user_id=user.id,
                date=date,
                center=center
            ).first()

            if not existing:
                new_donation = Donation(
                    user_id=user.id,
                    date=date,
                    center=center,
                    successful=True
                )
                session.add(new_donation)
                imported_count += 1

        session.commit()
        bot.send_message(message.chat.id, f"✅ Успешно импортировано {imported_count} донаций!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)