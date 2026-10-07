---
name: Clawdmeter
description: Companion-App und Geräte-UI eines LLM-Nutzungsmonitors für den Schreibtisch
colors:
  bordeaux: "#7c2d3a"
  bordeaux-deep: "#682530"
  bordeaux-night: "#d05a6c"
  bordeaux-night-hover: "#de7080"
  cellar-shadow: "#2a0e14"
  linen: "#f7f5f2"
  paper: "#ffffff"
  linen-subtle: "#f0ede8"
  ink: "#1a1614"
  ink-muted: "#6b6259"
  ink-subtle: "#9a9088"
  cellar: "#15110f"
  cellar-elev: "#1e1a17"
  cellar-subtle: "#221d1a"
  chalk: "#f4efea"
  chalk-muted: "#b3aaa1"
  chalk-subtle: "#7d736a"
  status-ok: "#15803d"
  status-warn: "#b45309"
  status-danger: "#b91c1c"
  device-black: "#000000"
  device-panel: "#1f1f1e"
  device-text: "#faf9f5"
  device-dim: "#b0aea5"
  device-terracotta: "#d97757"
  device-bordeaux: "#7a2e36"
typography:
  display:
    fontFamily: "Fraunces, SF Pro Display, Segoe UI Variable Display, Georgia, serif"
    fontSize: "32px"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.02em"
    fontVariation: "'opsz' 60, 'SOFT' 30"
  headline:
    fontFamily: "Fraunces, SF Pro Display, Segoe UI Variable Display, Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontVariation: "'opsz' 36, 'SOFT' 30"
  title:
    fontFamily: "Fraunces, SF Pro Display, Segoe UI Variable Display, Georgia, serif"
    fontSize: "18px"
    fontWeight: 500
    letterSpacing: "-0.005em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  control:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.1em"
  mono:
    fontFamily: "ui-monospace, SF Mono, Cascadia Code, Cascadia Mono, JetBrains Mono, Menlo, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "7": "32px"
components:
  button-primary:
    backgroundColor: "{colors.bordeaux}"
    textColor: "{colors.paper}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.bordeaux-deep}"
  button-ghost:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
  button-ghost-hover:
    backgroundColor: "{colors.linen-subtle}"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "{spacing.5}"
  action-card-primary:
    backgroundColor: "{colors.bordeaux}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "{spacing.5}"
  input:
    backgroundColor: "{colors.linen}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "8px 11px"
  option:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  statuschip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.pill}"
    padding: "6px 12px 6px 10px"
---

# Design System: Clawdmeter

## Overview

**Creative North Star: "Das Sommelier-Werkzeug"**

Clawdmeter serviert, es präsentiert nicht. Die Companion-App ist ein ruhiges, präzises Werkzeug auf warmem Leinen, mit genau einem Akzent: Bordeaux. Sie nutzt die Systemschrift und die native Titelleiste des Betriebssystems, damit sie sich wie ein Mac- oder Windows-Programm anfühlt. Nur Überschriften tragen eine weiche Serife (Fraunces), so wie ein Etikett den Inhalt einer Flasche benennt, ohne ihn zu übertönen.

Die Dichte ist kompakt-desktop: 14px Grundschrift, 13px Bedienelemente, Karten mit 20px Innenabstand in einer zentrierten Spalte von höchstens 980px. Tiefe ist leicht erhaben: Karten liegen mit einem Hauchschatten auf dem Grund, heben sich beim Hover um 2px, und nur die primäre Aktion bekommt einen Bordeaux-Schimmer. Hell und Dunkel folgen der Systemeinstellung; im Dunkeln wird aus Leinen ein Kellergewölbe (`cellar`), und Bordeaux hellt sich auf, damit es lesbar bleibt.

Die zweite Oberfläche ist das Gerät selbst: ein AMOLED-Display auf echtem Schwarz. Es teilt sich mit der App die Rollenverteilung der Schriften (Serife für Titel, Grotesk für UI, Mono für Zahlen) und, in der Wine Edition, den Bordeaux-Akzent. Standard-Firmware-Builds tragen stattdessen Terra-Cotta.

