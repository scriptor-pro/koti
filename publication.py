# koti — suivi de rituels quotidiens
# Copyright (C) 2026 scriptor-pro
# SPDX-License-Identifier: GPL-3.0-or-later
"""Publication de koti.html sur bunny.net : envoi vers la storage zone, URL signée, purge du cache."""
import base64
import hashlib
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CLES_REQUISES = ("storage_endpoint", "storage_access_key", "pull_zone", "public_hostname",
                 "token_auth_security_key", "remote_filename", "token_validity_seconds")
MARQUEUR_EDGE_RULE = "koti: no-cache navigateur (auto)"


class ErreurPublication(Exception):
    pass


def charger_config(dossier):
    """La configuration bunny, ou None si .bunny_config.json est absent."""
    chemin = dossier / ".bunny_config.json"
    if not chemin.exists():
        return None
    try:
        config = json.loads(chemin.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ErreurPublication(f"{chemin} illisible : {exc.strerror or type(exc).__name__}.") from None
    except ValueError as exc:
        raise ErreurPublication(f"{chemin} illisible : {exc}") from None
    if not isinstance(config, dict):
        raise ErreurPublication(f"{chemin} : un objet JSON est attendu.")
    manquantes = [c for c in CLES_REQUISES if not config.get(c)]
    if manquantes:
        raise ErreurPublication(f"{chemin} : clés manquantes ou vides : {', '.join(manquantes)}.")
    try:
        int(config["token_validity_seconds"])
    except (TypeError, ValueError):
        raise ErreurPublication(f"{chemin} : token_validity_seconds doit être un nombre entier de secondes.") from None
    return config


def generer_url_signee(security_key, hostname, url_path, expires):
    hashable = f"{security_key}{url_path}{expires}"
    token = base64.b64encode(hashlib.md5(hashable.encode()).digest()).decode()
    token = token.replace("+", "-").replace("/", "_").replace("=", "")
    return f"https://{hostname}{url_path}?token={token}&expires={expires}"


def publier(dossier):
    config = charger_config(dossier)
    if config is None:
        print("(.bunny_config.json absent — publication ignorée)")
        return
    fichier = config["remote_filename"]
    try:
        resultat = subprocess.run(
            [
                "curl", "-s", "--max-time", "60", "-o", "/dev/null", "-w", "%{http_code}",
                "-X", "PUT",
                "-H", f"AccessKey: {config['storage_access_key']}",
                "-H", "Content-Type: text/html",
                "--data-binary", f"@{dossier / 'koti.html'}",
                f"{config['storage_endpoint']}/{fichier}",
            ],
            capture_output=True, text=True,
        )
    except OSError as exc:
        raise ErreurPublication(f"envoi vers bunny.net impossible : curl introuvable ou inutilisable ({exc.strerror or type(exc).__name__}).") from None
    code = resultat.stdout.strip()
    if code not in ("200", "201"):
        raise ErreurPublication(f"envoi vers bunny.net ({fichier}) : HTTP {code or 'aucune réponse'}.")
    validite = int(config["token_validity_seconds"])
    hote = config["public_hostname"]
    print(f"OK — {fichier} publié sur bunny.net.")
    print(f"URL signée (valide ~{validite // 86400} jours) :")
    print(generer_url_signee(config["token_auth_security_key"], hote, f"/{fichier}", int(time.time()) + validite))
    purger_cache(f"https://{hote}/{fichier}")


def _lire_cle_api():
    cle = os.environ.get("BUNNY_API_KEY")
    if cle:
        return cle
    fichier = Path.home() / ".config" / "koti" / "bunny.env"
    if not fichier.exists():
        return None
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne.startswith("export "):
            ligne = ligne[len("export "):]
        if ligne.startswith("BUNNY_API_KEY="):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _contexte_ssl():
    for ca in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
        if os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


def purger_cache(url):
    cle = _lire_cle_api()
    if not cle:
        print("Envoi effectué — purge CDN NON faite (ni BUNNY_API_KEY ni ~/.config/koti/bunny.env).", file=sys.stderr)
        return
    api = "https://api.bunny.net/purge?url=" + urllib.parse.quote(url, safe="") + "&async=false"
    requete = urllib.request.Request(api, method="POST", headers={"AccessKey": cle})
    try:
        with urllib.request.urlopen(requete, timeout=30, context=_contexte_ssl()) as reponse:
            code = reponse.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except urllib.error.URLError as exc:
        raise ErreurPublication(f"purge CDN : {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        raise ErreurPublication(f"purge CDN : {exc.strerror or type(exc).__name__}.") from None
    if not 200 <= code < 300:
        raise ErreurPublication(f"purge CDN : HTTP {code}.")
    print("OK — cache CDN purgé.")


def _api_bunny(methode, chemin, cle, corps=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(
        "https://api.bunny.net" + chemin, data=donnees, method=methode,
        headers={"AccessKey": cle, "Accept": "application/json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(requete, timeout=30, context=_contexte_ssl()) as reponse:
        brut = reponse.read()
        return reponse.status, (json.loads(brut) if brut else None)


def assurer_edge_rule(dossier):
    """Pose (une seule fois) l'Edge Rule « Cache-Control: no-cache » sur la page, côté navigateur."""
    config = charger_config(dossier)
    cle = _lire_cle_api()
    if config is None or not cle:
        print("Edge Rule ignorée (configuration ou clé d'API bunny absente).", file=sys.stderr)
        return
    try:
        _, zones = _api_bunny("GET", "/pullzone?page=0&perPage=1000", cle)
        elements = zones.get("Items") if isinstance(zones, dict) else zones
        identifiant = next((z.get("Id") for z in (elements or []) if z.get("Name") == config["pull_zone"]), None)
        if not identifiant:
            raise ErreurPublication(f"pull zone « {config['pull_zone']} » introuvable.")
        _, zone = _api_bunny("GET", f"/pullzone/{identifiant}", cle)
        if any(r.get("Description") == MARQUEUR_EDGE_RULE for r in (zone.get("EdgeRules") or [])):
            print("OK — Edge Rule déjà en place.")
            return
        regle = {
            "ActionType": 5,
            "ActionParameter1": "Cache-Control",
            "ActionParameter2": "no-cache",
            "Enabled": True,
            "Description": MARQUEUR_EDGE_RULE,
            "TriggerMatchingType": 0,
            "Triggers": [{"Type": 0, "PatternMatches": [f"*/{config['remote_filename']}*"],
                          "PatternMatchingType": 0, "Parameter1": ""}],
        }
        _api_bunny("POST", f"/pullzone/{identifiant}/edgerules/addOrUpdate", cle, regle)
        print("OK — Edge Rule posée (no-cache navigateur sur la page).")
    except urllib.error.HTTPError as exc:
        raise ErreurPublication(f"Edge Rule : HTTP {exc.code}.") from None
    except urllib.error.URLError as exc:
        raise ErreurPublication(f"Edge Rule : {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        raise ErreurPublication(f"Edge Rule : {exc.strerror or type(exc).__name__}.") from None
