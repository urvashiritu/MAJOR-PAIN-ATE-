/* API fetch wrappers — live + dataset + SSE */
const API = {
    async dashboard() {
        const res = await fetch('/api/dashboard');
        if (!res.ok) throw new Error(`dashboard: ${res.status}`);
        return res.json();
    },

    async datasetDashboard() {
        const res = await fetch('/api/dataset/dashboard');
        if (!res.ok) throw new Error(`dataset/dashboard: ${res.status}`);
        return res.json();
    },

    async alerts() {
        const res = await fetch('/api/alerts');
        if (!res.ok) throw new Error(`alerts: ${res.status}`);
        return res.json();
    },

    async datasetAlerts() {
        const res = await fetch('/api/dataset/alerts');
        if (!res.ok) throw new Error(`dataset/alerts: ${res.status}`);
        return res.json();
    },

    async investigation(id) {
        const res = await fetch(`/api/investigation/${id}`);
        if (!res.ok) throw new Error(`investigation: ${res.status}`);
        return res.json();
    },

    async users() {
        const res = await fetch('/api/users');
        if (!res.ok) throw new Error(`users: ${res.status}`);
        return res.json();
    },

    async stats() {
        const res = await fetch('/api/stats');
        if (!res.ok) throw new Error(`stats: ${res.status}`);
        return res.json();
    },

    async ackAlert(id) {
        const res = await fetch(`/api/alerts/${id}/ack`, { method: 'POST' });
        if (!res.ok) throw new Error(`ack: ${res.status}`);
        return res.json();
    },

    async reset() {
        const res = await fetch('/api/reset', { method: 'POST' });
        if (!res.ok) throw new Error(`reset: ${res.status}`);
        return res.json();
    },

    async devLogin(username) {
        const res = await fetch('/dev/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
        if (!res.ok) throw new Error(`devLogin: ${res.status}`);
        return res.json();
    },

    async userProfile(userId) {
        const res = await fetch(`/api/user_profile/${encodeURIComponent(userId)}`);
        if (!res.ok) throw new Error(`userProfile: ${res.status}`);
        return res.json();
    },

    async health() {
        const res = await fetch('/api/health');
        if (!res.ok) throw new Error(`health: ${res.status}`);
        return res.json();
    },

    connectSSE(callbacks) {
        const es = new EventSource('/events/stream');
        es.addEventListener('score', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (callbacks.onScore) callbacks.onScore(data);
            } catch (err) { /* parse error */ }
        });
        es.onerror = () => {
            if (callbacks.onError) callbacks.onError();
            es.close();
            setTimeout(() => API.connectSSE(callbacks), 3000);
        };
        return es;
    }
};
