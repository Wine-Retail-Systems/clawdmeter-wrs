#!/bin/bash
# Ermittelt und prueft das WRS-Gateway-Label (Header x-bf-lh-repo) fuer das
# aktuelle Repository.
#
#   set-repo-header.sh           -> "x-bf-lh-repo: jacques/foo"  (Headerzeile)
#   set-repo-header.sh --label   -> "jacques/foo"                (nur der Wert)
#   set-repo-header.sh --check   -> menschenlesbarer Statusbericht, Exit 1 nur bei
#                                   fehlendem/abweichendem Label
#   set-repo-header.sh --hook    -> SessionStart-JSON mit Statusmeldung, immer Exit 0
#
# Drei Faelle fuer das Label:
#   Git-Repo mit origin   -> <gruppe>/<repo>   (aus der Remote-URL)
#   Git-Repo ohne origin  -> local/<repo-name> (Name des Repo-Wurzelverzeichnisses)
#   kein Git-Repo         -> dir/<ordner-name> (Name des aktuellen Verzeichnisses)
# Die Praefixe halten die drei Faelle in der Gateway-Auswertung unterscheidbar.
#
# WARUM 'x-bf-lh-repo': Bifrost protokolliert Header nicht von sich aus.
# Automatisch in die Log-Metadaten uebernommen wird nur, was den Praefix
# 'x-bf-lh-' traegt; der Praefix faellt dabei weg, der Rest wird zum
# Metadaten-Schluessel ('repo'). Der frueher verwendete Header 'x-bf-label'
# liegt dagegen in Bifrosts eigenem Steuer-Namensraum, ist dort keine Funktion
# und wurde verworfen - die Kostenzuordnung ueber Labels blieb deshalb von Juli
# bis September 2026 durchgehend leer. Den Namen nicht wieder aendern.
#
# WICHTIG: Ein Hook kann keine Env-Variablen der Session setzen. Gesetzt wird
# der Header ueber "env" in der eingecheckten .claude/settings.json des Projekts
# (siehe CLAUDE.md, Abschnitt "LLM-Gateway - Label-Pflicht"). Dieses Skript
# liefert den Wert und prueft, ob er tatsaechlich ankommt.
#
# Verbindlich ist allein das Label. Die Gateway-Anbindung selbst — Base-URL
# (ANTHROPIC_BASE_URL) und Key (ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY) — ist
# optional: fehlt sie, meldet das Skript einen Hinweis und keinen Fehler.

set -u

# Host des LLM-Gateways. Nur zum Erkennen, ob die Session ueberhaupt darueber
# laeuft — ueberschreibbar, falls ein Projekt an einem anderen Gateway haengt.
GW_HOST="${WRS_GW_HOST:-llm-gw.wineretailsystems.cloud}"

# Auf Zeichen beschraenken, die in einem HTTP-Header-Wert unbedenklich sind.
# Unerlaubte Zeichen werden ersetzt, nicht geloescht: aus "Meine Ablage" wird
# "Meine-Ablage" statt "MeineAblage". Umlaute vorher transliterieren, sonst
# zerfaellt jedes Mehrbyte-Zeichen in mehrere Ersatzzeichen.
sanitize() {
  printf '%s' "$1" \
    | sed 's/ä/ae/g; s/ö/oe/g; s/ü/ue/g; s/Ä/Ae/g; s/Ö/Oe/g; s/Ü/Ue/g; s/ß/ss/g' \
    | tr -c 'A-Za-z0-9._/-' '-' \
    | tr -s '-' \
    | sed -E 's|-*/-*|/|g; s|^-+||; s|-+$||'
}

# Basisname eines Pfades, mit Rueckfalloption fuer "/".
base_of() {
  local b
  b=$(basename "$1")
  [ -n "$b" ] && [ "$b" != "/" ] && printf '%s' "$b" || printf 'root'
}

repo_label() {
  local root remote pfad

  if root=$(git rev-parse --show-toplevel 2>/dev/null) && [ -n "$root" ]; then
    remote=$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)
    if [ -n "$remote" ]; then
      # https://gitlab.example.de/gruppe/foo.git        -> gruppe/foo
      # ssh://git@gitlab.example.de:2222/gruppe/foo.git -> gruppe/foo
      # git@gitlab.example.de:gruppe/foo.git            -> gruppe/foo
      pfad=$(printf '%s' "$remote" | sed -E 's|^[a-zA-Z]+://[^/]+/||; s|^[^@/]*@[^:/]+:||; s|/+$||; s|\.git$||')
    else
      pfad="local/$(base_of "$root")"
    fi
  else
    pfad="dir/$(base_of "$PWD")"
  fi

  pfad=$(sanitize "$pfad")
  [ -n "$pfad" ] || return 1
  printf '%s' "$pfad"
}

# Das in dieser Session tatsaechlich gesetzte Label aus ANTHROPIC_CUSTOM_HEADERS
# herausziehen (leer, wenn kein x-bf-lh-repo enthalten ist).
aktives_label() {
  # Header-Name case-insensitiv, ohne den Labelwert selbst umzuschreiben.
  # grep arbeitet zeilenweise, mehrere Header sind per Newline getrennt.
  printf '%s\n' "${ANTHROPIC_CUSTOM_HEADERS:-}" \
    | grep -oE '[xX]-[bB][fF]-[lL][hH]-[rR][eE][pP][oO][[:space:]]*:[[:space:]]*[^[:space:]]+' \
    | head -n1 \
    | sed -E 's/^[^:]*:[[:space:]]*//'
}

