/* app.js — claude_powerbi avec historique + onglets pages */

// ── État global ───────────────────────────────────────────
let H           = [];          // Historique conversation courante
let fw          = true;        // Premier message flag
let currentPage = 'all';       // Onglet actif
let allKpis     = {};          // KPIs chargés depuis Odoo

// Historique persistant de toutes les conversations
let conversations = [];        // [{id, title, page, history, messages}]
let currentConvId = null;

// ── Suggestions par page ──────────────────────────────────
const SUGGESTIONS = {
    all: [
        { icon: '📋', title: 'Résumé exécutif',   sub: 'Synthèse des 3 pages',         q: 'Résumé exécutif complet des 3 pages du rapport stage bi' },
        { icon: '🏆', title: 'Meilleur client',    sub: 'Analyse et importance',        q: 'Quel est le meilleur client et son importance stratégique ?' },
        { icon: '📊', title: 'Analyse marges',     sub: 'Rentabilité détaillée',        q: 'Analyse la marge brute et le taux de marge par client' },
        { icon: '⚠️', title: 'Risques',            sub: "Points d'attention",           q: 'Quels sont les risques et alertes dans mes données de vente ?' },
        { icon: '💡', title: 'Recommandations',    sub: 'Actions concrètes',            q: 'Donne 5 recommandations stratégiques pour améliorer les ventes' },
        { icon: '📅', title: 'Tendances',          sub: 'Évolution mensuelle',          q: 'Compare les ventes mois par mois et explique les tendances' },
        { icon: '📦', title: 'Top produits',       sub: 'Performance produits',         q: 'Analyse les top produits par CA et par quantité' },
        { icon: '🎯', title: 'Conversion',         sub: 'Optimisation devis',           q: 'Comment améliorer le taux de conversion des devis ?' },
    ],
    page1: [
        { icon: '📊', title: 'KPIs Vue Générale',  sub: 'CA, Marge, Conversion',        q: 'Analyse tous les KPIs de la page Vue Générale' },
        { icon: '📈', title: 'Évolution CA',       sub: 'Tendance mensuelle',           q: 'Comment évolue le CA mois par mois ?' },
        { icon: '👥', title: 'Répartition clients',sub: '% CA par client',              q: 'Analyse la répartition du CA par client' },
        { icon: '🗂️', title: 'CA par catégorie',  sub: 'Barres horizontales',          q: 'Quelle catégorie de produit génère le plus de CA ?' },
    ],
    page2: [
        { icon: '📋', title: 'KPIs Commerciale',  sub: 'CA, Marge, Taux Marge',        q: 'Analyse tous les KPIs de la page Analyse Commerciale' },
        { icon: '🎯', title: 'Taux conversion',   sub: '76% — comment améliorer ?',    q: 'Comment améliorer le taux de conversion de 76% ?' },
        { icon: '📦', title: 'Quantité vendue',   sub: 'Par mois',                     q: 'Analyse la quantité vendue par mois' },
        { icon: '👤', title: 'Clients',           sub: 'Performance commerciale',      q: 'Quels clients ont le meilleur potentiel commercial ?' },
    ],
    page3: [
        { icon: '📊', title: 'KPIs Produits',     sub: 'Prix moyen, distincts, qté',   q: 'Analyse les KPIs de la page Analyse Produits' },
        { icon: '🏅', title: 'Top 10 CA',         sub: 'Produits les plus rentables',  q: 'Quels sont les 10 produits qui génèrent le plus de CA ?' },
        { icon: '📦', title: 'Top 5 Quantité',    sub: 'Produits les plus vendus',     q: 'Quels sont les 5 produits les plus vendus en quantité ?' },
        { icon: '💰', title: 'Panier moyen',      sub: 'Par produit',                  q: 'Quels produits ont le panier moyen le plus élevé ?' },
    ],
};

// ── Initialisation ────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    loadKPIs();
    renderSuggestions();
    document.getElementById('inp').focus();
    // Synchronisation automatique toutes les 10 secondes
    setInterval(() => loadKPIs(false), 10000);
});

