import os
import re
import datetime
from typing import Optional
from dotenv import load_dotenv
import telebot
from telebot import types
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from collections import defaultdict
from threading import Thread
from geopy.distance import geodesic
import logging
import colorama
from organizer_bot import *
import random
from MainWebAPP import DonorType

# Инициализация colorama для цветного вывода в консоль
colorama.init()

# ====================== КОНФИГУРАЦИЯ ======================
# Загрузка переменных окружения
load_dotenv()

# Настройки бота
BOT_TOKEN = "8070241125:AAHqv4jo2AIRdjdkxXnm-c3uoghCG8S9vBI"
DATABASE_URL = 'sqlite:///C:/Users/Иван/PycharmProjects/abobych/donor.db'

# Списки ID пользователей
ADMIN_IDS = [-4983144611]  # ID чата организаторов
ORGANIZER_APPROVAL_CHAT_ID = -4938535692

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Настройка базы данных
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# Кэш для хранения последних сообщений
message_cache = defaultdict(dict)


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

class OrganizerRequest(Base):
    """Модель заявки на организатора"""
    __tablename__ = 'organizer_requests'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    status = Column(String(20), default='pending')  # pending, approved, rejected
    rejection_reason = Column(String(500), nullable=True)
    request_date = Column(Date, default=datetime.datetime.now)

    user = relationship("User")

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



# Создание таблиц
Base.metadata.create_all(engine)

# ====================== КОНСТАНТЫ ======================
DONOR_TYPES = ['student', 'staff', 'external']

BLOOD_CENTERS = [
    {
        'name': 'ЦК им. О.К. Гаврилова (Поликарпова)',
        'address': '125284, г. Москва, ул. Поликарпова, д. 14, корп. 2',
        'coords': (55.778654, 37.549824)
    },
    {
        'name': 'ЦК им. О.К. Гаврилова (Бакинская)',
        'address': '115516, г. Москва, ул. Бакинская, д. 31',
        'coords': (55.617139, 37.660258)
    },
    {
        'name': 'ЦК им. О.К. Гаврилова (Шаболовка)',
        'address': '115162, г. Москва, ул. Шаболовка, д. 57',
        'coords': (55.715839, 37.609223)
    },
    {
        'name': 'Центр крови ФМБА России',
        'address': 'Щукинская улица, 6к2, Москва, 123182',
        'coords': (55.810001, 37.479867)
    }
]


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def validate_name(name: str) -> bool:
    """Проверка формата русского имени"""
    return bool(re.fullmatch(r'[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+( [А-ЯЁ][а-яё]+)?', name))


def validate_group(group: str) -> bool:
    """Проверка формата учебной группы"""
    return bool(re.fullmatch(r'[А-Яа-яA-Za-z0-9-]+', group))


def format_user_info(user: User) -> str:
    """Форматирование информации о пользователе"""
    info = f"👤 <b>Ваши данные:</b>\n"
    info += f"▪ ФИО: {user.name}\n"
    info += f"▪ Тип: {'студент' if user.donor_type == 'student' else 'сотрудник' if user.donor_type == 'staff' else 'внешний донор'}\n"

    if user.donor_type == 'student' and user.group:
        info += f"▪ Группа: {user.group}\n"

    donation_count = session.query(Donation).filter_by(user_id=user.id).count()
    info += f"▪ Количество донаций: {donation_count}\n"

    last_donation = session.query(Donation).filter_by(user_id=user.id).order_by(Donation.date.desc()).first()
    if last_donation:
        info += f"▪ Последняя донация: {last_donation.date.strftime('%d.%m.%Y')} ({last_donation.center})\n"

    info += f"▪ В регистре ДКМ: {'да' if user.in_bm_registry else 'нет'}\n"
    return info

# donor_type = DonorType.STUDENT if message.text == 'Студент' else DonorType.STAFF if message.text == 'Сотрудник' else DonorType.EXTERNAL

def get_user_by_chat_id(chat_id: int) -> Optional[User]:
    """Получение пользователя по chat_id"""
    return session.query(User).filter_by(chat_id=chat_id).first()


def get_user_by_phone(phone: str) -> Optional[User]:
    """Получение пользователя по номеру телефона"""
    return session.query(User).filter_by(phone=phone).first()


def export_stats_to_csv():
    """Экспорт статистики в CSV"""
    from csv import writer
    import io

    users = session.query(User).all()
    donations = session.query(Donation).all()
    events = session.query(Event).all()

    output = io.StringIO()
    csv_writer = writer(output)

    # Заголовки для пользователей
    csv_writer.writerow([
        'User ID', 'Name', 'Donor Type', 'Group',
        'Donation Count', 'In BM Registry', 'Last Donation Date'
    ])

    for user in users:
        last_donation = session.query(Donation) \
            .filter_by(user_id=user.id) \
            .order_by(Donation.date.desc()) \
            .first()

        last_donation_date = last_donation.date.strftime('%Y-%m-%d') if last_donation else ''

        csv_writer.writerow([
            user.id,
            user.name,
            user.donor_type,
            user.group or '',
            session.query(Donation).filter_by(user_id=user.id).count(),
            'Yes' if user.in_bm_registry else 'No',
            last_donation_date
        ])

    # Разделитель и заголовки для мероприятий
    csv_writer.writerow([])
    csv_writer.writerow(['Event ID', 'Date', 'Center', 'Slots Available', 'Is Active'])

    for event in events:
        csv_writer.writerow([
            event.id,
            event.date.strftime('%Y-%m-%d'),
            event.center,
            event.slots_available,
            'Yes' if event.is_active else 'No'
        ])

    output.seek(0)
    return output.getvalue()


def get_nearest_center(user_coords):
    """Возвращает ближайший центр донорства и расстояние до него"""
    nearest = None
    min_distance = float('inf')

    for center in BLOOD_CENTERS:
        distance = geodesic(user_coords, center['coords']).km
        if distance < min_distance:
            min_distance = distance
            nearest = center

    return nearest, min_distance


def get_osm_route_url(start_coords, end_coords):
    """Генерирует URL для маршрута в OpenStreetMap"""
    return (f"https://www.openstreetmap.org/directions?"
            f"engine=graphhopper_foot&route={start_coords[0]}%2C{start_coords[1]}%3B"
            f"{end_coords[0]}%2C{end_coords[1]}")


def get_static_map_url(center_coords, zoom=14):
    """Генерирует URL для статичной карты"""
    return (f"https://static-maps.yandex.ru/1.x/?ll={center_coords[1]},{center_coords[0]}"
            f"&z={zoom}&l=map&pt={center_coords[1]},{center_coords[0]},pm2dgl")


