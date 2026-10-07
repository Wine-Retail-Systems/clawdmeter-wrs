# Spec Delta

## Purpose

Beschreibt, wie das Gerät einen Budget-Screen (`cost_budget`) darstellt: Verbrauch gegen Limit als Balken, der bei vorhandenen Anteilen nach Modellfamilie segmentiert ist, damit Budget und Modell-Mix in einem Element ablesbar sind.

## ADDED Requirements

### Requirement: Segmentierter Budgetbalken
Enthält ein `cost_budget`-Payload ein Limit (`m2 > 0`) und Anteile (`sh`), SHALL der Budgetbalken bis zur Auslastung `m1 / m2` (begrenzt auf 100 %) gefüllt sein, und die Füllung SHALL in Segmente in der Reihenfolge der Anteile aufgeteilt sein, deren Längen proportional zu den Anteilen sind. Jedes Segment SHALL eine eigene Farbe aus einer festen Palette tragen, die weder die Statusfarben Grün, Gelb noch Rot verwendet.

#### Scenario: Zwei Familien
- **WHEN** `m1 = 3769`, `m2 = 15000` und `sh = [{Opus, 74}, {Sonnet, 26}]` empfangen werden
- **THEN** ist der Balken zu rund 25 % gefüllt, davon etwa drei Viertel in der ersten und ein Viertel in der zweiten Segmentfarbe

#### Scenario: Überzogenes Budget
- **WHEN** `m1` größer als `m2` ist
- **THEN** ist der Balken vollständig gefüllt, segmentiert nach Anteilen, und die Prozentangabe zeigt den tatsächlichen Wert über 100 %

### Requirement: Legende der Anteile
Unter dem segmentierten Balken SHALL eine Legendenzeile je Anteil einen Farbpunkt in der Segmentfarbe, das Kürzel und den Prozentwert zeigen. Die Legende MUST auf beiden Displaygrößen (480×480 und 368×448) ohne Überlappung mit Prozentangabe und Reset-Countdown passen.

#### Scenario: Vier Einträge auf dem kleinen Display
- **WHEN** vier Anteile auf dem AMOLED-1.8 (368×448) angezeigt werden
- **THEN** sind alle vier Kürzel mit Prozentwert vollständig lesbar und überlagern keine anderen Elemente

### Requirement: Auslastungswarnung bleibt sichtbar
Die Auslastung SHALL weiterhin als Prozentwert angezeigt werden und SHALL ab 50 % gelb und ab 80 % rot eingefärbt sein, auch wenn der Balken segmentiert ist.

#### Scenario: Hohe Auslastung
- **WHEN** die Auslastung 92 % beträgt und Anteile vorliegen
- **THEN** ist der Balken nach Anteilen segmentiert und die Prozentangabe rot

### Requirement: Rückfall auf einfarbigen Balken
Fehlen Anteile im Payload, SHALL der Budget-Screen wie bisher einen einfarbigen Balken in der Auslastungsfarbe zeigen und keine Legende. Ist kein Limit gesetzt (`m2 = 0`), SHALL kein Balken und der Hinweis „Kein Budget gesetzt" erscheinen.

#### Scenario: Langdock ohne Anteile
- **WHEN** ein `cost_budget`-Payload ohne `sh` empfangen wird
- **THEN** zeigt der Screen den einfarbigen Balken ohne Legende, wie vor dieser Änderung

#### Scenario: Wechsel zwischen Zyklen
- **WHEN** ein Zyklus Anteile enthält und der folgende nicht
- **THEN** verschwinden Segmente und Legende, und der einfarbige Balken erscheint

### Requirement: Keine Sparkline mehr
Der `tokens_abs`-Screen SHALL keine Stunden-Sparkline und keinen Vergleich „vs. gestern" mehr zeigen; Wert, Donut mit Legende und Reset-Countdown bleiben. Ein empfangenes Feld `sp` SHALL ignoriert werden.

#### Scenario: Älterer Daemon sendet `sp`
- **WHEN** ein Payload mit Feld `sp` empfangen wird
- **THEN** wird es ohne Fehler ignoriert und der Screen rendert normal