// ── KPIs depuis Odoo ──────────────────────────────────────
async function loadKPIs(verbose = true) {
    try {
        const res = await fetch('/api/kpis');
        const k   = await res.json();
        if (k.error) throw new Error(k.error);
        allKpis = k;

        document.getElementById('kpiList').innerHTML = `
            <b>CA HT</b>           : ${n(k.ca_ht)} DT<br>
            <b>Marge Brute</b>     : ${n(k.marge_brute)} DT (${p(k.taux_marge)})<br>
            <b>Taux Conversion</b> : ${p(k.taux_conversion)}<br>
            <b>Commandes</b>       : ${k.nb_commandes}<br>
            <b>Clients</b>         : ${k.nb_clients}<br>
            <b>Qté Vendue</b>      : ${k.qte_vendue}<br>
            <b>Produits</b>        : ${k.nb_distincts} distincts<br>
            <b>Prix Moyen</b>      : ${n(k.prix_moyen)} DT<br>
            <b>Période</b>         : ${k.date_debut} → ${k.date_fin}<br>
            <span style="color:#666;font-size:10px">Sync: ${k.last_sync || '--'}</span>
        `;

        // Mettre à jour l'heure de sync dans le topbar
        const st = document.getElementById('syncTime');
        if (st) st.textContent = `Sync: ${k.last_sync || '--'}`;

        setDot(true);
        updatePageData();
    } catch (e) {
        if (verbose) {
            document.getElementById('kpiList').innerHTML =
                `<span style="color:#E74C3C">Erreur: ${e.message}</span>`;
        }
        setDot(false);
    }
}

async function doRefresh() {
    const b = document.querySelector('.refresh');
    b.textContent = '⟳ ...'; b.disabled = true;
    await loadKPIs();
    b.textContent = '✅';
    setTimeout(() => { b.textContent = '⟳ Actualiser'; b.disabled = false; }, 2000);
}

function setDot(ok) {
    const d = document.getElementById('dot');
    d.className = 'dot' + (ok ? '' : ' err');
}

// ── Onglets pages ─────────────────────────────────────────
function switchPage(page) {
    currentPage = page;
    // Mettre à jour onglets
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + page).classList.add('active');
    // Mettre à jour suggestions
    renderSuggestions();
    // Mettre à jour données affichées
    updatePageData();
    // Mettre à jour placeholder
    const placeholders = {
        all:   'Posez une question sur les 3 pages...',
        page1: 'Posez une question sur Vue Générale...',
        page2: 'Posez une question sur Analyse Commerciale...',
        page3: 'Posez une question sur Analyse Produits...',
    };
    document.getElementById('inp').placeholder = placeholders[page];
}

function updatePageData() {
    const k  = allKpis;
    const pd = document.getElementById('pageData');
    const pi = document.getElementById('pageDataInner');
    if (!k.ca_ht) { pd.style.display = 'none'; return; }

    pd.style.display = '';
    let html = '';

    // Toutes les pages — tous les KPIs
    if (currentPage === 'all') {
        html = `
            <div class="pd-card"><div class="pd-label">CA HT</div><div class="pd-value">${n(k.ca_ht)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Marge Brute</div><div class="pd-value">${n(k.marge_brute)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Taux Marge</div><div class="pd-value">${p(k.taux_marge)}</div></div>
            <div class="pd-card"><div class="pd-label">Taux Conversion</div><div class="pd-value">${p(k.taux_conversion)}</div></div>
            <div class="pd-card"><div class="pd-label">Nb Commandes</div><div class="pd-value">${k.nb_commandes}</div></div>
            <div class="pd-card"><div class="pd-label">Nb Clients</div><div class="pd-value">${k.nb_clients}</div></div>
            <div class="pd-card"><div class="pd-label">Panier Moyen</div><div class="pd-value">${n(k.panier_moyen)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Qté Vendue</div><div class="pd-value">${k.qte_vendue}</div></div>
            <div class="pd-card"><div class="pd-label">Prix Moyen Produits</div><div class="pd-value">${n(k.prix_moyen)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Produits Distincts</div><div class="pd-value">${k.nb_distincts}</div></div>
        `;
    }

    // PAGE 1 — VUE GÉNÉRALE
    // Cartes Power BI : CA HT | Panier Moyen | Marge Brute | Taux Conversion | Nb Commandes | Nb Clients
    if (currentPage === 'page1') {
        html = `
            <div class="pd-card"><div class="pd-label">CA HT</div><div class="pd-value">${n(k.ca_ht)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Panier Moyen</div><div class="pd-value">${n(k.panier_moyen)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Marge Brute</div><div class="pd-value">${n(k.marge_brute)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Taux Conversion</div><div class="pd-value">${p(k.taux_conversion)}</div></div>
            <div class="pd-card"><div class="pd-label">Nombre Commandes</div><div class="pd-value">${k.nb_commandes}</div></div>
            <div class="pd-card"><div class="pd-label">Nombre Clients</div><div class="pd-value">${k.nb_clients}</div></div>
        `;
    }

    // PAGE 2 — ANALYSE COMMERCIALE
    // Cartes Power BI : CA HT | Marge Brute | Taux de Marge | Nb Commandes | Nb Clients | Qté Vendue
    if (currentPage === 'page2') {
        html = `
            <div class="pd-card"><div class="pd-label">CA HT</div><div class="pd-value">${n(k.ca_ht)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Marge Brute</div><div class="pd-value">${n(k.marge_brute)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Taux de Marge</div><div class="pd-value">${p(k.taux_marge)}</div></div>
            <div class="pd-card"><div class="pd-label">Nombre Commandes</div><div class="pd-value">${k.nb_commandes}</div></div>
            <div class="pd-card"><div class="pd-label">Nombre Clients</div><div class="pd-value">${k.nb_clients}</div></div>
            <div class="pd-card"><div class="pd-label">Quantité Vendue</div><div class="pd-value">${k.qte_vendue}</div></div>
        `;
    }

    // PAGE 3 — ANALYSE PRODUITS
    // Cartes Power BI : Prix Moyen Produits | Quantité Vendue | Quantité Top Produits | NB Produits Non Vendues | NB Produits Distincts
    if (currentPage === 'page3') {
        html = `
            <div class="pd-card"><div class="pd-label">Prix Moyen Produits</div><div class="pd-value">${n(k.prix_moyen)} DT</div></div>
            <div class="pd-card"><div class="pd-label">Quantité Vendue</div><div class="pd-value">${k.qte_vendue}</div></div>
            <div class="pd-card"><div class="pd-label">Quantité Top Produits</div><div class="pd-value">${k.qte_top_produit}</div></div>
            <div class="pd-card"><div class="pd-label">NB Produits Non Vendues</div><div class="pd-value">${k.nb_non_vendus}</div></div>
            <div class="pd-card"><div class="pd-label">NB Produits Distincts</div><div class="pd-value">${k.nb_distincts}</div></div>
        `;
    }

    pi.innerHTML = html;
}