**Key Characteristics:**
- Ein einziger warmer Akzent (Bordeaux) auf warm getönten Neutraltönen, nie kaltes Grau.
- Native OS-Chrome und Systemschrift für Bedienung; Fraunces nur für Überschriften und Marke.
- Ruhige, leicht erhabene Karten; Bewegung nur als Antwort auf Interaktion.
- Status wird über kleine Punkte mit Halo kommuniziert, nicht über flächige Farbbalken.
- Weinglas als Brand-Mark in einem Bordeaux-Verlaufsquadrat.

## Colors

Warmes Leinen und Tinte, ein Bordeaux als einzige Stimme, Statusfarben nur für Zustände.

### Primary
- **Bordeaux** (`bordeaux`): Primärbuttons, die primäre Action-Card, Fokusrahmen, aktive Optionen, Links beim Hover, das Herz im Footer. Hover dunkelt zu **Tiefem Bordeaux** (`bordeaux-deep`) ab.
- **Nacht-Bordeaux** (`bordeaux-night`, Hover `bordeaux-night-hover`): derselbe Akzent im Dunkelmodus, aufgehellt für Kontrast auf `cellar`.
- **Kellerschatten** (`cellar-shadow`): nur als Zielfarbe in Bordeaux-Verläufen (Brand-Mark, primäre Action-Card), nie als Fläche.
- Der weiche Akzent-Ton (`--accent-soft`: Bordeaux mit 8% Deckkraft hell, 14% dunkel) trägt Fokusringe, aktive Optionen, Icon-Hintergründe und den radialen Schimmer oben im Fenster.

### Neutral
- **Leinen** (`linen`): Fenstergrund und Eingabefelder.
- **Papier** (`paper`): erhabene Flächen, also Karten, Statuschip, Ghost-Buttons und Optionen.
- **Leinen gedämpft** (`linen-subtle`): Hover-Flächen, Mono-Hinweise, Logansicht.
- **Tinte** (`ink`), **Tinte gedämpft** (`ink-muted`), **Tinte blass** (`ink-subtle`): Haupttext, Sekundärtext, Labels und Footer.
- **Keller** (`cellar`, `cellar-elev`, `cellar-subtle`) und **Kreide** (`chalk`, `chalk-muted`, `chalk-subtle`): die Dunkelmodus-Entsprechungen von Leinen und Tinte.
- Linien sind Tinte bzw. Kreide mit 8% (`--border`) oder 14% (`--border-strong`) Deckkraft, nie eine eigene Grauskala.

### Status
- **OK** (`status-ok`), **Warnung** (`status-warn`), **Fehler** (`status-danger`): Statuspunkte und Hinweisboxen. Hinweisboxen mischen die Farbe mit 10–12% in den Hintergrund und mit 22–24% in den Rahmen.

### Gerät (Firmware)
- **Gerät Schwarz** (`device-black`) als AMOLED-Grund, **Gerät Panel** (`device-panel`) für Flächen, **Gerät Text** (`device-text`) und **Gerät gedimmt** (`device-dim`).
- Akzent: **Terra-Cotta** (`device-terracotta`) in Standard-Builds, **Geräte-Bordeaux** (`device-bordeaux`) in der Wine Edition. Quelle ist `firmware/src/theme.h`.

### Named Rules
**The One Voice Rule.** Bordeaux ist die einzige Akzentfarbe der App. Statusfarben bezeichnen Zustände und werden nie dekorativ eingesetzt.

**The Warm Neutral Rule.** Jedes Neutral hat einen Braunstich. Kaltes Grau, reines Schwarz oder reines Weiß als Fenstergrund gibt es in der App nicht; reines Schwarz gehört dem AMOLED-Gerät.

## Typography

**Display Font:** Fraunces (mit SF Pro Display, Segoe UI Variable Display, Georgia)
**Body Font:** Systemschrift (SF Pro Text auf macOS, Segoe UI Variable Text auf Windows)
**Label/Mono Font:** ui-monospace (SF Mono, Cascadia Code, JetBrains Mono, Menlo)

**Character:** Eine weiche, optisch skalierte Serife benennt, die native Grotesk bedient. Mono steht für alles, was der Nutzer abliest oder kopiert: Ports, Versionen, Logs.

