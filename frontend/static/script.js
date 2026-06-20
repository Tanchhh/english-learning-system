window.toggleTheme = function() {
    const body = document.body;
    const isDark = body.classList.toggle('dark-mode');

    localStorage.setItem('darkMode', isDark);

    updateThemeIcon(isDark);
};

function updateThemeIcon(isDark) {
    const icons = document.querySelectorAll('.theme-toggle');
    icons.forEach(icon => {
        icon.textContent = isDark ? '☀️' : '🌙';
        icon.setAttribute('title', isDark ? 'Светлая тема' : 'Тёмная тема');
    });
}

function loadTheme() {
    const isDark = localStorage.getItem('darkMode') === 'true';
    if (isDark) {
        document.body.classList.add('dark-mode');
    }
    updateThemeIcon(isDark);
}

window.logout = function() {
    localStorage.removeItem('token');
    localStorage.removeItem('isAdmin');
    localStorage.removeItem('username');

    window.location.href = '/';
};

window.checkAuthUI = function() {
    const token = localStorage.getItem('token');
    const isAdmin = localStorage.getItem('isAdmin') === 'true';

    const loginBtn = document.getElementById('nav-login');
    const profileBtn = document.getElementById('nav-profile');
    const adminBtn = document.getElementById('nav-admin');
    const logoutBtn = document.getElementById('logoutBtn');

    if (token) {
        if (loginBtn) loginBtn.style.display = 'none';
        if (profileBtn) profileBtn.style.display = 'inline-block';
        if (adminBtn) {
            adminBtn.style.display = isAdmin ? 'inline-block' : 'none';
        }
        if (logoutBtn) {
            logoutBtn.style.display = 'inline-block';
            logoutBtn.onclick = logout;
        }
    } else {
        if (loginBtn) loginBtn.style.display = 'inline-block';
        if (profileBtn) profileBtn.style.display = 'none';
        if (adminBtn) adminBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'none';
    }
};

window.showAlert = function(message, type = 'error') {
    const alertBox = document.getElementById('alert');
    if (!alertBox) return;

    alertBox.className = '';
    alertBox.classList.add(`alert-${type}`);
    alertBox.textContent = message;
    alertBox.style.display = 'block';

    setTimeout(() => {
        alertBox.style.display = 'none';
        alertBox.textContent = '';
    }, 4000);
};

async function loadTopics() {
    const container = document.getElementById('topicsList');
    if (!container) return;

    try {
        const response = await fetch('/api/topics');
        if (!response.ok) throw new Error('Ошибка сети');

        const topics = await response.json();
        container.innerHTML = '';

        if (topics.length === 0) {
            container.innerHTML = '<p class="text-center" style="grid-column: 1/-1;">Тем пока нет. Администратор может добавить их в панели управления.</p>';
            return;
        }

        topics.forEach(topic => {
            let badgeClass = 'badge-a1';
            if (topic.level === 'A2') badgeClass = 'badge-a2';
            if (topic.level === 'B1') badgeClass = 'badge-b1';
            if (topic.level === 'B2') badgeClass = 'badge-b2';

            const cardHtml = `
                <div class="card topic-card" onclick="window.location.href='/topic/${topic.id}'">
                    <span class="badge ${badgeClass}">${topic.level || 'General'}</span>
                    <h3>${topic.title}</h3>
                    <p style="color: var(--text-secondary); font-size: 0.9rem;">
                        ${topic.description || 'Нет описания'}
                    </p>
                </div>
            `;
            container.innerHTML += cardHtml;
        });

    } catch (error) {
        console.error('Ошибка загрузки тем:', error);
        container.innerHTML = `
            <div class="card text-center" style="grid-column: 1/-1;">
                <p style="color: var(--error);">❌ Не удалось загрузить список тем</p>
                <p style="font-size: 0.9rem; color: var(--text-secondary);">
                    Проверьте подключение к серверу и попробуйте обновить страницу
                </p>
            </div>
        `;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadTheme();

    checkAuthUI();

    if (document.getElementById('topicsList')) {
        loadTopics();
    }

    console.log('✅ Страница загружена, скрипты инициализированы');
});