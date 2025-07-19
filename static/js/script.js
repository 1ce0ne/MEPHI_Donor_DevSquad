// Общая функция для управления модальными окнами
function initModal(modalId, btnId, formId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    const btn = document.getElementById(btnId);
    const form = document.getElementById(formId);
    const closeBtn = modal.querySelector('.close-modal');

    if (btn) btn.onclick = () => modal.style.display = 'block';
    if (closeBtn) closeBtn.onclick = () => modal.style.display = 'none';
}

// Универсальный обработчик кнопок "Подробнее"
function setupDetailsButtons(buttonClass, rowPrefix) {
    document.querySelectorAll(buttonClass).forEach(button => {
        button.addEventListener('click', function() {
            const id = this.getAttribute('data-id');
            const detailsRow = document.getElementById(`${rowPrefix}-${id}`);
            if (detailsRow) {
                detailsRow.style.display = detailsRow.style.display === 'none' ? 'table-row' : 'none';
            }
        });
    });
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
    // Модальные окна для всех страниц
    initModal('mailingModal', 'addMailingBtn', 'mailingForm');
    initModal('eventModal', 'addEventBtn', 'eventForm');
    initModal('uploadStatsModal', 'uploadStatsBtn', 'uploadStatsForm');

    // Обработчики закрытия модальных окон
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    };

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
        }
    });

    // Инициализация кнопок "Подробнее" для всех страниц
    setupDetailsButtons('.event-details-btn', 'event-details');
    setupDetailsButtons('.donor-details-btn', 'donor-details');
});