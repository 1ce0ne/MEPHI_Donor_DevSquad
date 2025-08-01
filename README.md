# 🩸 MEPHI Donor - Система управления донорскими акциями

## 🏆 Хакатон "Nuclear IT Hack"

**MEPHI Donor** - это инновационная система для организации и управления донорскими акциями в учебных заведениях, разработанная командой *"DevSquad"* на хакатоне "Nuclear IT Hack".

## 📌 Оглавление

1. [✨ Особенности](#-особенности)
2. [🏗️ Архитектура](#️-архитектура)
3. [🛠️ Технологический стек](#️-технологический-стек)
4. [🚀 Запуск проекта](#-запуск-проекта)
5. [📱 Использование бота](#-использование-бота)
6. [🧩 Структура проекта](#-структура-проекта)
7. [👨‍💻 Команда](#-команда)

---

## ✨ Особенности

### Для доноров:
- 📅 Регистрация на мероприятия в 1 клик
- 📱 Удобный интерфейс в Telegram
- ℹ️ Вся информация о донорстве в одном месте
- 📍 Поиск ближайшего центра сдачи крови
- ❓ Возможность задать вопрос организаторам

### Для организаторов:
- 📊 Полная статистика по донорам и мероприятиям
- 📢 Гибкая система рассылок
- 📝 Управление мероприятиями
- 📥 Импорт/экспорт данных
- 👥 Управление командой организаторов

---

## 🏗️ Архитектура

1. **Telegram Bot** - основной интерфейс для доноров
2. **FastAPI Server** - backend система
3. **SQLite Database** - хранение данных
4. **Admin Panel** - веб-интерфейс для организаторов

---

## 🛠️ Технологический стек

### Backend:
- Python 3.10
- FastAPI
- SQLAlchemy
- Telebot (python-telegram-bot)

### Frontend:
- HTML5, CSS3, JavaScript
- Jinja2 templates

### База данных:
- SQLite (для разработки)
  
---

## 🚀 Запуск проекта

### Предварительные требования:
- Python 3.10+
- Telegram bot token
- Доступ к серверу (для продакшена)

### Установка:

Установите зависимости:
```bash
python -m venv venv
source venv/bin/activate  # Linux/MacOS
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Запуск:

1. Запустите FastAPI сервер:
```bash
uvicorn MainWebAPP:app --reload
```

2. Запустите Telegram бота:
```bash
python users_bot.py
```

3. Запустите бота для администраторов (в отдельном терминале):
```bash
python adminbot.py
```

---

## 📱 Использование бота

### Основные команды:
- `/start` - начать работу с ботом
- `📅 Ближайшие Дни Донора` - список мероприятий
- `🩸 Информация о донорстве` - требования и рекомендации
- `📝 Мои данные` - просмотр и редактирование профиля

### Процесс регистрации:
1. Отправьте контакт (номер телефона)
2. Введите ФИО
3. Выберите статус (студент/сотрудник)
4. Дайте согласие на обработку данных

---

### Возможности:
- 👥 Управление донорами
- 📅 Создание мероприятий
- 📊 Просмотр статистики
- 📢 Отправка рассылок
- ❓ Ответы на вопросы

---

## 🧩 Структура проекта

```
MEPHI_Donor_DevSquad/
│                           # Telegram боты
├── users_bot.py            # Бот для доноров
├── organizer_bot.py        # Бот для приема заявок организаторам
├── adminbot.py             # Бот для администраторов
│ 
├── documents/              # Документы
│   └── soglas.pdf          # Согласие на обработку данных
│          
├── static/                 # Статические файлы
│   ├──  css              
│   │    └── style.css
│   ├──  img
│   │    └── logo.png              
│   └──  js
│        └── script.js              
│
│
└── MainWebAPP.py           # Backend для Web сайта
```

---

## 👨‍💻 Команда

- **Попов Иван** - Team Lead, Fullstack Developer
- **Никифоров Данила** - Frontend Developer
- **Пятковский Артём** - Backend Designer

## Презентация
https://www.figma.com/slides/dYBb79PtEnZiAbSzSYTHAd/Product-Review?node-id=1-880&t=HxqKSJPR3AqH7BrX-1

## Админ бот
@mephidonor_admin_bot

## Обычный бот
@mephidonor_bot

---

🚀 **Давайте вместе делать добро с помощью технологий!** 🚀