# Denselben Griff fuer den abgeloesten Header 'x-bf-label: repo=...'. Er wird
# nur erkannt, um eine praezise Meldung geben zu koennen: Ein Projekt, das noch
# darauf steht, sieht sonst bloss "Label fehlt" und sucht an der falschen
# Stelle.
altes_label() {
  printf '%s\n' "${ANTHROPIC_CUSTOM_HEADERS:-}" \
    | grep -oE '[xX]-[bB][fF]-[lL][aA][bB][eE][lL][[:space:]]*:[[:space:]]*repo=[^[:space:]]+' \
    | head -n1 \
    | sed -E 's/^.*repo=//'
}

# Fuer JSON-Ausgabe: Backslash/Anfuehrungszeichen escapen, Zeilenumbrueche zu \n.
json_escape() {
  printf '%s' "$1" \
    | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
    | awk 'BEGIN{ORS=""} {if (NR>1) printf "\\n"; print}'
}

# Prueft das Label (verbindlich) und die Gateway-Anbindung (optional).
# Setzt STATUS_MELDUNG (Text fuer Bericht/Hook) und STATUS_HINWEIS (optionale
# Beobachtungen, kein Fehler) und gibt 0 (Label in Ordnung) oder 1 (Label fehlt
# oder weicht ab) zurueck.
pruefe() {
  local erwartet="$1" aktiv alt basis probleme="" hinweise=""
  aktiv=$(aktives_label)
  alt=$(altes_label)

  if [ -z "$aktiv" ] && [ -n "$alt" ]; then
    probleme="Veraltetes Gateway-Label: gesetzt ist 'x-bf-label: repo=$alt'. Diesen Header protokolliert das Gateway nicht — er wird verworfen, und die Kostenzuordnung ueber Labels bleibt leer. Erwartet wird 'x-bf-lh-repo: $erwartet'. /wrs-agent-rules erneut ausfuehren."
  elif [ -z "$aktiv" ]; then
    probleme="Gateway-Label fehlt (erwartet: x-bf-lh-repo: $erwartet). ANTHROPIC_CUSTOM_HEADERS ist nicht gesetzt oder enthaelt kein x-bf-lh-repo — pruefe den env-Block in .claude/settings.json bzw. fuehre /wrs-agent-rules erneut aus."
  elif [ "$aktiv" != "$erwartet" ]; then
    probleme="Gateway-Label weicht ab: gesetzt $aktiv, erwartet $erwartet. Wurde das Repository umbenannt, verschoben oder eine fremde .claude/settings.json uebernommen? /wrs-agent-rules erneut ausfuehren."
  fi

  # Base-URL und Key sind optional: laeuft ein Projekt nicht ueber das Gateway,
  # ist das kein Konfigurationsfehler. Das Label bleibt dann ohne Wirkung, wird
  # aber weiter mitgefuehrt — es kostet nichts und greift, sobald die Session
  # doch ueber das Gateway laeuft. Deshalb nur Hinweise, keine Probleme.
  basis="${ANTHROPIC_BASE_URL:-}"
  if [ -z "$basis" ]; then
    hinweise="ANTHROPIC_BASE_URL ist nicht gesetzt — diese Session laeuft nicht ueber das LLM-Gateway, das Label wird also nirgends ausgewertet. Zulaessig: die Gateway-Anbindung ist optional."
  elif ! printf '%s' "$basis" | grep -qF "$GW_HOST"; then
    hinweise="ANTHROPIC_BASE_URL zeigt nicht auf $GW_HOST (aktuell: $basis) — das Label wird dort nicht ausgewertet. Zulaessig, wenn das Projekt bewusst an einem anderen Endpunkt haengt (erwarteter Host ueber WRS_GW_HOST anpassbar)."
  elif [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    hinweise="Kein Gateway-Key in der Umgebung gefunden (ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY). Laeuft die Session trotzdem, kommt er aus einer anderen Quelle (z. B. apiKeyHelper) — sonst lokal setzen, niemals einchecken."
  fi

  STATUS_HINWEIS="$hinweise"
  if [ -n "$probleme" ]; then
    STATUS_MELDUNG="$probleme${hinweise:+
$hinweise}"
    return 1
  fi
  STATUS_MELDUNG="Gateway-Label aktiv: x-bf-lh-repo: $erwartet"
  return 0
}

label=$(repo_label) || exit 0

case "${1:-}" in
  --label)
    printf '%s\n' "$label"
    ;;
  --check)
    if pruefe "$label"; then
      printf 'OK: %s\n' "$STATUS_MELDUNG"
      [ -n "$STATUS_HINWEIS" ] && printf 'HINWEIS:\n%s\n' "$STATUS_HINWEIS"
      exit 0
    fi
    printf 'PROBLEM:\n%s\n' "$STATUS_MELDUNG" >&2
    exit 1
    ;;
  --hook)
    if pruefe "$label"; then
      # Label sitzt: Hinweise zur optionalen Gateway-Anbindung mitgeben, aber
      # die Session nicht damit aufhalten.
      meldung="$STATUS_MELDUNG${STATUS_HINWEIS:+
$STATUS_HINWEIS}"
      printf '{"systemMessage":"%s","suppressOutput":true}\n' "$(json_escape "$meldung")"
    else
      printf '{"systemMessage":"%s","suppressOutput":false}\n' "$(json_escape "$STATUS_MELDUNG")"
    fi
    ;;
  *)
    printf 'x-bf-lh-repo: %s\n' "$label"
    ;;
esac
