# organizer_bot.py
import telebot
from telebot import types
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
from users_bot import bot, session, get_user_by_chat_id, ADMIN_IDS, User

# Удаляем свою модель Organizer и используем модель из adminbot.py
from adminbot import Organizer


def is_organizer(chat_id):
    """Проверка, является ли пользователь организатором"""
    user = get_user_by_chat_id(chat_id)
    if not user:
        return False

    # Проверяем, есть ли активная запись в таблице организаторов
    organizer = session.query(Organizer).filter_by(user_id=user.id, is_active=True).first()
    return organizer is not None


def register_organizer(chat_id, user):
    """Завершение регистрации сотрудника как организатора"""
    # Проверяем, не зарегистрирован ли уже как организатор
    existing = session.query(Organizer).filter_by(user_id=user.id).first()
    if existing:
        if existing.is_active:
            bot.send_message(chat_id, "Вы уже зарегистрированы как организатор.")
            return
        else:
            # Активируем существующего организатора
            existing.is_active = True
            session.commit()
    else:
        # Создаем нового организатора
        new_organizer = Organizer(
            user_id=user.id,
            is_active=True
        )
        session.add(new_organizer)
        session.commit()

    # Обновляем клавиатуру
    keyboard = create_main_menu_keyboard(chat_id)
    bot.send_message(chat_id,
                     "✅ Вы зарегистрированы как организатор. Доступно меню администратора.",
                     reply_markup=keyboard)


def show_admin_panel(chat_id):
    user = get_user_by_chat_id(chat_id)
    if not user:
        bot.send_message(chat_id, "Сначала нужно пройти регистрацию.")
        return

    # Проверяем, является ли пользователь организатором
    if not is_organizer(chat_id):
        bot.send_message(chat_id, "Вы не зарегистрированы как организатор.")
        return

    admin_url = "http://89.23.113.93:3000/"
    bot.send_message(chat_id, f"🔐 Административная панель:\n{admin_url}",
                     disable_web_page_preview=True)


def create_main_menu_keyboard(chat_id=None, is_admin=False, is_organizer_flag=False):
    """Обновленная клавиатура с учетом организатора"""
    if chat_id is not None:
        is_organizer_flag = is_organizer(chat_id)
        is_admin = chat_id in ADMIN_IDS

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('📅 Ближайшие Дни Донора')
    btn2 = types.KeyboardButton('🩸 Информация о донорстве крови')
    btn3 = types.KeyboardButton('🦴 Информация о донорстве костного мозга')
    btn4 = types.KeyboardButton('ℹ О донациях в МИФИ')
    btn5 = types.KeyboardButton('📝 Мои данные')
    btn6 = types.KeyboardButton('❓ Задать вопрос организаторам')
    btn7 = types.KeyboardButton('📍 Ближайший центр донорства')

    keyboard.add(btn5, btn6)
    keyboard.add(btn1, btn7)
    keyboard.add(btn2, btn3)
    keyboard.add(btn4)

    if is_admin:
        keyboard.add(types.KeyboardButton('⚙ Админ-панель'))
    elif is_organizer_flag:
        keyboard.add(types.KeyboardButton('⚙ Администрирование'))

    return keyboard