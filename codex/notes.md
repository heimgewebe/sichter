Sichter Notes – interne Hinweise

Dies sind interne Entwicklungsnotizen für zukünftige Sichter-Erweiterungen.

1. Heuristik-Regeln
	•	Code-Hotspots anhand von Änderungsfrequenz + SemantAH-Ähnlichkeitsgraph erkennen.
	•	Driftdetektion: Konfliktpotenzial steigt bei 3+ semantischen Brüchen in einem PR.
	•	Redundanz-Scanner: Mehrfach auftauchende Lösungsbausteine → Hinweis erzeugen.

2. Rückgaberegeln
	•	Nie mehr als drei Vorschläge pro Analyse.
	•	Immer Risikoindikator ergänzen.
	•	Bei Unsicherheit: lieber Nachfragen generieren statt falsche Behauptungen.

3. Vision
	•	Sichter soll später autonome „Mini-Checks“ farbkodiert bündeln: strukturell, semantisch, riskant, stilistisch.
	•	Ziel: deterministische, vertrauenswürdige Soft-Reflexion.