### Hierarchy
- **Display** (500, 32px, 1.1, `opsz` 60): Seitenüberschrift, eine pro Screen.
- **Headline** (600, 20px, 1.1): der Markenname „Clawdmeter" im Header.
- **Title** (500, 18–19px): Karten- und Action-Card-Titel.
- **Body** (400, 14px, 1.55): Fließtext in Karten, in `ink-muted`.
- **Control** (500, 13px): Buttons, Eingabefelder, Optionen, Hinweisboxen.
- **Label** (600, 11px, 0.1em, Großbuchstaben): Overlines über Karten und die Unterzeile der Marke.
- **Mono** (12px; Logansicht 11.5px, 1.55): Gerätepfade, Optionsmetadaten, Fortschrittsangaben, Logs.

### Named Rules
**The Label Rule.** Fraunces erscheint nur in Überschriften und im Markennamen. Bedienelemente, Fließtext und Zahlen stehen nie in der Serife.

## Layout

Eine zentrierte Spalte (`max-width` 980px) mit 32px Seitenrand, darüber eine Header-Zeile (Marke links, Statuschip rechts) und darunter ein schlichter Footer. Die Shell ist ein dreizeiliges Grid (Header, Inhalt, Footer). Über dem Header liegt eine unsichtbare Zieh-Leiste für das Fenster; ihre Höhe und Einrückung kommen vom Betriebssystem (macOS 28px hoch mit 80px Platz für die Ampel-Knöpfe, Windows 32px hoch mit 138px Platz rechts für die Fensterknöpfe).

Inhalte stapeln sich als Karten mit 24px Abstand. Die Landing-Seite nutzt ein zweispaltiges Raster aus Action-Cards (16px Abstand), das unter 720px einspaltig wird. Das Fenster öffnet mit 880×700 und lässt sich auf mindestens 720×540 verkleinern.

Alle Abstände kommen aus der 4px-Skala (`spacing`). Bei Seitenwechseln steigen Inhalte gestaffelt um 6px auf (360ms, 60ms Versatz pro Element), aber nur ohne `prefers-reduced-motion`.

## Elevation & Depth

Leicht erhaben. Flächen liegen mit einem kaum sichtbaren, warm getönten Schatten auf dem Leinen; Tiefe entsteht zuerst über den Tonschritt `linen` → `paper` und erst danach über Schatten. Im Dunkelmodus werden die Schatten schwarz und kräftiger, weil warme Schatten auf `cellar` verschwinden würden.

### Shadow Vocabulary
- **Ruhe** (`--shadow-sm`): jede Karte, jeder Button, der Statuschip.
- **Anheben** (`--shadow-md`): Action-Cards beim Hover, zusammen mit `translateY(-2px)`.
- **Bordeaux-Schimmer** (`--shadow-accent`): nur Brand-Mark und primäre Action-Card.
- **Fokus**: 3px-Ring im weichen Akzent-Ton, kombiniert mit dem Ruheschatten.

### Named Rules
**The Lift-On-Intent Rule.** Flächen ruhen. Sie heben sich nur, wenn der Nutzer auf sie zeigt, und nur die eine primäre Aktion darf schimmern.

## Shapes

Sanft gerundete Rechtecke in drei Stufen: 6px für kleine Elemente (Zurück-Button, Mono-Hinweise), 10px für Bedienelemente (Buttons, Felder, Optionen, Hinweisboxen, Icon-Kacheln), 14px für Karten. Pillen (999px) gibt es nur für den Statuschip, Kreise nur für Statuspunkte. Rahmen sind 1px stark und haarfein. Icons haben 1.75px Strichstärke mit runden Enden im 24er-Raster, im Stil von Lucide.

## Components

### Buttons
- **Shape:** sanft gerundet (10px).
- **Primary:** Bordeaux mit weißem Text, 9px 16px, 13px/500, dazu ein innerer Lichtrand oben (`inset 0 1px 0 rgba(255,255,255,.18)`) und der Ruheschatten.
- **Hover / Active / Focus:** Hover dunkelt zu `bordeaux-deep` ab (120ms); Active drückt 1px nach unten; Focus zeigt den 3px-Akzentring. Disabled hat 50% Deckkraft.
- **Ghost:** Papier mit Tinte und kräftigem Haarrahmen; beim Hover `linen-subtle`.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** `paper` auf `linen`.
- **Shadow Strategy:** Ruheschatten, siehe Elevation.
- **Border:** 1px `--border`.
- **Internal Padding:** 20px, Elemente mit 12px Abstand. Aufbau: Label-Overline, Titel in Fraunces, Fließtext in `ink-muted`, optional ein Mono-Hinweis auf `linen-subtle`.

