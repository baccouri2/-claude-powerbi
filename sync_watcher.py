"""
sync_watcher.py
Surveille les changements dans Power BI Desktop en temps réel
et met à jour automatiquement les données dans Claude
"""

import time, threading, os, psutil, hashlib, json
from datetime import datetime

# Cache des données précédentes
_last_data_hash = None
_last_data      = {}
_lock           = threading.Lock()
_callbacks      = []  # Fonctions appelées lors d'un changement


def _get_pbi_port():
    """Détecte le port Power BI Desktop actuel"""
    ws_root = os.path.expanduser(
        r"~\AppData\Local\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
    )
    if os.path.exists(ws_root):
        for ws in os.listdir(ws_root):
            for root, _, files in os.walk(os.path.join(ws_root, ws)):
                for fname in files:
                    if fname.lower() in ['msmdsrv.port', 'port']:
                        try:
                            return int(open(os.path.join(root, fname)).read().strip())
                        except:
                            pass

    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if ('msmdsrv' in proc.info['name'].lower() and
                    'Power BI' in (proc.info.get('exe') or '')):
                for c in proc.net_connections():
                    if c.status == 'LISTEN' and c.laddr.port != 2383:
                        return c.laddr.port
        except:
            pass
    return None


def _data_hash(data: dict) -> str:
    """Calcule un hash des données pour détecter les changements"""
    try:
        s = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(s.encode()).hexdigest()
    except:
        return ""


def _load_data():
    """Charge les données depuis Power BI Desktop"""
    try:
        from powerbi_direct import get_data_from_powerbi
        return get_data_from_powerbi()
    except Exception as e:
        print(f"[Sync] Erreur chargement : {e}")
        return None


def get_current_data() -> dict:
    """Retourne les données en cache (toujours à jour)"""
    with _lock:
        return _last_data.copy() if _last_data else {}


def on_change(callback):
    """Enregistre une fonction appelée lors d'un changement"""
    _callbacks.append(callback)


def _notify_change(old_data, new_data):
    """Notifie tous les callbacks d'un changement"""
    for cb in _callbacks:
        try:
            cb(old_data, new_data)
        except Exception as e:
            print(f"[Sync] Erreur callback : {e}")


def _watch_loop(interval: int = 10):
    """Boucle de surveillance — vérifie toutes les `interval` secondes"""
    global _last_data_hash, _last_data

    print(f"[Sync] Démarrage surveillance (intervalle: {interval}s)")

    while True:
        try:
            # Vérifier si Power BI est ouvert
            port = _get_pbi_port()
            if not port:
                time.sleep(interval)
                continue

            # Charger les nouvelles données
            new_data = _load_data()
            if not new_data:
                time.sleep(interval)
                continue

            new_hash = _data_hash(new_data)

            with _lock:
                if new_hash != _last_data_hash:
                    old_data       = _last_data.copy()
                    _last_data     = new_data
                    _last_data_hash = new_hash

                    timestamp = datetime.now().strftime("%H:%M:%S")
                    k = new_data.get("kpis", {})
                    print(f"[Sync {timestamp}] Changement détecté !")
                    print(f"  CA HT: {k.get('ca_ht',0):,.2f} DT | "
                          f"Cmd: {int(k.get('nb_commandes',0))} | "
                          f"Cli: {int(k.get('nb_clients',0))}")

                    # Notifier les callbacks
                    if old_data:
                        _notify_change(old_data, new_data)
                else:
                    pass  # Pas de changement

        except Exception as e:
            print(f"[Sync] Erreur surveillance : {e}")

        time.sleep(interval)


def start(interval: int = 10):
    """
    Démarre la surveillance en arrière-plan
    interval : secondes entre chaque vérification (défaut: 10s)
    """
    global _last_data, _last_data_hash

    # Charger les données initiales
    print("[Sync] Chargement initial...")
    data = _load_data()
    if data:
        with _lock:
            _last_data      = data
            _last_data_hash = _data_hash(data)
        k = data.get("kpis", {})
        print(f"[Sync] Données initiales chargées :")
        print(f"  CA HT: {k.get('ca_ht',0):,.2f} DT | "
              f"Cmd: {int(k.get('nb_commandes',0))} | "
              f"Cli: {int(k.get('nb_clients',0))}")
    else:
        print("[Sync] Impossible de charger les données initiales")

    # Démarrer la boucle en arrière-plan
    t = threading.Thread(target=_watch_loop, args=(interval,), daemon=True)
    t.start()
    print(f"[Sync] Surveillance active (toutes les {interval}s)")
    return t