# ====================== КЛАВИАТУРЫ ======================
def main_menu_keyboard(is_admin: bool = False, is_organizer: bool = False):
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('📅 Ближайшие Дни Донора')
    btn2 = types.KeyboardButton('🩸 Информация о донорстве крови')
    btn3 = types.KeyboardButton('🦴 Информация о донорстве костного мозга')
    btn4 = types.KeyboardButton('ℹ О донациях в МИФИ')
    btn5 = types.KeyboardButton('📝 Мои данные')
    btn6 = types.KeyboardButton('❓ Задать вопрос организаторам')
    btn7 = types.KeyboardButton('📍 Ближайший центр донорства')
    btn8 = types.KeyboardButton('📋 Мои заявки')  # Новая кнопка

    keyboard.add(btn5, btn6)
    keyboard.add(btn1, btn7)
    keyboard.add(btn2, btn3)
    keyboard.add(btn4, btn8)  # Добавляем новую кнопку

    if is_admin:
        keyboard.add(types.KeyboardButton('⚙ Админ-панель'))
    elif is_organizer:
        keyboard.add(types.KeyboardButton('⚙ Администрирование'))

    return keyboard


def admin_keyboard():
    """Клавиатура администратора"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        '📊 Статистика',
        '✏ Редактировать данные доноров',
        '📩 Ответить на вопросы',
        '📢 Сделать рассылку',
        '➕ Создать мероприятие',
        '📝 Изменить информационные разделы',
        '📥 Загрузить данные донаций',
        '📤 Выгрузить статистику',
        '🔙 Главное меню'
    ]
    for btn_text in buttons:
        keyboard.add(types.KeyboardButton(btn_text))
    return keyboard


# ====================== ОСНОВНЫЕ ФУНКЦИИ ======================
def ask_for_consent(chat_id: int):
    """Запрос согласия на обработку данных"""
    consent_text = (
        "Перед началом работы с ботом необходимо дать согласие на обработку персональных данных:\n\n"
        "1. Я согласен(а) на обработку моих персональных данных для целей организации донорских акций.\n"
        "2. Я согласен(а) получать информационные сообщения, связанные с донорскими акциями.\n\n"
        "Вы согласны?"
    )

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn1 = types.KeyboardButton('Да, согласен(а)')
    btn2 = types.KeyboardButton('Нет, не согласен(а)')
    btn3 = types.KeyboardButton('📄 Пользовательское соглашение')
    keyboard.add(btn1, btn2, btn3)

    bot.send_message(chat_id, consent_text, reply_markup=keyboard)


def show_upcoming_events(chat_id: int):
    """Показать предстоящие мероприятия"""
    events = session.query(Event).filter_by(is_active=True).order_by(Event.date).all()

    if not events:
        bot.send_message(chat_id, "На данный момент нет запланированных Дней Донора.")
        return

    text = "📅 <b>Ближайшие Дни Донора:</b>\n\n"
    for event in events:
        text += f"▪ <b>{event.date.strftime('%d.%m.%Y')}</b> - {event.center}\n"
        text += f"   Доступно мест: {event.slots_available}\n\n"

    text += "Хотите зарегистрироваться на одно из мероприятий?"

    keyboard = types.InlineKeyboardMarkup()
    for event in events:
        keyboard.add(types.InlineKeyboardButton(
            text=f"{event.date.strftime('%d.%m.%Y')} - {event.center}",
            callback_data=f"register_{event.id}"
        ))

    bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode='HTML')


def show_blood_info(chat_id: int):
    text = (
        "🩸 <b>Информация о донорстве крови</b>\n\n"
        "<b>Требования к донорам:</b>\n"
        "▪ Возраст: Не менее 18 лет\n"
        "▪ Вес: Не менее 50 кг\n"
        "▪ Здоровье:\n"
        "   - Отсутствие хронических заболеваний в острой фазе\n"
        "   - Не болели ангиной, ОРВИ, гриппом менее чем за месяц до сдачи крови\n"
        "   - Температура тела ≤ 37°C\n"
        "   - Давление: систолическое 90-160 мм рт.ст., диастолическое 60-100 мм рт.ст.\n"
        "   - Гемоглобин: женщины ≥ 120 г/л, мужчины ≥ 130 г/л\n"
        "▪ Периодичность:\n"
        "   - Цельная кровь: не чаще 4-5 раз в год для мужчин, 3-4 раза для женщин\n\n"
        "<b>Подготовка к донации (за 2-3 дня):</b>\n"
        "▪ Питание:\n"
        "   - Исключить жирную, острую, копченую пищу\n"
        "   - Отказаться от фастфуда, молочных продуктов и продуктов с яйцами\n"
        "▪ Образ жизни:\n"
        "   - Отказ от алкоголя за 48 часов\n"
        "   - Избегать интенсивных физических нагрузок\n"
        "   - Отменить прием лекарственных препаратов (в т.ч. анальгетиков) за 72 часа\n"
        "▪ Накануне:\n"
        "   - Легкий ужин до 20:00\n"
        "   - Сон не менее 8 часов\n"
        "   - Обязательный завтрак (каша на воде, сладкий чай, сушки, хлеб с вареньем)\n"
        "   - Нельзя курить в течение часа до сдачи крови\n"
        "<b>Рацион донора за 2-3 дня до донации</b>\n"
        "▪ Водный режим: 1.5–2 литра воды в день (чистая вода, морсы, компоты)\n"
        "▪ Основа рациона:\n"
        "   - Крупы на воде\n"
        "   - Отварное нежирное мясо (говядина, индейка, курица)\n"
        "   - Белая нежирная рыба (треска, хек)\n"
        "   - Овощи и фрукты\n"
        "▪ Запрещено:\n"
        "   - Жирное мясо (свинина, баранина)\n"
        "   - Молочные продукты (сыр, сливочное масло, йогурты)\n"
        "   - Яйца и орехи\n"
        "   - Фастфуд, копчености, майонез\n"
        "   - Некоторые фрукты и овощи: цитрусовые, бананы, киви, клубника/малина, авокадо,"
        " виноград, все экзотические фрукты, свекла, шпинат.\n"
        "<b>Абсолютные противопоказания</b>\n"
        "▪ Инфекционные:\n"
        "   - ВИЧ/СПИД\n"
        "   - Сифилис\n"
        "   - Вирусные гепатиты (B, C)\n"
        "   - Туберкулез\n"
        "▪ Паразитарные:\n"
        "   - Токсоплазмоз\n"
        "   - Лейшманиоз\n"
        "   - Онкологические заболевания\n"
        "   - Болезни крови\n"
        "▪ Сердечно-сосудистые:\n"
        "   - Гипертония II-III ст\n"
        "   - Ишемическая болезнь\n"
        "   - Органические поражения ЦНС\n"
        "   - Бронхиальная астма\n"
        "<b>Временные противопоказания</b>\n"
        "▪ После заболеваний:\n"
        "   - ОРВИ, грипп - 1 месяц\n"
        "   - Ангина - 1 месяц\n"
        "   - Менструация + 5 дней после\n"
        "▪ После процедур::\n"
        "   - Татуировки/пирсинг - 4-12 месяцев\n"
        "   - Эндоскопия - 4-6 месяцев\n"
        "   - Прививки (живые вакцины)\n"
        "▪ Лекарства:\n"
        "   - Антибиотики - 2 недели после курса\n"
        "   - Анальгетики - 3 дня после приема\n"
    )

    bot.send_message(chat_id, text, parse_mode='HTML')



def show_bone_marrow_info(chat_id: int):
    """Показать информацию о донорстве костного мозга"""
    text = (
        "🦴 <b>Информация о донорстве костного мозга</b>\n\n"
        "<b>Важность донорства:</b>\n"
        "Ежегодно в России более 5 000 человек нуждаются в трансплантации костного мозга.\n\n"
        "<b>Процедура вступления в регистр:</b>\n"
        "1. Первичное согласие (заполнение анкеты)\n"
        "2. Забор биоматериала (анализ крови или мазок с щеки)\n"
        "3. Типирование (генетический анализ)\n"
        "4. Ожидание (может занять 2-10 лет)\n\n"
        "<b>Процедура донации:</b>\n"
        "▪ Периферический забор стволовых клеток (80% случаев)\n"
        "▪ Пункция костного мозга (20% случаев)"
    )
    bot.send_message(chat_id, text, parse_mode='HTML')


def show_mephi_donation_info(chat_id: int):
    """Показать информацию о донациях в МИФИ"""
    text = (
        "ℹ <b>О донациях в МИФИ</b>\n\n"
        "<b>Процедура сдачи крови в МИФИ:</b>\n"
        "1. Прибытие в МИФИ (Студенческий офис)\n"
        "2. Регистрация:\n"
        "   - Заполнение документов\n"
        "   - Получение направления\n"
        "   - Получение бахил\n"
        "3. Медобследование:\n"
        "   - Измерение давления и пульса\n"
        "   - Экспресс-анализ крови\n"
        "4. Процедура забора крови (10-15 минут)\n"
        "5. Отдых и питание после донации\n"
        "6. Получение справок"
    )
    bot.send_message(chat_id, text, parse_mode='HTML')


def show_user_data(chat_id: int):
    """Показать данные пользователя"""
    user = get_user_by_chat_id(chat_id)
    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    text = format_user_info(user)

    # Добавляем историю донаций
    donations = session.query(Donation).filter_by(user_id=user.id).order_by(Donation.date.desc()).all()
    if donations:
        text += "\n\n<b>История донаций:</b>\n"
        for donation in donations:
            status = "✅" if donation.successful else "❌"
            text += f"▪ {status} {donation.date.strftime('%d.%m.%Y')} - {donation.center}\n"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("Изменить данные", callback_data="edit_user_data"),
        types.InlineKeyboardButton("🗑 Удалить аккаунт", callback_data="delete_account_confirm")
    )

    # Удаляем предыдущее сообщение с кнопкой (если есть)
    try:
        if f"last_msg_{chat_id}" in message_cache:
            bot.delete_message(chat_id, message_id=message_cache[f"last_msg_{chat_id}"])
    except:
        pass

    # Отправляем новое сообщение и сохраняем его ID
    msg = bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode='HTML')
    message_cache[f"last_msg_{chat_id}"] = msg.message_id


@bot.message_handler(func=lambda message: message.text == '📋 Мои заявки')
def handle_my_applications(message):
    """Обработчик кнопки 'Мои заявки'"""
    chat_id = message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    show_user_applications(chat_id, user)


def show_user_applications(chat_id: int, user: User, page: int = 0, history: bool = False):
    """Показать заявки пользователя"""
    today = datetime.date.today()

    # Получаем список ID мероприятий, на которые зарегистрирован пользователь
    registered_events = user.registered_events or []

    if not registered_events:
        if history:
            text = "У вас пока нет истории мероприятий."
        else:
            text = "У вас нет активных заявок на мероприятия."

        keyboard = types.InlineKeyboardMarkup()
        if history:
            keyboard.add(types.InlineKeyboardButton("🔙 Назад к активным заявкам", callback_data="applications_back"))
        else:
            keyboard.add(types.InlineKeyboardButton("📜 История мероприятий", callback_data="applications_history"))

        bot.send_message(chat_id, text, reply_markup=keyboard)
        return

    if history:
        # Все мероприятия, на которые пользователь зарегистрирован
        events = session.query(Event).filter(
            Event.id.in_(registered_events)
        ).order_by(Event.date.desc()).all()
    else:
        # Только будущие мероприятия
        events = session.query(Event).filter(
            Event.id.in_(registered_events),
            Event.date >= today
        ).order_by(Event.date.asc()).all()

    if not events:
        if history:
            text = "У вас пока нет истории мероприятий."
        else:
            text = "У вас нет активных заявок на мероприятия."

        keyboard = types.InlineKeyboardMarkup()
        if history:
            keyboard.add(types.InlineKeyboardButton("🔙 Назад к активным заявкам", callback_data="applications_back"))
        else:
            keyboard.add(types.InlineKeyboardButton("📜 История мероприятий", callback_data="applications_history"))

        bot.send_message(chat_id, text, reply_markup=keyboard)
        return

    # Разбиваем на страницы по 10 мероприятий
    pages = [events[i:i + 10] for i in range(0, len(events), 10)]
    current_page = pages[page] if page < len(pages) else pages[-1]

    if history:
        text = "📜 <b>История ваших мероприятий</b>\n\n"
    else:
        text = "📋 <b>Ваши активные заявки</b>\n\n"

    for event in current_page:
        status = "✅" if event.date >= today else "⌛"
        text += f"{status} <b>{event.date.strftime('%d.%m.%Y')}</b> - {event.center}\n"

    # Создаем клавиатуру
    keyboard = types.InlineKeyboardMarkup()

    if len(pages) > 1:
        row = []
        if page > 0:
            row.append(types.InlineKeyboardButton("⬅️", callback_data=f"applications_page_{page - 1}_{int(history)}"))
        if page < len(pages) - 1:
            row.append(types.InlineKeyboardButton("➡️", callback_data=f"applications_page_{page + 1}_{int(history)}"))
        keyboard.row(*row)

    if history:
        keyboard.add(types.InlineKeyboardButton("🔙 Назад к активным заявкам", callback_data="applications_back"))
    else:
        keyboard.add(types.InlineKeyboardButton("📜 История мероприятий", callback_data="applications_history"))

    # Удаляем предыдущее сообщение (если есть)
    try:
        if f"last_applications_msg_{chat_id}" in message_cache:
            bot.delete_message(chat_id, message_cache[f"last_applications_msg_{chat_id}"])
    except:
        pass

    # Отправляем новое сообщение
    msg = bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=keyboard)
    message_cache[f"last_applications_msg_{chat_id}"] = msg.message_id


@bot.callback_query_handler(func=lambda call: call.data.startswith('applications_page_'))
def handle_applications_page(call):
    """Обработчик переключения страниц"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    parts = call.data.split('_')
    page = int(parts[2])
    history = bool(int(parts[3]))

    show_user_applications(chat_id, user, page, history)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == 'applications_history')