### Action-Card (Signatur)
Große klickbare Karte auf der Landing-Seite mit 36px-Icon-Kachel, Fraunces-Titel (19px), Hinweistext und einem Text-CTA mit Pfeil am unteren Rand. Beim Hover hebt sie sich um 2px. Die **primäre** Variante ist ein Bordeaux-Verlauf (135°, zu `cellar-shadow`) mit weißer Schrift und dem Bordeaux-Schimmer; es gibt genau eine pro Screen.

### Inputs / Fields
- **Style:** `linen` als Grund (eine Stufe tiefer als die Karte), kräftiger Haarrahmen, 10px Radius, 8px 11px Innenabstand, 13px. Das Label steht darüber (12px/600), der Hilfetext darunter (11px, `ink-muted`).
- **Focus:** der Rahmen wird Bordeaux, dazu der 3px-Akzentring.
- **Error / Disabled:** Fehlertext steht unter dem Feld; disabled hat 55% Deckkraft.

### Options (Radio-Liste)
Zeilen auf Papier mit 10px Radius, nativer Radio-Button in Bordeaux, Label links und Mono-Metadaten rechts. Die aktive Zeile bekommt einen Bordeaux-Rahmen und den weichen Akzent-Ton als Fläche.

### Statuschip und Statuspunkt
Pille auf Papier rechts im Header: 8px-Punkt mit 3px-Halo in der Statusfarbe, dazu ein kurzer Text. Ein laufender Vorgang pulsiert langsam (2s, der Halo wächst von 3px auf 6px). Die Zustände sind ok, warn, error und unknown.

### Navigation
Es gibt keine Navigationsleiste. Die Marke im Header führt zurück zur Landing-Seite, Unterseiten haben einen kleinen Zurück-Button (6px Radius, Haarrahmen, 12px) im Subheader. Wizards laufen als gestapelte Karten.

### Fortschritt und Log
Ein 6px-Fortschrittsbalken in einer Linienfarbe, gefüllt mit einem Bordeaux-Verlauf (220ms). Die Logansicht ist eine Mono-Fläche auf `linen-subtle`, höchstens 320px hoch und scrollbar.

### Gerät (Firmware-UI)
Die Provider-Screens auf echtem Schwarz zeigen oben links ein 80×80-Logo, mittig den Providernamen mit Notiz, rechts Akku bzw. USB, darunter Balken pro Zeitfenster und unten einen Status-Spinner. Die Layouts hängen von `kind` und Displaygröße ab (`compute_layout()` in `firmware/src/ui.cpp`).

## Do's and Don'ts

### Do:
- **Do** jede Farbe über die CSS-Variablen in `companion/src/styles.css` beziehen und für jede neue Farbe eine Hell- und eine Dunkel-Variante anlegen.
- **Do** die Systemschrift für alles Bedienbare verwenden und Fraunces nur für Überschriften.
- **Do** Statuspunkte mit Halo verwenden, wenn ein Zustand gezeigt werden soll, und die Statusfarben nur dafür einsetzen.
- **Do** neue Abstände aus der 4px-Skala (`spacing`) nehmen und die Radien 6/10/14px einhalten.
- **Do** jede Animation hinter `prefers-reduced-motion: no-preference` stellen und Transitions auf 120–220ms halten.
- **Do** jedem interaktiven Element einen sichtbaren `:focus-visible`-Zustand mit dem 3px-Akzentring geben.

### Don't:
- **Don't** einen zweiten Akzent neben Bordeaux einführen, auch nicht Terra-Cotta: Terra-Cotta gehört ausschließlich zur Standard-Firmware.
- **Don't** reines Weiß oder kaltes Grau als Fenstergrund verwenden.
- **Don't** mehr als eine primäre (Bordeaux-gefüllte) Action-Card pro Screen zeigen.
- **Don't** Webfonts aus dem Netz nachladen: Die App muss offline und unter ihrer eigenen CSP funktionieren.
- **Don't** Fehlertexte in Bordeaux setzen: Fehler tragen `status-danger`, damit sie nicht mit dem Akzent verwechselt werden.
