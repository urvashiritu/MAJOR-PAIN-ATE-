/* Global search shared by the SPA shell and Dataset Analysis. */
(function () {
    'use strict';

    function esc(value) {
        const node = document.createElement('div');
        node.textContent = value == null ? '' : String(value);
        return node.innerHTML;
    }

    function analystBase() {
        return location.pathname.indexOf('/analyst/dataset') === 0 ? '/analyst' : '';
    }

    function goTo(path) {
        location.href = analystBase() + path;
    }

    function initGlobalSearch() {
        const input = document.getElementById('global-search');
        const overlay = document.getElementById('search-overlay');
        const modalInput = document.getElementById('search-modal-input');
        const results = document.getElementById('search-results');
        if (!input || !overlay || !modalInput || !results) return;

        let timer = null;
        let lastFocused = null;

        function openSearch() {
            if (overlay.classList.contains('open')) return;
            lastFocused = document.activeElement;
            overlay.classList.add('open');
            overlay.setAttribute('aria-hidden', 'false');
            setTimeout(function () { modalInput.focus(); }, 60);
        }

        function closeSearch() {
            if (!overlay.classList.contains('open')) return;
            overlay.classList.remove('open');
            overlay.setAttribute('aria-hidden', 'true');
            modalInput.value = '';
            results.innerHTML = '<div class="search-result-group">Type to search</div>';
            if (lastFocused && lastFocused.focus) lastFocused.focus();
        }

        input.addEventListener('focus', openSearch);
        input.addEventListener('click', openSearch);
        overlay.addEventListener('click', function (event) {
            if (event.target === overlay) closeSearch();
        });

        document.addEventListener('keydown', function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                openSearch();
            }
            if (event.key === 'Escape') closeSearch();
        });

        modalInput.addEventListener('input', function () {
            clearTimeout(timer);
            const q = modalInput.value.trim();
            if (!q) {
                results.innerHTML = '<div class="search-result-group">Type to search</div>';
                return;
            }
            timer = setTimeout(async function () {
                try {
                    const data = await API.search(q);
                    let html = '';
                    if (data.users && data.users.length) {
                        html += '<div class="search-result-group">Users (' + data.users.length + ')</div>';
                        data.users.forEach(function (user) {
                            html += '<button type="button" class="search-result-item" data-go="#/users">' +
                                '<span class="mono">' + esc(user.name || user.user_id) + '</span>' +
                                '<span class="text-faint"> ' + esc(user.persona) + ' · ' +
                                user.live_events + ' events · max ' + formatScore(user.max_score) +
                                '</span></button>';
                        });
                    }
                    if (data.events && data.events.length) {
                        html += '<div class="search-result-group">Events (' + data.events.length + ')</div>';
                        data.events.slice(0, 10).forEach(function (event) {
                            html += '<div class="search-result-item is-static">' +
                                '<span class="mono">' + esc(event.ts) + '</span> ' +
                                esc(event.name || event.user_id) +
                                '<span class="text-faint"> ' + esc(event.src_computer) + ' → ' +
                                esc(event.dst_computer) + '</span> ' +
                                '<span class="mono">' + formatScore(event.combined_score) + '</span> ' +
                                '<span class="stamp stamp-' +
                                (event.decision === 'block' ? 'critical' : event.decision === 'flag' ? 'medium' : 'low') +
                                '">' + esc(event.decision) + '</span></div>';
                        });
                    }
                    if (data.alerts && data.alerts.length) {
                        html += '<div class="search-result-group">Alerts (' + data.alerts.length + ')</div>';
                        data.alerts.slice(0, 10).forEach(function (alert) {
                            html += '<button type="button" class="search-result-item" data-go="#/alerts">' +
                                '<span class="mono">' + esc(alert.timestamp) + '</span> ' +
                                esc(alert.name || alert.user_id) +
                                '<span class="text-faint"> ' + esc(alert.reasons) + '</span></button>';
                        });
                    }
                    if (!html) {
                        html = '<div class="search-result-group">No results for "' + esc(q) + '"</div>';
                    }
                    results.innerHTML = html;
                } catch (error) {
                    results.innerHTML = '<div class="search-result-group">Search failed</div>';
                }
            }, 180);
        });

        results.addEventListener('click', function (event) {
            const target = event.target.closest('[data-go]');
            if (!target) return;
            closeSearch();
            goTo(target.dataset.go);
        });
    }

    window.initGlobalSearch = initGlobalSearch;
})();
