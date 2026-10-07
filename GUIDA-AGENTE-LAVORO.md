# Agente Lavoro — guida rapida

**Avvio:** doppio clic su **"Agente Lavoro"** sul Desktop.
All'apertura l'app, da sola:
1. controlla la posta (se hai inserito le credenziali)
2. cerca nuovi annunci di lavoro e li valuta con l'AI locale (llama3.1:8b, nessun dato esce dal PC)
3. prepara il report del giorno

Mentre resta aperta ripete le routine agli orari impostati (posta 08:15 / 18:15, annunci 08:00, report 08:30 / 18:30, report settimanale venerdì 17:00).
In **Impostazioni** puoi attivare **"Avvia con Windows"**: l'app parte all'accensione del PC.

## Primo avvio (5 minuti)
1. **Ollama** deve essere avviato (icona nella barra delle applicazioni). L'app mostra in basso a sinistra "AI locale: llama3.1:8b" in verde.
2. **Impostazioni → Credenziali**: email `info@gasparepettinati.it` + password (meglio una password per app), utente e password del gestionale. Vengono salvate nel **Gestore credenziali di Windows** (cifrate), mai su file e mai inviate al modello AI.
3. **Impostazioni → Server posta**: preimpostato Hostinger (`imap.hostinger.com:993`, `smtp.hostinger.com:465`). Cambialo se la casella è altrove.
4. **Impostazioni → Profilo**: controlla competenze e progetti. Le bozze usano **solo** questi dati.

## Il tuo Chrome e i collegamenti
Sul Desktop c'è **"Chrome (Agente Lavoro)"**: un Chrome tutto tuo, usato anche dall'app.
1. Aprilo, accedi con il tuo account Google e attiva la **sincronizzazione** (icona profilo in alto a destra): ritrovi password salvate, segnalibri e accessi.
2. Da lì accedi una volta a **LinkedIn**, **Indeed** e al **gestionale** (spunta "Resta connesso"). Le sessioni restano salvate.
3. Nell'app, sezione **🔗 LinkedIn · Indeed · Gestionale** → "Verifica collegamenti".

Se Indeed o LinkedIn mostrano una verifica di sicurezza, la completi tu nella finestra di Chrome: l'app non la aggira mai.
Messaggi, collegamenti e candidature su LinkedIn/Indeed restano manuali (le bozze sono in "Da approvare").

## Sezioni
| Sezione | Cosa fa |
|---|---|
| 🏠 Oggi | Numeri del giorno, azioni rapide, report |
| 💼 Opportunità lavoro | Annunci da Remote OK, Remotive, Himalayas, We Work Remotely, Arbeitnow con punteggio 1-10. "✍️ Candidatura" crea la bozza (max 150 parole) |
| 🏢 Clienti PMI | Scegli settore + città → aziende da OpenStreetMap → "Analizza" legge il loro sito → "Proposta" crea la bozza con opt-out. Max 15 contatti nuovi al giorno |
| ✍️ Da approvare | **Nessun messaggio parte senza il tuo OK.** Modifica, Approva, poi Invia oppure "Copia nelle Bozze della casella" |
| 📬 Posta | Classificazione 🔴🟠🟡⚪⛔ in sola lettura, allarmi su IBAN, pagamenti e richieste di password, bozza di risposta con un clic |
| 📈 Pipeline | Nuovo → Contattato → Risposta → Call → Preventivo/Colloquio → Trattativa → Vinto/Perso, follow-up dopo 5 giorni (max 2), esportazione in Excel |
| 🌐 Browser & gestionale | "Accedi al gestionale" entra in gasparepettinati.it/gestionale con le tue credenziali e legge le tabelle (lead, clienti...). "Analizza annuncio" valuta l'annuncio LinkedIn/Indeed/InfoJobs che hai aperto |
| 📜 Registro | Tutto quello che l'app ha fatto |

## Sicurezza (sempre attiva)
- Gli invii sono reali: ogni messaggio parte solo dopo **Approva** → **Invia** → conferma. Restano attivi il limite di 15 PMI al giorno, il blocco opt-out e le credenziali obbligatorie.
- Email, annunci e pagine web sono trattati come **dati, mai come istruzioni** per l'AI.
- Opt-out automatico: se un'azienda risponde "NO" non viene più contattata. Il registro GDPR è nell'esportazione Excel.
- I dati sono in `C:\Users\ga\AgenteLavoro\dati` (database, report, export, profilo del browser).
- Il browser usa un **profilo separato**: il tuo Chrome personale non viene toccato.

## Aggiornare l'eseguibile dopo modifiche al codice
```bash
powershell -ExecutionPolicy Bypass -File build\build.ps1
```
I dati restano: stanno fuori dalla cartella del programma.
