(function() {
    const STORAGE_KEY = 'scicollab-language';
    const DEFAULT_LANG = 'en';
    const TARGET_LANG = 'ru';
    const textOriginals = new WeakMap();
    let currentLang = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
    let observer = null;
    let observerTimer = null;

    const dictionary = {
        'SciCollab': 'SciCollab',
        'Projects': 'Проекты',
        'Project': 'Проект',
        'Project Feed': 'Лента проектов',
        'My Projects': 'Мои проекты',
        'Create Project': 'Создать проект',
        'Profile': 'Профиль',
        'Change Profile': 'Редактировать профиль',
        'Logout': 'Выйти',
        'Login': 'Войти',
        'Register': 'Регистрация',
        'Register with Password': 'Зарегистрироваться с паролем',
        'Sign In': 'Войти',
        'Create Account': 'Создать аккаунт',
        "Don't have a password account?": 'Нет аккаунта с паролем?',
        'Already have an account?': 'Уже есть аккаунт?',
        'Remember Me': 'Запомнить меня',
        'Email': 'Эл. почта',
        'Password': 'Пароль',
        'Repeat Password': 'Повторите пароль',
        'Username': 'Имя пользователя',
        'Name': 'Имя',
        'Surname': 'Фамилия',
        'University': 'Университет',
        'Degree': 'Степень',
        'Avatar': 'Аватар',
        'Skills': 'Навыки',
        'Skills:': 'Навыки:',
        'Fields/Interests': 'Области/интересы',
        'Fields/Interests:': 'Области/интересы:',
        'Save Changes': 'Сохранить изменения',
        'Your Profile': 'Ваш профиль',
        'Edit Profile': 'Редактировать профиль',
        'Details': 'Детали',
        'Achievements': 'Достижения',
        'No achievements yet.': 'Достижений пока нет.',
        'No additional details provided.': 'Дополнительные сведения не указаны.',
        'Invite to Chat': 'Пригласить в чат',
        'Invite': 'Пригласить',
        'Project:': 'Проект:',
        'Title': 'Название',
        'Description': 'Описание',
        'Goals': 'Цели',
        'Tags': 'Теги',
        'Project Tags': 'Теги проекта',
        'Project Image': 'Изображение проекта',
        'Project Materials': 'Материалы проекта',
        'Deadline Date': 'Дата дедлайна',
        'Deadline Time (Optional, 24hr format HH:MM)': 'Время дедлайна (необязательно, формат 24ч HH:MM)',
        'Project Type': 'Тип проекта',
        'Public Project': 'Публичный проект',
        'Cancel': 'Отмена',
        'Create Chat': 'Создать чат',
        'Create New Chat': 'Создать новый чат',
        'Chat Name': 'Название чата',
        'Chat Details': 'Детали чата',
        'Create New Chat for': 'Создать новый чат для',
        'Enter chat name...': 'Введите название чата...',
        'Message': 'Сообщение',
        'Send': 'Отправить',
        'File': 'Файл',
        'Search': 'Поиск',
        'Type': 'Тип',
        'Chats': 'Чаты',
        'Experiment': 'Эксперимент',
        'Study': 'Исследование',
        'Other': 'Другое',
        'Public': 'Публичный',
        'Private': 'Приватный',
        'Created by:': 'Создал:',
        'Created on:': 'Создано:',
        'Deadline:': 'Дедлайн:',
        'Type:': 'Тип:',
        'Visibility:': 'Видимость:',
        'No deadline set': 'Дедлайн не задан',
        'Leave Project': 'Покинуть проект',
        'Application Pending': 'Заявка ожидает ответа',
        'Apply to Project': 'Подать заявку',
        'Private Project': 'Приватный проект',
        'Edit Project': 'Редактировать проект',
        'Delete Project': 'Удалить проект',
        'Current Image': 'Текущее изображение',
        'Existing Materials': 'Существующие материалы',
        'Delete': 'Удалить',
        'No materials uploaded yet.': 'Материалы пока не загружены.',
        'Project Chats': 'Чаты проекта',
        'Team Members': 'Участники команды',
        'Admins': 'Администраторы',
        'Members': 'Участники',
        'Creator': 'Создатель',
        'You': 'Вы',
        'Remove Admin': 'Убрать администратора',
        'Creator (Cannot be demoted)': 'Создатель (нельзя понизить)',
        'Make Admin': 'Сделать администратором',
        'Remove': 'Удалить',
        'All members are admins.': 'Все участники являются администраторами.',
        'No members yet.': 'Участников пока нет.',
        'This is a private project. You need to be invited to see more details or members.': 'Это приватный проект. Чтобы увидеть детали и участников, нужно приглашение.',
        'Apply to this project to see chats and member details.': 'Подайте заявку на проект, чтобы увидеть чаты и участников.',
        'Project Feed': 'Лента проектов',
        'Loading more projects...': 'Загружаем еще проекты...',
        "You've reached the end!": 'Вы дошли до конца!',
        'No more projects to show. Check back later for new opportunities!': 'Больше проектов нет. Загляните позже за новыми возможностями.',
        'Create Your Own Project': 'Создать свой проект',
        'Apply to Join': 'Подать заявку',
        'View Details': 'Подробнее',
        'No projects found!': 'Проекты не найдены!',
        'Create a Project': 'Создать проект',
        'Goals': 'Цели',
        'By': 'Автор',
        'Unknown': 'Неизвестно',
        'Projects I Created': 'Проекты, которые я создал',
        "Projects I'm a Member Of": 'Проекты, где я участник',
        "You haven't created any projects yet.": 'Вы пока не создали ни одного проекта.',
        'Create one now!': 'Создать сейчас!',
        'You are not a member of any other projects yet.': 'Вы пока не состоите в других проектах.',
        'Explore projects!': 'Посмотреть проекты!',
        'View Project': 'Открыть проект',
        'Real-Time Chat': 'Чат в реальном времени',
        'Create and join projects': 'Создавайте проекты и присоединяйтесь к ним',
        'Welcome to Science Collab': 'Добро пожаловать в Science Collab',
        'A platform for students to connect, collaborate, and create science projects together.': 'Платформа, где студенты знакомятся, сотрудничают и создают научные проекты вместе.',
        'Start scientific projects and invite others to collaborate with you': 'Запускайте научные проекты и приглашайте других к совместной работе',
        'Communicate with your team in real-time with project-specific chat rooms': 'Общайтесь с командой в реальном времени в чатах отдельных проектов',
        'Privacy Policy': 'Политика конфиденциальности',
        'Notifications': 'Уведомления',
        'Loading notifications...': 'Загружаем уведомления...',
        'Error loading notifications': 'Ошибка загрузки уведомлений',
        'Retry': 'Повторить',
        'No new notifications': 'Новых уведомлений нет',
        "You're all caught up!": 'Вы все посмотрели!',
        'Accept': 'Принять',
        'Reject': 'Отклонить',
        'Dismiss': 'Скрыть',
        'Dismissing...': 'Скрываем...',
        'Accepting...': 'Принимаем...',
        'Rejecting...': 'Отклоняем...',
        'Accepted!': 'Принято!',
        'Members': 'Участники',
        'Delete Chat': 'Удалить чат',
        'Leave Chat': 'Покинуть чат',
        'Unknown User': 'Неизвестный пользователь',
        'No messages yet. Be the first to start the conversation!': 'Сообщений пока нет. Начните разговор первым!',
        'Type a message...': 'Введите сообщение...',
        'Chat Members': 'Участники чата',
        'Invite Member': 'Пригласить участника',
        'No new project members to invite.': 'Нет новых участников проекта для приглашения.',
        'Previous': 'Назад',
        'Next': 'Далее',
        'Change Language': 'Сменить язык',
        'Language Icon': 'Иконка языка',
        'Notification Icon': 'Иконка уведомлений',
        'Profile Avatar': 'Аватар профиля',
        'Project Image': 'Изображение проекта',
        'Default Project Image': 'Стандартное изображение проекта',
        'Generic Project': 'Стандартный проект',
        'Attachment': 'Вложение',
        'Attach': 'Прикрепить',
        'Close': 'Закрыть',
        'File': 'Файл',
        'Landing Image': 'Изображение главной страницы',
        'Scientific Collaboration Platform': 'Платформа научного сотрудничества',
        'Welcome to Science Collab': 'Добро пожаловать в Science Collab'
    };

    const patterns = [
        [/^(.+)'s Profile$/, '$1 — профиль'],
        [/^Created:\s*(.+)$/, 'Создано: $1'],
        [/^Created on:\s*(.+)$/, 'Создано: $1'],
        [/^Deadline:\s*(.+)$/, 'Дедлайн: $1'],
        [/^By\s+(.+)$/, 'Автор: $1'],
        [/^From:\s*(.+)$/, 'От: $1'],
        [/^Members:\s*(\d+)$/, 'Участники: $1'],
        [/^Members:\s*(\d+)\s*•\s*Created on:\s*(.+)$/, 'Участники: $1 • Создано: $2'],
        [/^Page\s+(\d+)\s+of\s+(\d+)$/, 'Страница $1 из $2'],
        [/^Projects I Created\s*\((.+)\)$/, 'Проекты, которые я создал ($1)'],
        [/^Projects I'm a Member Of\s*\((.+)\)$/, 'Проекты, где я участник ($1)'],
        [/^Team Members\s*\((.+)\)$/, 'Участники команды ($1)'],
        [/^Admins\s*\((.+)\)$/, 'Администраторы ($1)'],
        [/^Create New Chat for\s+(.+)$/, 'Создать новый чат для $1'],
        [/^Project:\s*(.+)$/, 'Проект: $1'],
        [/^Uploaded by\s+(.+)\s+on\s+(.+)$/, 'Загрузил $1 $2'],
        [/^Try updating your\s+preferences\s+or check back later for new projects\.$/, 'Обновите предпочтения или загляните позже за новыми проектами.']
    ];

    const reverseDictionary = Object.fromEntries(
        Object.entries(dictionary).map(function(entry) {
            return [entry[1], entry[0]];
        })
    );

    function translateText(text, lang) {
        const trimmed = text.trim();
        if (!trimmed) return text;

        const leading = text.match(/^\s*/)[0];
        const trailing = text.match(/\s*$/)[0];

        if (lang === TARGET_LANG) {
            if (dictionary[trimmed]) return leading + dictionary[trimmed] + trailing;
            for (const item of patterns) {
                if (item[0].test(trimmed)) return leading + trimmed.replace(item[0], item[1]) + trailing;
            }
            return text;
        }

        if (reverseDictionary[trimmed]) return leading + reverseDictionary[trimmed] + trailing;
        return text;
    }

    function translateTextNode(node, lang) {
        if (!textOriginals.has(node)) {
            textOriginals.set(node, node.nodeValue);
        }

        const original = textOriginals.get(node);
        node.nodeValue = lang === TARGET_LANG ? translateText(original, lang) : original;
    }

    function translateAttribute(element, attr, lang) {
        if (!element.hasAttribute(attr)) return;

        const dataKey = 'i18nOriginal' + attr.replace(/[-:](.)/g, function(_, char) {
            return char.toUpperCase();
        }).replace(/^(.)/, function(_, char) {
            return char.toUpperCase();
        });

        if (!element.dataset[dataKey]) {
            element.dataset[dataKey] = element.getAttribute(attr);
        }

        const original = element.dataset[dataKey];
        element.setAttribute(attr, lang === TARGET_LANG ? translateText(original, lang) : original);
    }

    function shouldSkipTextNode(node) {
        const parent = node.parentElement;
        if (!parent) return true;
        return ['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName);
    }

    function applyTranslation(root) {
        const scope = root || document.body;
        if (!scope) return;

        if (scope.nodeType === Node.TEXT_NODE) {
            if (!shouldSkipTextNode(scope)) translateTextNode(scope, currentLang);
            return;
        }

        const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
            acceptNode: function(node) {
                return shouldSkipTextNode(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            }
        });

        const nodes = [];
        while (walker.nextNode()) {
            nodes.push(walker.currentNode);
        }
        nodes.forEach(function(node) {
            translateTextNode(node, currentLang);
        });

        const elements = scope.querySelectorAll ? scope.querySelectorAll('input, textarea, button, img, [title], [aria-label], [placeholder]') : [];
        elements.forEach(function(element) {
            ['placeholder', 'value', 'alt', 'title', 'aria-label'].forEach(function(attr) {
                if (attr === 'value' && !['submit', 'button', 'reset'].includes((element.type || '').toLowerCase())) return;
                translateAttribute(element, attr, currentLang);
            });
        });

        translateDocumentTitle();
        updateLanguageButton();
    }

    function translateDocumentTitle() {
        if (!document.documentElement.dataset.i18nOriginalTitle) {
            document.documentElement.dataset.i18nOriginalTitle = document.title;
        }

        const original = document.documentElement.dataset.i18nOriginalTitle;
        document.title = currentLang === TARGET_LANG ? translateText(original, currentLang) : original;
    }

    function updateLanguageButton() {
        document.querySelectorAll('#header-change-lang').forEach(function(button) {
            button.setAttribute('aria-label', currentLang === TARGET_LANG ? 'Switch to English' : 'Переключить на русский');
            button.setAttribute('title', currentLang === TARGET_LANG ? 'Switch to English' : 'Переключить на русский');
            button.dataset.lang = currentLang.toUpperCase();
        });
        document.documentElement.lang = currentLang;
    }

    function toggleLanguage() {
        currentLang = currentLang === TARGET_LANG ? DEFAULT_LANG : TARGET_LANG;
        localStorage.setItem(STORAGE_KEY, currentLang);
        applyTranslation(document.body);
    }

    window.SciCollabI18n = {
        apply: function(root) {
            applyTranslation(root || document.body);
        },
        getLanguage: function() {
            return currentLang;
        }
    };

    function observeDynamicContent() {
        if (observer) observer.disconnect();

        observer = new MutationObserver(function(mutations) {
            if (currentLang !== TARGET_LANG) return;
            clearTimeout(observerTimer);
            observerTimer = setTimeout(function() {
                mutations.forEach(function(mutation) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
                            applyTranslation(node);
                        }
                    });
                });
            }, 25);
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('#header-change-lang').forEach(function(button) {
            button.addEventListener('click', toggleLanguage);
        });

        applyTranslation(document.body);
        observeDynamicContent();
    });
})();