// ── Suggestions ───────────────────────────────────────────
function renderSuggestions() {
    const cards = SUGGESTIONS[currentPage] || SUGGESTIONS.all;
    const container = document.getElementById('welcomeCards');
    container.innerHTML = '';
    cards.forEach(c => {
        const div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `<h4>${c.icon} ${c.title}</h4><p>${c.sub}</p>`;
        div.addEventListener('click', () => askCard(c.q));
        container.appendChild(div);
    });
}

// ── Formatage ─────────────────────────────────────────────
function n(v) {
    return v ? parseFloat(v).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';
}
function p(v) { return v ? parseFloat(v).toFixed(2) + '%' : '0%'; }
function resizeTA(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px'; }
function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); } }
function askCard(q) { document.getElementById('inp').value = q; doSend(); }

// ── Gestion conversations ─────────────────────────────────
function newConv() {
    // Sauvegarder conversation courante si elle a des messages
    if (H.length > 0) saveCurrentConv();

    H   = [];
    fw  = true;
    currentConvId = null;

    // Nettoyer zone de chat
    document.querySelectorAll('.grp').forEach(g => g.remove());
    document.getElementById('welcome').style.display = '';
    document.getElementById('inp').focus();
}

function saveCurrentConv() {
    if (H.length === 0) return;

    const firstQ = H.find(m => m.role === 'user');
    const title  = firstQ ? firstQ.content.substring(0, 35) + (firstQ.content.length > 35 ? '...' : '') : 'Conversation';

    if (currentConvId) {
        // Mettre à jour existante
        const idx = conversations.findIndex(c => c.id === currentConvId);
        if (idx !== -1) {
            conversations[idx].history  = [...H];
            conversations[idx].messages = getMessagesHTML();
        }
    } else {
        // Nouvelle conversation
        currentConvId = Date.now().toString();
        conversations.unshift({
            id      : currentConvId,
            title   : title,
            page    : currentPage,
            history : [...H],
            messages: getMessagesHTML()
        });
    }
    renderConvList();
}

function getMessagesHTML() {
    return document.getElementById('ci').innerHTML;
}