def handle_applications_history(call):
    """Обработчик кнопки 'История мероприятий'"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    show_user_applications(chat_id, user, history=True)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == 'applications_back')
def handle_applications_back(call):
    """Обработчик кнопки 'Назад к активным заявкам'"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    show_user_applications(chat_id, user)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'delete_account_confirm')
def handle_delete_account_confirm(call):
    """Обработчик подтверждения удаления аккаунта (первый шаг)"""
    chat_id = call.message.chat.id

    # Создаем список кнопок и перемешиваем их
    buttons = [
        types.InlineKeyboardButton("Да, я хочу удалить аккаунт", callback_data="delete_account_step2"),
        types.InlineKeyboardButton("Нет, я передумал", callback_data="back_to_profile"),
        types.InlineKeyboardButton("Нет, пусть будет", callback_data="back_to_profile"),
    ]
    random.shuffle(buttons)

    keyboard = types.InlineKeyboardMarkup()
    for btn in buttons:
        keyboard.add(btn)

    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile"))

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="⚠️ <b>Вы уверены, что хотите удалить аккаунт?</b>\n\n"
                 "Все ваши данные будут безвозвратно удалены из системы.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")
        bot.send_message(
            chat_id,
            "⚠️ <b>Вы уверены, что хотите удалить аккаунт?</b>\n\n"
            "Все ваши данные будут безвозвратно удалены из системы.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )


@bot.callback_query_handler(func=lambda call: call.data == 'delete_account_step2')
def handle_delete_account_step2(call):
    """Обработчик подтверждения удаления аккаунта (второй шаг)"""
    chat_id = call.message.chat.id

    # Создаем список кнопок и перемешиваем их (кроме кнопки Назад)
    buttons = [
        types.InlineKeyboardButton("Да, точно хочу удалить", callback_data="delete_account_final"),
        types.InlineKeyboardButton("Нет, передумал", callback_data="back_to_profile"),
        types.InlineKeyboardButton("Нет, оставлю", callback_data="back_to_profile")
    ]
    random.shuffle(buttons)

    # Создаем клавиатуру и добавляем кнопки
    keyboard = types.InlineKeyboardMarkup()
    for btn in buttons:
        keyboard.add(btn)

    # Добавляем статичную кнопку "Назад" в конце
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile"))
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="❌ <b>Последнее предупреждение!</b>\n\n"
                 "Вы действительно хотите удалить свой аккаунт и все связанные данные? "
                 "Это действие нельзя отменить!",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")
        bot.send_message(
            chat_id,
            "❌ <b>Последнее предупреждение!</b>\n\n"
            "Вы действительно хотите удалить свой аккаунт и все связанные данные? "
            "Это действие нельзя отменить!",
            reply_markup=keyboard,
            parse_mode='HTML'
        )


@bot.callback_query_handler(func=lambda call: call.data == 'delete_account_final')
def handle_delete_account_final(call):
    """Финальное удаление аккаунта"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    try:
        # Удаляем все связанные данные пользователя
        # 1. Удаляем донации
        session.query(Donation).filter_by(user_id=user.id).delete()

        # 2. Удаляем вопросы
        session.query(Question).filter_by(user_id=user.id).delete()

        # 3. Удаляем заявки на организатора
        session.query(OrganizerRequest).filter_by(user_id=user.id).delete()

        # 4. Удаляем из таблицы организаторов (если есть)
        from organizer_bot import Organizer
        session.query(Organizer).filter_by(user_id=user.id).delete()

        # 5. Удаляем самого пользователя
        session.delete(user)
        session.commit()

        # Отправляем подтверждение
        bot.send_message(
            chat_id,
            "Ваш аккаунт и все связанные данные были успешно удалены.\n\n"
            "Для повторной регистрации используйте команду /start"
        )

        # Вызываем /start для нового пользователя
        start(call.message)

    except Exception as e:
        print(f"Ошибка при удалении аккаунта: {e}")
        bot.send_message(chat_id, "Произошла ошибка при удалении аккаунта. Пожалуйста, попробуйте позже.")
        show_user_data(chat_id)


def show_admin_panel(chat_id: int):
    """Показать панель администратора"""
    if chat_id not in ADMIN_IDS:
        bot.send_message(chat_id, "У вас нет прав доступа.")
        return

    bot.send_message(chat_id, "⚙ <b>Админ-панель</b>",
                     reply_markup=admin_keyboard(), parse_mode='HTML')


def show_admin_stats(chat_id: int):
    """Показать статистику администратору"""
    if chat_id not in ADMIN_IDS:
        bot.send_message(chat_id, "У вас нет прав доступа.")
        return

    total_donors = session.query(User).count()
    active_donors = session.query(User).join(Donation).distinct(User.id).count()
    upcoming_events = session.query(Event).filter_by(is_active=True).count()
    unanswered_questions = session.query(Question).filter_by(answered=False).count()

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"▪ Всего доноров: {total_donors}\n"
        f"▪ Активных доноров: {active_donors}\n"
        f"▪ Предстоящих мероприятий: {upcoming_events}\n"
        f"▪ Неотвеченных вопросов: {unanswered_questions}"
    )

    bot.send_message(chat_id, text, parse_mode='HTML')


def register_for_event(chat_id: int, event_id: int):
    """Регистрация пользователя на мероприятие"""
    user = get_user_by_chat_id(chat_id)
    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    event = session.query(Event).get(event_id)
    if not event:
        bot.send_message(chat_id, "Мероприятие не найдено.")
        return

    # Проверяем, не зарегистрирован ли уже пользователь на другое мероприятие в эту дату
    existing_registrations = session.query(Event).filter(
        Event.id.in_(user.registered_events or []),
        Event.date == event.date
    ).all()

    if existing_registrations:
        conflict_event = existing_registrations[0]
        bot.send_message(
            chat_id,
            f"Вы уже зарегистрированы на мероприятие {conflict_event.date.strftime('%d.%m.%Y')} "
            f"({conflict_event.center}). Невозможно зарегистрироваться на два мероприятия в один день."
        )
        return

    # Проверяем, не зарегистрирован ли уже пользователь на это мероприятие
    if event_id in (user.registered_events or []):
        bot.send_message(chat_id, "Вы уже зарегистрированы на это мероприятие.")
        return

    # Регистрируем пользователя
    if not user.registered_events:
        user.registered_events = []
    print(*user.registered_events, 'old')
    event.slots_available -= 1
    user.registered_events.append(event_id)

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(user, "registered_events")

    print(*user.registered_events, 'new')
    session.commit()

    # Для внешних доноров - дополнительная регистрация
    if user.donor_type == 'external':
        text = (
            f"Вы успешно зарегистрированы на {event.date.strftime('%d.%m.%Y')} ({event.center}).\n\n"
            "Как внешний донор, вам также необходимо пройти регистрацию по ссылке:\n"
            "https://it.mephi.ru/donor-registration"
        )
    else:
        text = f"Вы успешно зарегистрированы на {event.date.strftime('%d.%m.%Y')} ({event.center})."

    bot.send_message(chat_id, text)


def answer_question(admin_chat_id: int, question_id: int):
    """Ответ на вопрос пользователя"""
    question = session.query(Question).get(question_id)
    if not question:
        bot.send_message(admin_chat_id, "Вопрос не найден.")
        return

    bot.send_message(admin_chat_id,
                     f"Ответ на вопрос (ID: {question.id}):\n{question.text}\n\nВведите ваш ответ:",
                     reply_markup=types.ForceReply(selective=True))


def export_stats(chat_id: int):
    """Экспорт статистики в CSV"""
    if chat_id not in ADMIN_IDS:
        bot.send_message(chat_id, "У вас нет прав доступа.")
        return

    try:
        csv_data = export_stats_to_csv()

        # Создаем временный файл
        with open('donor_stats.csv', 'w', encoding='utf-8') as f:
            f.write(csv_data)

        # Отправляем файл
        with open('donor_stats.csv', 'rb') as f:
            bot.send_document(chat_id, f, caption='📊 Статистика доноров')

    except Exception as e:
        bot.send_message(chat_id, f"Ошибка при экспорте статистики: {str(e)}")


# ====================== ОБРАБОТЧИКИ СООБЩЕНИЙ ======================
@bot.message_handler(commands=['start'])
def start(message):
    """Обработчик команды /start"""
    chat_id = message.chat.id
    user = get_user_by_chat_id(chat_id)

    if user:
        greeting = f"Добро пожаловать, {user.name.split()[1]}!\n\n"
        greeting += "Это бот Дня Донора НИЯУ МИФИ. Здесь вы можете зарегистрироваться на донорскую акцию, узнать информацию о донорстве и посмотреть свою историю донаций."

        from organizer_bot import is_organizer
        is_org = is_organizer(chat_id)
        bot.send_message(chat_id, greeting,
                        reply_markup=main_menu_keyboard(is_admin=(chat_id in ADMIN_IDS),
                                                      is_organizer=is_org))
    else:
        greeting = "👋 Добро пожаловать в бот Дня Донора НИЯУ МИФИ!\n\n"
        greeting += "Наша цель - упростить процесс регистрации на донорские акции и предоставить вам всю необходимую информацию о донорстве крови и костного мозга.\n\n"
        greeting += "Для начала работы нам нужно провести авторизацию по номеру телефона."

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(types.KeyboardButton('📱 Отправить номер телефона', request_contact=True))

        bot.send_message(chat_id, greeting, reply_markup=keyboard)


@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    """Обработчик отправки контакта"""
    chat_id = message.chat.id
    phone_number = message.contact.phone_number

    user = get_user_by_phone(phone_number)

    if user:
        # Обновляем chat_id если пользователь сменил устройство
        if user.chat_id != chat_id:
            user.chat_id = chat_id
            session.commit()

        bot.send_message(chat_id,
                         f"Мы нашли ваши данные:\n{format_user_info(user)}\n\nЭто вы?",
                         reply_markup=types.ForceReply(selective=True))
    else:
        # Новый пользователь
        new_user = User(chat_id=chat_id, phone=phone_number)
        session.add(new_user)
        session.commit()

        bot.send_message(chat_id,
                         "Введите ваше ФИО (например, Иванов Иван Иванович):",
                         reply_markup=types.ForceReply(selective=True))


@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите ваше ФИО' in message.reply_to_message.text)
@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите ваше ФИО' in message.reply_to_message.text)
def handle_name(message):
    """Обработчик ввода ФИО"""
    chat_id = message.chat.id
    name = message.text.strip()

    if not validate_name(name):
        bot.send_message(chat_id, "Пожалуйста, введите корректное ФИО (например, Иванов Иван Иванович):",
                         reply_markup=types.ForceReply(selective=True))
        return

    user = get_user_by_chat_id(chat_id)
    if user:
        # Сохраняем временно в кэше
        message_cache[f"temp_name_{chat_id}"] = name

        # Создаем инлайн-кнопки для подтверждения
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("✅ Да, верно", callback_data=f"confirm_name_yes_{chat_id}"),
            types.InlineKeyboardButton("❌ Нет, изменить", callback_data=f"confirm_name_no_{chat_id}")
        )

        bot.send_message(chat_id, f"Вы указали ФИО: <b>{name}</b>\n\nЭто верно?",
                         reply_markup=keyboard, parse_mode='HTML')


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_name_'))
def handle_name_confirmation(call):
    """Обработчик подтверждения ФИО через инлайн-кнопки"""
    chat_id = call.message.chat.id
    action = call.data.split('_')[2]
    user_chat_id = int(call.data.split('_')[3]) if len(call.data.split('_')) > 3 else chat_id

    if action == 'no':
        # Удаляем сообщение с кнопками
        bot.delete_message(chat_id, call.message.message_id)
        # Запрашиваем ФИО снова
        bot.send_message(user_chat_id, "Введите ваше ФИО еще раз:",
                         reply_markup=types.ForceReply(selective=True))
        return

    # Подтверждено - сохраняем и переходим к выбору типа
    user = get_user_by_chat_id(user_chat_id)
    if user:
        user.name = message_cache[f"temp_name_{user_chat_id}"]
        session.commit()
        del message_cache[f"temp_name_{user_chat_id}"]  # Очищаем кэш

        # Удаляем сообщение с кнопками
        bot.delete_message(chat_id, call.message.message_id)

        # Предлагаем выбрать тип донора
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(
            types.KeyboardButton('Студент'),
            types.KeyboardButton('Сотрудник'),
            types.KeyboardButton('Внешний донор')
        )
        bot.send_message(user_chat_id, "Выберите ваш статус:", reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text in ['Студент', 'Сотрудник', 'Внешний донор'])
def handle_donor_type(message):
    """Обработчик выбора типа донора"""
    chat_id = message.chat.id
    donor_type = 'student' if message.text == 'Студент' else 'staff' if message.text == 'Сотрудник' else 'external'

    user = get_user_by_chat_id(chat_id)
    if user:
        user.donor_type = donor_type
        session.commit()

        if donor_type == 'student':
            bot.send_message(chat_id, "Введите номер вашей учебной группы:",
                             reply_markup=types.ForceReply(selective=True))
        elif donor_type == 'staff':
            ask_for_consent(chat_id)
        else:
            # Для внешних доноров отправляем сообщение с дополнительной регистрацией
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.add(types.KeyboardButton('Я прошел регистрацию'))

            bot.send_message(
                chat_id,
                "Пожалуйста, пройдите дополнительную регистрацию на сайте:\n"
                "https://donor.blood.ru/news/den-donora-v-niyau-mifi/\n\n"
                "После прохождения регистрации нажмите кнопку ниже:",
                reply_markup=keyboard
            )


@bot.message_handler(func=lambda message: message.text == 'Я прошел регистрацию')
def handle_external_registration_complete(message):
    """Обработчик завершения регистрации внешнего донора"""
    chat_id = message.chat.id
    user = get_user_by_chat_id(chat_id)

    if user and user.donor_type == 'external':
        ask_for_consent(chat_id)
    else:
        bot.send_message(chat_id, "Ошибка. Пожалуйста, начните регистрацию заново с помощью /start")

@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите номер вашей учебной группы' in message.reply_to_message.text)
def handle_group(message):
    """Обработчик ввода группы"""
    chat_id = message.chat.id
    group = message.text.strip()

    if not validate_group(group):
        bot.send_message(chat_id, "Пожалуйста, введите корректный номер группы:",
                         reply_markup=types.ForceReply(selective=True))
        return

    # Сохраняем временно в кэше
    message_cache[f"temp_group_{chat_id}"] = group

    # Создаем инлайн-кнопки для подтверждения
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Да, верно", callback_data=f"confirm_group_yes_{chat_id}"),
        types.InlineKeyboardButton("❌ Нет, изменить", callback_data=f"confirm_group_no_{chat_id}")
    )

    bot.send_message(chat_id, f"Вы указали группу: <b>{group}</b>\n\nЭто верно?",
                     reply_markup=keyboard, parse_mode='HTML')


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_group_'))
def handle_group_confirmation(call):
    """Обработчик подтверждения группы через инлайн-кнопки"""
    chat_id = call.message.chat.id
    action = call.data.split('_')[2]
    user_chat_id = int(call.data.split('_')[3]) if len(call.data.split('_')) > 3 else chat_id

    if action == 'no':
        # Удаляем сообщение с кнопками
        bot.delete_message(chat_id, call.message.message_id)
        # Запрашиваем группу снова
        bot.send_message(user_chat_id, "Введите номер вашей учебной группы еще раз:",
                         reply_markup=types.ForceReply(selective=True))
        return

    # Подтверждено - сохраняем и переходим к согласию
    user = get_user_by_chat_id(user_chat_id)
    if user:
        user.group = message_cache[f"temp_group_{user_chat_id}"]
        session.commit()
        del message_cache[f"temp_group_{user_chat_id}"]  # Очищаем кэш

        # Удаляем сообщение с кнопками
        bot.delete_message(chat_id, call.message.message_id)

        ask_for_consent(user_chat_id)


@bot.message_handler(func=lambda message: message.text == '📄 Пользовательское соглашение')
def show_agreement(message):
    """Показать пользовательское соглашение"""
    try:
        # Путь к файлу соглашения
        agreement_path = os.path.join('documents', 'soglas.pdf')

        # Проверяем существование файла
        if not os.path.exists(agreement_path):
            raise FileNotFoundError(f"Файл соглашения не найден по пути: {agreement_path}")

        # Отправляем сообщение и файл
        bot.send_message(
            message.chat.id,
            "Ознакомьтесь с Политикой обработки персональных данных:"
        )

        with open(agreement_path, 'rb') as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption='Политика обработки персональных данных'
            )

    except FileNotFoundError as e:
        logging.error(f"Ошибка при отправке соглашения: {e}")
        bot.send_message(
            message.chat.id,
            "Извините, файл соглашения временно недоступен. Пожалуйста, попробуйте позже."
        )
    except Exception as e:
        logging.error(f"Неожиданная ошибка при отправке соглашения: {e}")
        bot.send_message(
            message.chat.id,
            "Произошла ошибка при отправке файла соглашения. Пожалуйста, сообщите об этом администратору."
        )


@bot.message_handler(func=lambda message: message.text in ['Да, согласен(а)', 'Нет, не согласен(а)'])
def handle_consent(message):
    """Обработчик согласия на обработку данных"""
    chat_id = message.chat.id

    if message.text == 'Нет, не согласен(а)':
        bot.send_message(chat_id, "Для использования бота необходимо дать согласие на обработку персональных данных.")
        ask_for_consent(chat_id)
        return

    user = get_user_by_chat_id(chat_id)
    if user:
        user.consent_given = True
        user.consent_date = datetime.datetime.now()
        session.commit()

        # Для сотрудников отправляем заявку на организатора
        if user.donor_type == 'staff':
            send_organizer_request(user)
        else:
            bot.send_message(chat_id,
                             "Спасибо! Теперь вы можете пользоваться всеми функциями бота.",
                             reply_markup=main_menu_keyboard(is_admin=(chat_id in ADMIN_IDS)))


def send_organizer_request(user):
    """Отправка заявки на организатора"""
    # Проверяем, нет ли уже активной заявки
    existing_request = session.query(OrganizerRequest).filter_by(user_id=user.id, status='pending').first()
    if existing_request:
        bot.send_message(user.chat_id, "Ваша заявка на организатора уже отправлена и ожидает рассмотрения.")
        return

    # Создаем новую заявку
    new_request = OrganizerRequest(
        user_id=user.id,
        status='pending',
        request_date=datetime.datetime.now()
    )
    session.add(new_request)
    session.commit()

    # Отправляем заявку в чат администраторов
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Принять", callback_data=f"approve_org_{new_request.id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_org_{new_request.id}")
    )

    bot.send_message(
        ORGANIZER_APPROVAL_CHAT_ID,
        f"📋 Новая заявка на организатора:\n\n"
        f"ID: {new_request.id}\n"
        f"Пользователь: {user.name}\n"
        f"Телефон: {user.phone}\n"
        f"Дата: {new_request.request_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Статус: Ожидает рассмотрения",
        reply_markup=keyboard
    )

    bot.send_message(
        user.chat_id,
        "Ваша заявка на организатора отправлена администраторам. Вы получите уведомление, когда она будет рассмотрена.\n\n"
        "Пока ваша заявка не одобрена, вы можете пользоваться ботом как обычный пользователь.",
        reply_markup=main_menu_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_org_'))
def handle_approve_organizer(call):
    """Обработчик подтверждения заявки организатора"""
    request_id = int(call.data.split('_')[2])
    request = session.query(OrganizerRequest).get(request_id)

    if not request:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return

    if request.status != 'pending':
        bot.answer_callback_query(call.id, f"Заявка уже обработана (статус: {request.status})")
        return

    user = session.query(User).get(request.user_id)
    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    # Регистрируем организатора
    from organizer_bot import register_organizer
    register_organizer(user.chat_id, user)

    # Обновляем статус заявки
    request.status = 'approved'
    session.commit()

    # Уведомляем пользователя
    bot.send_message(
        user.chat_id,
        "🎉 Поздравляем! Ваша заявка на организатора одобрена. Теперь вам доступны дополнительные функции."
    )

    # Обновляем сообщение в чате администраторов
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📋 Заявка на организатора:\n\n"
                 f"ID: {request.id}\n"
                 f"Пользователь: {user.name}\n"
                 f"Телефон: {user.phone}\n"
                 f"Дата: {request.request_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                 f"Статус: ✅ Одобрена",
            reply_markup=None
        )
    except:
        pass

    bot.answer_callback_query(call.id, "Заявка одобрена")


@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_org_'))
def handle_reject_organizer(call):
    """Обработчик отклонения заявки организатора"""
    request_id = int(call.data.split('_')[2])
    request = session.query(OrganizerRequest).get(request_id)

    if not request:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return

    if request.status != 'pending':
        bot.answer_callback_query(call.id, f"Заявка уже обработана (статус: {request.status})")
        return

    user = session.query(User).get(request.user_id)
    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return

    # Запрашиваем причину отказа
    msg = bot.send_message(
        call.message.chat.id,
        f"Введите причину отказа для заявки ID {request_id} от пользователя {user.name}:",
        reply_markup=types.ForceReply(selective=True)
    )

    # Сохраняем ID сообщения для обработки ответа
    message_cache[f"reject_reason_{request_id}"] = msg.message_id

    bot.answer_callback_query(call.id, "Введите причину отказа")


@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите причину отказа для заявки' in message.reply_to_message.text)
@bot.message_handler(func=lambda message: message.reply_to_message and
                                      'Введите причину отказа для заявки' in message.reply_to_message.text)
def handle_rejection_reason(message):
    """Обработчик ввода причины отказа"""
    # Получаем ID заявки из текста сообщения
    request_id = int(message.reply_to_message.text.split('ID ')[1].split(' ')[0])
    reason = message.text.strip()

    if not reason:
        bot.send_message(message.chat.id, "Причина отказа не может быть пустой. Попробуйте еще раз.")
        return

    request = session.query(OrganizerRequest).get(request_id)
    if not request:
        bot.send_message(message.chat.id, "Заявка не найдена.")
        return

    user = session.query(User).get(request.user_id)
    if not user:
        bot.send_message(message.chat.id, "Пользователь не найден.")
        return

    # Удаляем запись организатора, если она была создана
    organizer = session.query(Organizer).filter_by(user_id=user.id).first()
    if organizer:
        session.delete(organizer)
        session.commit()

    # Удаляем самого пользователя
    session.delete(user)
    session.commit()

    # Обновляем заявку
    request.status = 'rejected'
    request.rejection_reason = reason
    session.commit()

    # Уведомляем пользователя
    try:
        bot.send_message(
            user.chat_id,
            f"❌ Ваша заявка на организатора отклонена.\n\n"
            f"Причина: {reason}\n\n"
            f"Для повторной подачи заявки пройдите регистрацию заново через команду /start"
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления пользователю: {e}")

    # Обновляем сообщение в чате администраторов
    try:
        bot.edit_message_text(
            chat_id=message.reply_to_message.chat.id,
            message_id=message.reply_to_message.message_id,
            text=f"📋 Заявка на организатора:\n\n"
                 f"ID: {request.id}\n"
                 f"Пользователь: {user.name}\n"
                 f"Телефон: {user.phone}\n"
                 f"Дата: {request.request_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                 f"Статус: ❌ Отклонена\n"
                 f"Причина: {reason}",
            reply_markup=None
        )
    except Exception as e:
        print(f"Ошибка при редактировании сообщения администратора: {e}")

    bot.send_message(message.chat.id, "Причина отказа отправлена пользователю. Пользователь удален из системы.")

def ask_question(chat_id: int):
    """Запрос вопроса у пользователя"""
    bot.send_message(
        chat_id,
        "Введите ваш вопрос организаторам:",
        reply_markup=types.ForceReply(selective=True)
    )

@bot.message_handler(func=lambda message: message.text in [
    '📅 Ближайшие Дни Донора',
    '🩸 Информация о донорстве крови',
    '🦴 Информация о донорстве костного мозга',
    'ℹ О донациях в МИФИ',
    '📝 Мои данные',
    '❓ Задать вопрос организаторам',
    '⚙ Админ-панель'
])
def handle_main_menu(message):
    """Обработчик главного меню"""
    chat_id = message.chat.id

    if message.text == '📅 Ближайшие Дни Донора':
        show_upcoming_events(chat_id)
    elif message.text == '🩸 Информация о донорстве крови':
        show_blood_info(chat_id)
    elif message.text == '🦴 Информация о донорстве костного мозга':
        show_bone_marrow_info(chat_id)
    elif message.text == 'ℹ О донациях в МИФИ':
        show_mephi_donation_info(chat_id)
    elif message.text == '📝 Мои данные':
        show_user_data(chat_id)
    elif message.text == '❓ Задать вопрос организаторам':
        ask_question(chat_id)  # Здесь вызываем новую функцию
    elif message.text == '⚙ Админ-панель' and chat_id in ADMIN_IDS:
        show_admin_panel(chat_id)

@bot.message_handler(func=lambda message: message.text == '⚙ Администрирование')
def handle_organizer_admin(message):
    """Обработчик кнопки администрирования для организаторов"""
    from organizer_bot import show_admin_panel
    show_admin_panel(message.chat.id)

@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите ваш вопрос организаторам' in message.reply_to_message.text)
def handle_question(message):
    """Обработчик вопроса пользователя"""
    chat_id = message.chat.id
    question_text = message.text.strip()

    if not question_text or len(question_text) < 5:
        bot.send_message(chat_id, "Вопрос слишком короткий. Пожалуйста, введите развернутый вопрос:",
                         reply_markup=types.ForceReply(selective=True))
        return

    user = get_user_by_chat_id(chat_id)
    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    # Создаем новый вопрос
    new_question = Question(
        user_id=user.id,
        text=question_text,
        answered=False,
        timestamp=datetime.datetime.now()
    )
    session.add(new_question)
    session.commit()

    # Уведомляем администраторов
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"❓ Новый вопрос от донора:\n"
                f"ID вопроса: {new_question.id}\n"
                f"Дата: {new_question.timestamp.strftime('%d.%m.%Y %H:%M')}\n"
                f"От: {user.name} ({user.phone})\n\n"
                f"Текст вопроса:\n{question_text}",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("Ответить", callback_data=f"answer_{new_question.id}")
                )
            )
        except Exception as e:
            print(f"Ошибка при уведомлении администратора {admin_id}: {e}")

    bot.send_message(chat_id, "✅ Ваш вопрос успешно отправлен организаторам. Мы ответим вам в ближайшее время.")
    start(message)


@bot.message_handler(func=lambda message: message.reply_to_message and
                                          'Введите ваш ответ:' in message.reply_to_message.text)
def handle_answer(message):
    admin_chat_id = message.chat.id
    answer_text = message.text
    question_id = int(message.reply_to_message.text.split('ID: ')[1].split(')')[0])

    question = session.query(Question).get(question_id)
    if not question:
        bot.send_message(admin_chat_id, "Вопрос не найден.")
        return

    question.answer = answer_text
    question.answered = True
    session.commit()

    # Отправляем ответ пользователю
    user = session.query(User).get(question.user_id)
    if user:
        try:
            bot.send_message(
                user.chat_id,
                f"📩 Ответ на ваш вопрос:\n{question.text}\n\n"
                f"💬 Ответ организаторов:\n{answer_text}"
            )
        except Exception as e:
            print(f"Ошибка при отправке ответа пользователю {user.chat_id}: {e}")

    bot.send_message(admin_chat_id, "Ответ успешно отправлен.")



@bot.message_handler(content_types=['location'])
def handle_location(message):
    """Обработчик геолокации"""
    chat_id = message.chat.id
    user_coords = (message.location.latitude, message.location.longitude)

    nearest_center, distance = get_nearest_center(user_coords)

    if not nearest_center:
        bot.send_message(chat_id, "Не удалось определить ближайший центр. Попробуйте позже.")
        return

    # Форматируем расстояние
    if distance < 1:
        distance_str = f"{distance * 1000:.0f} метров"
    else:
        distance_str = f"{distance:.1f} км"

    route_url = get_osm_route_url(user_coords, nearest_center['coords'])
    map_url = get_static_map_url(nearest_center['coords'])

    text = (
        f"📍 <b>Ближайший центр донорства:</b>\n\n"
        f"<b>{nearest_center['name']}</b>\n"
        f"Адрес: {nearest_center['address']}\n\n"
        f"Расстояние: {distance_str}\n"
        f"<a href='{route_url}'>Построить маршрут</a>\n\n"
    )

    # Отправляем текст
    bot.send_message(
        chat_id,
        text,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=main_menu_keyboard(is_admin=(chat_id in ADMIN_IDS))
    )

    # Отправляем статичную карту
    bot.send_photo(chat_id, map_url, caption="Местоположение центра на карте")


@bot.message_handler(func=lambda message: message.text == '📍 Ближайший центр донорства')
def handle_nearest_center(message):
    """Обработчик запроса ближайшего центра"""
    chat_id = message.chat.id

    # Формируем текст с адресами
    text = "🏥 <b>Адреса центров донорства в Москве:</b>\n\n"

    for center in BLOOD_CENTERS:
        text += f"<b>{center['name']}</b>\n"
        text += f"Адрес: {center['address']}\n\n"

    text += "\nЧтобы найти ближайший к вам центр, отправьте свою геолокацию (кнопка ниже) или нажмите /cancel для отмены."

    # Создаем клавиатуру с кнопкой отправки геолокации
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        types.KeyboardButton('📍 Отправить геолокацию', request_location=True),
        types.KeyboardButton('🔙 Назад')
    )

    bot.send_message(
        chat_id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


@bot.message_handler(func=lambda message: message.text in [
    '📊 Статистика',
    '✏ Редактировать данные доноров',
    '📩 Ответить на вопросы',
    '📢 Сделать рассылку',
    '➕ Создать мероприятие',
    '📝 Изменить информационные разделы',
    '📥 Загрузить данные донаций',
    '📤 Выгрузить статистику',
    '🔙 Главное меню'
])

def handle_admin_commands(message):
    """Обработчик команд администратора"""
    chat_id = message.chat.id

    if chat_id not in ADMIN_IDS:
        bot.send_message(chat_id, "У вас нет прав доступа.")
        return

    if message.text == '📊 Статистика':
        show_admin_stats(chat_id)
    elif message.text == '✏ Редактировать данные доноров':
        # Реализация редактирования данных доноров
        pass
    elif message.text == '📩 Ответить на вопросы':
        # Реализация ответа на вопросы
        pass
    elif message.text == '📢 Сделать рассылку':
        # Реализация рассылки
        pass
    elif message.text == '➕ Создать мероприятие':
        # Реализация создания мероприятия
        pass
    elif message.text == '📝 Изменить информационные разделы':
        # Реализация изменения информационных разделов
        pass
    elif message.text == '📥 Загрузить данные донаций':
        # Реализация загрузки данных донаций
        pass
    elif message.text == '📤 Выгрузить статистику':
        export_stats(chat_id)
    elif message.text == '🔙 Главное меню':
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu_keyboard(is_admin=True))

register_for_event
# ====================== ОБРАБОТЧИКИ CALLBACK-ЗАПРОСОВ ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith('register_'))
def handle_register_callback(call):
    """Обработчик регистрации на мероприятие"""
    event_id = int(call.data.split('_')[1])
    register_for_event(call.message.chat.id, event_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_'))
def handle_answer_callback(call):
    """Обработчик ответа на вопрос"""
    question_id = int(call.data.split('_')[1])
    answer_question(call.message.chat.id, question_id)


@bot.callback_query_handler(func=lambda call: call.data == 'edit_user_data')
def handle_edit_user_data(call):
    """Обработчик изменения данных пользователя"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    btn1 = types.InlineKeyboardButton("✏️ Изменить ФИО", callback_data="edit_name")
    btn2 = types.InlineKeyboardButton("📚 Изменить группу", callback_data="edit_group")
    btn3 = types.InlineKeyboardButton("🔄 Изменить статус ДКМ", callback_data="edit_bm_status")
    btn4 = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile")

    keyboard.add(btn1)
    if user.donor_type == 'student':
        keyboard.add(btn2)
    keyboard.add(btn3, btn4)

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="Выберите, что хотите изменить:",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")
        bot.send_message(chat_id, "Выберите, что хотите изменить:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == 'edit_name')
def handle_edit_name(call):
    """Обработчик изменения ФИО"""
    chat_id = call.message.chat.id
    msg = bot.send_message(chat_id, "Введите новое ФИО:", reply_markup=types.ForceReply(selective=True))
    bot.register_next_step_handler(msg, process_name_change)


def process_name_change(message):
    """Обработка изменения ФИО"""
    chat_id = message.chat.id
    user = get_user_by_chat_id(chat_id)
    new_name = message.text.strip()

    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    if not validate_name(new_name):
        msg = bot.send_message(chat_id, "Неверный формат ФИО. Введите в формате 'Иванов Иван Иванович':",
                               reply_markup=types.ForceReply(selective=True))
        bot.register_next_step_handler(msg, process_name_change)
        return

    user.name = new_name
    session.commit()
    bot.send_message(chat_id, "✅ ФИО успешно изменено!")
    show_user_data(chat_id)
    start(message)


@bot.callback_query_handler(func=lambda call: call.data == 'edit_group')
def handle_edit_group(call):
    """Обработчик изменения группы"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.donor_type != 'student':
        bot.send_message(chat_id, "Эта функция доступна только студентам.")
        return

    msg = bot.send_message(chat_id, "Введите новую группу:", reply_markup=types.ForceReply(selective=True))
    bot.register_next_step_handler(msg, process_group_change)


def process_group_change(message):
    """Обработка изменения группы"""
    chat_id = message.chat.id
    user = get_user_by_chat_id(chat_id)
    new_group = message.text.strip()

    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    if not validate_group(new_group):
        msg = bot.send_message(chat_id, "Неверный формат группы. Попробуйте еще раз:",
                               reply_markup=types.ForceReply(selective=True))
        bot.register_next_step_handler(msg, process_group_change)
        return

    user.group = new_group
    session.commit()
    bot.send_message(chat_id, "✅ Группа успешно изменена!")
    show_user_data(chat_id)
    start(message)


@bot.callback_query_handler(func=lambda call: call.data == 'back_to_profile')
def handle_back_to_profile(call):
    """Обработчик возврата к профилю"""
    show_user_data(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data in ['edit_bm_status'])
def handle_edit_bm_status(call):
    """Обработчик изменения статуса ДКМ"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)
    current_status = "да" if user.in_bm_registry else "нет"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("Да", callback_data="set_bm_yes"),
        types.InlineKeyboardButton("Нет", callback_data="set_bm_no")
    )

    bot.send_message(chat_id, f"Текущий статус в регистре ДКМ: {current_status}. Изменить на:",
                     reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data in ['set_bm_yes', 'set_bm_no'])
def handle_bm_status_change(call):
    """Обработчик изменения статуса ДКМ"""
    chat_id = call.message.chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    if call.data == 'set_bm_yes':
        user.in_bm_registry = True
        session.commit()
        bot.answer_callback_query(call.id, "Статус ДКМ изменен на 'да'")
    else:
        user.in_bm_registry = False
        session.commit()
        bot.answer_callback_query(call.id, "Статус ДКМ изменен на 'нет'")

    show_user_data(chat_id)
    start(message)


# ====================== ЗАПУСК БОТА ======================

class ColoredFormatter(logging.Formatter):
    """Кастомный форматтер с цветами для разных уровней логгирования"""

    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: GREEN + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.INFO: GREEN + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.WARNING: YELLOW + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.ERROR: RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.CRITICAL: BOLD_RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


if __name__ == "__main__":

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(ColoredFormatter())

    logger.addHandler(ch)

    print("Бот запускается...")
    bot.infinity_polling()