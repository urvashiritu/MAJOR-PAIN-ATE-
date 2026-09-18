/* API fetch wrappers */
const API = {
    async dashboard() {
        const res = await fetch('/api/dashboard');
        if (!res.ok) throw new Error(`dashboard: ${res.status}`);
        return res.json();
    },

    async alerts() {
        const res = await fetch('/api/alerts');
        if (!res.ok) throw new Error(`alerts: ${res.status}`);
        return res.json();
    },

    async liveEvents() {
        const res = await fetch('/api/live_events');
        if (!res.ok) throw new Error(`live_events: ${res.status}`);
        return res.json();
    },

    async health() {
        const res = await fetch('/api/health');
        if (!res.ok) throw new Error(`health: ${res.status}`);
        return res.json();
    }
};