function renderConvList() {
    const list = document.getElementById('convList');
    if (conversations.length === 0) {
        list.innerHTML = '<div class="conv-empty">Aucune conversation</div>';
        return;
    }
    list.innerHTML = conversations.map(c => `
        <div class="conv-item ${c.id === currentConvId ? 'active' : ''}"
             onclick="loadConv('${c.id}')">
            <span class="conv-title" title="${c.title}">${c.title}</span>
            <button class="conv-del" onclick="delConv(event,'${c.id}')" title="Supprimer">✕</button>
        </div>
    `).join('');
}

function loadConv(id) {
    // Sauvegarder courante
    if (H.length > 0) saveCurrentConv();

    const conv = conversations.find(c => c.id === id);
    if (!conv) return;

    currentConvId = id;
    H  = [...conv.history];
    fw = false;

    document.getElementById('welcome').style.display = 'none';
    document.getElementById('ci').innerHTML = conv.messages;
    scroll();

    // Switcher sur l'onglet de la conversation
    if (conv.page) switchPage(conv.page);

    renderConvList();
}

function delConv(e, id) {
    e.stopPropagation();
    conversations = conversations.filter(c => c.id !== id);
    if (currentConvId === id) {
        H = []; fw = true; currentConvId = null;
        document.querySelectorAll('.grp').forEach(g => g.remove());
        document.getElementById('welcome').style.display = '';
    }
    renderConvList();
}

// ── Affichage messages ────────────────────────────────────
function hideWelcome() {
    if (fw) { document.getElementById('welcome').style.display = 'none'; fw = false; }
}

function esc(t) {
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmt(text) {
    return esc(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g,     '<em>$1</em>')
        .replace(/^#{1,3} (.+)$/gm,'<strong>$1</strong>')
        .replace(/\n\n+/g,         '</p><p>')
        .replace(/\n/g,            '<br>');
}

function addUser(t) {
    hideWelcome();
    const ci = document.getElementById('ci');
    const g  = document.createElement('div');
    g.className = 'grp';
    g.innerHTML = `
        <div class="sender u">Vous</div>
        <div class="row u">
            <div class="bub">${esc(t)}</div>
            <div class="av u">V</div>
        </div>`;
    ci.appendChild(g);
    scroll();
}

function addClaude(t) {
    const ci = document.getElementById('ci');
    const g  = document.createElement('div');
    g.className = 'grp';
    g.innerHTML = `
        <div class="sender">Claude</div>
        <div class="row c">
            <div class="av c">C</div>
            <div class="bub"><p>${fmt(t)}</p></div>
        </div>
        <div class="acts">
            <button class="act" onclick="cpMsg(this)">📋 Copier</button>
            <button class="act" onclick="this.textContent='👍'">👍</button>
            <button class="act" onclick="this.textContent='👎'">👎</button>
        </div>`;
    ci.appendChild(g);
    scroll();
}

function showTyping() {
    const ci = document.getElementById('ci');
    const d  = document.createElement('div');
    d.id = 'ty'; d.className = 'typing-row';
    d.innerHTML = `
        <div class="av c">C</div>
        <div class="dots"><span></span><span></span><span></span></div>`;
    ci.appendChild(d);
    scroll();
}
function hideTyping() { const t = document.getElementById('ty'); if (t) t.remove(); }
function scroll() { const c = document.getElementById('chat'); c.scrollTop = c.scrollHeight; }

function cpMsg(btn) {
    const txt = btn.closest('.grp').querySelector('.bub').innerText;
    navigator.clipboard.writeText(txt);
    btn.textContent = '✅ Copié';
    setTimeout(() => btn.textContent = '📋 Copier', 2000);
}

// ── Envoi — conversation continue ────────────────────────
async function doSend() {
    const inp = document.getElementById('inp');
    const sb  = document.getElementById('sb');
    const q   = inp.value.trim();
    if (!q || sb.disabled) return;

    inp.value = ''; inp.style.height = 'auto'; sb.disabled = true;
    addUser(q);
    showTyping();

    // Envoyer avec l'historique complet
    try {
        const res = await fetch('/api/chat', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({
                question  : q,
                historique: H,          // Tout l'historique des échanges précédents
                page      : currentPage // Page active pour contextualiser
            })
        });
        const data = await res.json();
        hideTyping();
        addClaude(data.response);

        // Ajouter les deux messages à l'historique APRÈS la réponse
        H.push({ role: 'user',      content: q });
        H.push({ role: 'assistant', content: data.response });

        // Sauvegarder automatiquement dans l'historique
        saveCurrentConv();

    } catch (e) {
        hideTyping();
        addClaude('❌ Erreur de connexion. Vérifiez que le serveur est actif.');
    }

    sb.disabled = false;
    inp.focus();
}
