/* User-controlled content is rendered as text, never parsed as HTML. */
window.SciCollabUI = (() => {
    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function localUrl(value) {
        if (typeof value !== 'string' || !value.startsWith('/')) return '#';
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? url.href : '#';
        } catch {
            return '#';
        }
    }

    function link(url, text, className) {
        const node = element('a', className, text);
        node.href = localUrl(url);
        return node;
    }

    function image(url, alt, className) {
        const node = element('img', className);
        node.src = localUrl(url);
        node.alt = alt || '';
        return node;
    }

    function csrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    function postForm(url, label, className) {
        const form = element('form', 'action-form');
        form.method = 'post';
        form.action = localUrl(url);
        const token = element('input');
        token.type = 'hidden';
        token.name = 'csrf_token';
        token.value = csrfToken();
        const button = element('button', className, label);
        button.type = 'submit';
        form.append(token, button);
        return form;
    }

    function projectCard(project, index) {
        const card = element('div', 'project-card');
        card.dataset.index = index;
        const picture = element('div', 'project-image');
        if (project.image) {
            picture.append(image(project.image, project.title));
        } else {
            picture.classList.add('generic');
            picture.append(image('/static/uploads/default-project.svg', 'Generic Project'));
        }
        const content = element('div', 'project-card-content');
        content.append(element('h2', 'project-title', project.title));
        if (project.tags?.length) {
            const tags = element('div', 'project-tags');
            project.tags.forEach(tag => tags.append(element('span', 'project-tag', tag)));
            content.append(tags);
        }
        if (project.description) content.append(element('p', 'project-description', project.description));
        if (project.goals) {
            content.append(element('div', 'project-goals-title', 'Goals'),
                element('p', 'project-goals', project.goals));
        }
        const meta = element('div', 'project-meta');
        const creator = element('div', '', 'By ');
        creator.append(link(project.creator ? `/users/view/${project.creator.id}` : '#',
            project.creator?.username || 'Unknown'));
        meta.append(creator, element('div', '', `Deadline: ${project.deadline || 'No deadline set'}`));
        const actions = element('div', 'project-actions');
        actions.append(postForm(project.apply_url, 'Apply to Join', 'full-button'),
            link(project.view_url, 'View Details', 'full-button'));
        content.append(meta, actions);
        card.append(picture, content);
        return card;
    }

    function message(message, currentUserId) {
        const root = element('div', `message ${message.user_id === currentUserId ? 'message-outgoing' : 'message-incoming'}`);
        root.id = `message-${message.id}`;
        const avatar = element('div', 'message-avatar');
        avatar.append(image(message.avatar_url, message.username));
        const content = element('div', 'message-content');
        const header = element('div', 'message-header');
        const author = element('span', 'message-author');
        author.append(link(`/users/view/${message.user_id}`, message.username));
        header.append(author, element('span', 'message-time',
            new Date(message.timestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})));
        const body = element('div', 'message-body');
        if (message.text) body.append(element('p', 'message-text', message.text));
        if (message.file && message.attachment_url) {
            const attachment = element('div', 'message-attachment');
            const download = link(message.attachment_url);
            download.target = '_blank';
            download.rel = 'noopener noreferrer';
            if (/\.(jpg|jpeg|png|gif)$/i.test(message.file)) {
                download.append(image(message.preview_url, 'Attachment', 'message-image'));
            } else {
                const file = element('div', 'file-attachment');
                file.append(element('span', '', message.file.split('_').slice(1).join('_') || message.file));
                download.append(file);
            }
            attachment.append(download);
            body.append(attachment);
        }
        content.append(header, body);
        root.append(avatar, content);
        return root;
    }

    function notification(notification, formatTimestamp) {
        const item = element('div', 'notification-item');
        item.dataset.id = notification.id;
        item.dataset.projectId = notification.project_id || '';
        item.dataset.chatId = notification.chat_id || '';
        // Older notifications may contain HTML; it is deliberately displayed as text.
        item.append(element('p', '', notification.text));
        const details = element('small', '', 'From: ');
        details.append(notification.sender
            ? link(`/users/view/${notification.sender.id}`, notification.sender.username)
            : document.createTextNode('System'));
        details.append(document.createTextNode(` • ${formatTimestamp(notification.timestamp)}`));
        item.append(details);
        function action(label, className) {
            const button = element('button', className, label);
            button.type = 'button';
            button.dataset.id = notification.id;
            return button;
        }
        if (notification.type === 'invite') {
            const actions = element('div', 'notification-actions');
            actions.append(action('Accept', 'accept-btn'), action('Reject', 'reject-btn'));
            item.append(actions);
        }
        item.append(action('Dismiss', 'dismiss-btn'));
        return item;
    }

    function searchResults(items) {
        const list = element('ul');
        items.forEach(item => {
            const row = element('li');
            const result = link(item.url, `${item.title || item.name} `);
            result.append(element('small', 'text-muted', `(${item.type})`));
            row.append(result);
            list.append(row);
        });
        return list;
    }

    document.addEventListener('submit', event => {
        const message = event.target.dataset.confirm;
        if (message && !window.confirm(message)) event.preventDefault();
    });

    return {projectCard, message, notification, searchResults, csrfToken};
})();
