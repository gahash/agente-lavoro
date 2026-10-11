"""Genera le vetrine (repository showcase) dei progetti in ~/Desktop/GitHub_Ready.

Solo testi descrittivi: nessun codice, nessun dato reale, nessun nome di cliente o fornitore.
Uso: python3 scripts/genera_vetrine.py   → scrive in vetrine/<slug>/ (README.md + LICENSE)
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "vetrine"
LICENZA = (BASE / "templates" / "LICENSE-proprietaria.txt").read_text(encoding="utf-8")
CONTATTI = "**Contatti:** [gasparepettinati.it](https://gasparepettinati.it) · info@gasparepettinati.it"
SETTORE = "un operatore italiano del mercato libero luce e gas"

P = [
 dict(slug="erpcrm-energy-showcase", emoji="⚡", titolo="ERPCRM Energy — Suite gestionale per venditori di luce e gas",
  tag="CRM, back-office, fatturazione e call center in un'unica piattaforma per il mercato libero dell'energia.",
  desc="Suite gestionale per il mercato libero luce e gas: CRM cliente 360°, back-office, billing, call center e compliance",
  stack_breve="Vue 3 · TypeScript · Fastify · PHP · PostgreSQL/MySQL · Docker",
  problema="Chi vende energia sul mercato libero lavora con strumenti separati: un CRM per i clienti, fogli Excel per le pratiche, un software per il call center, un altro per la fatturazione. I dati si duplicano e gli adempimenti ARERA diventano un lavoro manuale.",
  soluzione=["**Scheda cliente 360°**: anagrafica, forniture (POD/PDR), contratti, documenti, interazioni e pagamenti in un'unica vista.",
   "**Centralino e liste di contatto** con softphone WebRTC integrato.",
   "**Back-office**: gestione pratiche, flussi verso il Sistema Informativo Integrato e archivio XML luce/gas.",
   "**Billing engine** con calcolo delle voci della bolletta e controlli prima della fatturazione.",
   "**Credito e morosità**, tesoreria e banche, listini e offerte commerciali.",
   "**Comunicazioni**: WhatsApp, SMS ed email dal gestionale; area clienti online.",
   "**API per il sito web**: le offerte pubblicate e i contratti firmati online arrivano direttamente nel gestionale (webhook firmati HMAC).",
   "Ruoli e permessi, **audit log** delle attività, validazione di codice fiscale e partita IVA."],
  mermaid="""flowchart LR
    SITO[Sito offerte] -->|API + webhook HMAC| API
    OP[Operatori / Back-office] --> FE[Frontend Vue 3]
    FE --> API[Backend Fastify TypeScript]
    API --> CRM[CRM e contratti]
    API --> BILL[Billing engine]
    API --> TEL[Centralino WebRTC]
    API --> COM[WhatsApp · SMS · Email]
    CRM --> DB[(PostgreSQL / MySQL)]
    BILL --> DB""",
  stack=[("Frontend","Vue 3, Vite, TypeScript, Pinia"),("Backend","Node.js + Fastify (TypeScript), moduli PHP"),("Dati","PostgreSQL, MySQL, export Excel"),("Integrazioni","Twilio, WhatsApp, webhook HMAC verso il sito offerte"),("Infrastruttura","Docker, script di deploy, build Android")]),

 dict(slug="ai-sales-voice-agent-showcase", emoji="🎙️", titolo="Agente vocale AI per la vendita di luce e gas",
  tag="Un agente telefonico che parla in italiano, spiega le offerte con trasparenza e passa la chiamata a un operatore quando serve. Tutto self-hosted.",
  desc="Agente vocale AI self-hosted (STT, LLM e TTS locali) per vendita e assistenza luce e gas, con regole di compliance",
  stack_breve="Python · FastAPI · faster-whisper · TTS neurale · LLM locale",
  problema="Le chiamate commerciali nel settore energia sono tante, ripetitive e molto regolamentate: l'operatore deve presentarsi correttamente, spiegare PUN/PSV e costi obbligatori senza promettere risparmi certi e rispettare chi non vuole essere ricontattato.",
  soluzione=["**Conversazione vocale in italiano**: riconoscimento del parlato (Whisper) e voce sintetica naturale con più motori TTS selezionabili.",
   "**Motore decisionale** che guida la chiamata: presentazione, qualifica (casa/business, luce/gas/dual), spiegazione dell'offerta, gestione delle obiezioni.",
   "**Regole di compliance nel codice**: dichiarazione dell'identità, nessuna promessa di risparmio certo, chiusura cortese e blocco dei ricontatti su rifiuto.",
   "**Base di conoscenza** sulle domande frequenti (bolletta, POD/PDR, recesso, firma digitale, volture e subentri).",
   "**Apprendimento controllato**: le conversazioni vengono valutate e gli esempi approvati migliorano le risposte.",
   "Dashboard di analisi e training; test automatici su dialoghi, STT e instradamento TTS."],
  mermaid="""flowchart LR
    TEL[Telefonia SIP] --> STT[Speech-to-text Whisper]
    STT --> DE[Motore decisionale + compliance]
    DE --> LLM[LLM locale]
    DE --> KB[Base di conoscenza FAQ]
    DE --> TTS[Sintesi vocale neurale]
    TTS --> TEL
    DE --> AN[(Analisi e training)]""",
  stack=[("Backend","Python, FastAPI, Pydantic"),("Voce","faster-whisper, TTS neurali (XTTS, Kokoro, ElevenLabs opzionale)"),("AI","LLM locali via Ollama, motore decisionale a regole"),("Qualità","pytest su dialoghi, decisioni, STT e TTS")]),

 dict(slug="customer-care-voice-agent-showcase", emoji="📞", titolo="Sara — Assistente vocale per il customer care energia",
  tag="Un'assistente vocale che riconosce il cliente, legge bollette, contratti e pratiche dal CRM e apre ticket in autonomia.",
  desc="Assistente vocale per il customer care luce e gas: riconoscimento cliente, bollette, pratiche e ticket dal CRM, LLM con fallback",
  stack_breve="Python · FastAPI · LLM (cloud/locale) · VoIP · PHP/MySQL",
  problema="Il customer care riceve ogni giorno le stesse domande: stato della bolletta, pagamenti, avanzamento delle pratiche. Ogni chiamata richiede di cercare il cliente in più schermate.",
  soluzione=["**Identificazione del cliente** da nome, telefono o codice cliente.",
   "**Risposte sui dati reali**: bollette pagate e insolute, contratti, pratiche attive, consumi con grafici.",
   "**Apertura ticket** direttamente nel CRM e trasferimento all'operatore quando serve.",
   "**LLM con uscita strutturata (JSON)**: il modello restituisce sia il parlato sia le azioni da mostrare a schermo.",
   "**Fallback robusto**: se il modello non risponde subentra un motore a regole; funziona sia con un LLM cloud sia con un LLM locale.",
   "Canale **telefonico VoIP** e dashboard web con voce nel browser; ampia suite di test e simulazioni di chiamata (anche con cliente arrabbiato)."],
  mermaid="""flowchart LR
    C[Cliente al telefono / web] --> V[STT + VAD]
    V --> AG[Agente FastAPI]
    AG --> LLM[LLM con uscita JSON]
    LLM -. errore .-> R[Motore a regole]
    AG --> CRM[API CRM]
    CRM --> DB[(MySQL)]
    AG --> TTS[Sintesi vocale] --> C""",
  stack=[("Backend","Python, FastAPI"),("Voce","pyVoIP, webrtcvad, Whisper / faster-whisper, TTS cloud, SSML"),("AI","LLM cloud gestito oppure Ollama in locale, fallback a regole"),("CRM","API REST PHP + MySQL"),("Esercizio","systemd, script di deploy e diagnostica")]),

 dict(slug="call-quality-ai-showcase", emoji="🎧", titolo="Controllo qualità delle chiamate con AI",
  tag="Trascrive le telefonate del call center e le valuta automaticamente rispetto ai criteri di qualità dell'azienda.",
  desc="Piattaforma di quality assurance per call center: trascrizione delle chiamate e valutazione automatica con LLM, code di lavoro e report",
  stack_breve="PHP · Laravel · MySQL · Code di lavoro · LLM",
  problema="Nei call center il controllo qualità si fa ascoltando a campione poche chiamate: lento, costoso e soggettivo. Le chiamate critiche (per esempio i ripensamenti dei clienti) emergono troppo tardi.",
  soluzione=["**Caricamento e importazione massiva** delle registrazioni e delle trascrizioni.",
   "**Trascrizione automatica** e **valutazione con LLM** sui criteri di qualità definiti dall'azienda: punteggio, motivazioni, anomalie.",
   "**Code di lavoro asincrone** con più worker: l'interfaccia resta reattiva anche con migliaia di chiamate.",
   "Report per operatore, **ricerca semantica** nelle conversazioni, notifiche.",
   "Ruoli, autenticazione a due fattori (TOTP) e **audit log**."],
  mermaid="""flowchart LR
    UP[Registrazioni] --> Q[(Coda)]
    Q --> W[Worker]
    W --> STT[Trascrizione]
    STT --> LLM[Valutazione LLM]
    CR[(Criteri di qualità)] --> LLM
    LLM --> DB[(MySQL)]
    DB --> UI[Report e dashboard]""",
  stack=[("Applicazione","PHP, Laravel, architettura MVC"),("Dati","MySQL, SQLite per indici locali"),("AI","Server LLM esterno per trascrizione e valutazione"),("Sicurezza","TOTP, ruoli, audit log")]),

 dict(slug="otp-e-signature-showcase", emoji="✍️", titolo="Firma elettronica OTP con prove forensi",
  tag="Firma dei contratti via SMS/OTP con raccolta delle evidenze e ancoraggio crittografico degli hash.",
  desc="Servizio di firma elettronica via OTP: sessioni di firma, evidenze forensi, PDF sigillati e ancoraggio degli hash con Merkle tree",
  stack_breve="Python · FastAPI · Next.js · Redis · PostgreSQL · crittografia",
  problema="Far firmare un contratto a distanza deve essere semplice per il cliente ma solido come prova: chi ha firmato, quando, da quale dispositivo, e che il documento non sia stato alterato.",
  soluzione=["**Sessioni di firma con OTP** inviato via SMS ed email, con instradamento delle notifiche.",
   "**Raccolta delle evidenze**: IP, dispositivo, user agent e geolocalizzazione approssimativa tramite middleware dedicato.",
   "**PDF firmati e sigillati** con generazione del documento e hash.",
   "**Ancoraggio degli hash** raggruppati in un Merkle tree: si può dimostrare in seguito che il documento non è cambiato.",
   "Pannello operatore in Next.js: contratti, ispezione del dispositivo, stato del sistema.",
   "Test su crittografia, PDF, forensics e notifiche."],
  mermaid="""flowchart LR
    CL[Cliente] -->|link + OTP| FE[Pagina di firma]
    FE --> API[API FastAPI]
    API --> OTP[Servizio OTP + Redis]
    API --> FO[Evidenze forensi]
    API --> PDF[PDF firmato + hash]
    PDF --> MK[Merkle batcher]
    MK --> AN[(Ancoraggio hash)]
    API --> DB[(PostgreSQL)]""",
  stack=[("Backend","Python, FastAPI, Pydantic, PyJWT"),("Sicurezza","cryptography, OTP, Redis, analisi user agent / GeoIP"),("Documenti","pypdf, ReportLab"),("Frontend","Next.js, React, Tailwind"),("Integrità","Merkle tree, web3")]),

 dict(slug="energy-offer-activation-showcase", emoji="🧾", titolo="Sito offerte e attivazione contratti online",
  tag="Dal confronto delle offerte alla firma del contratto, online e senza carta, con i dati che arrivano direttamente nel gestionale.",
  desc="Sito offerte luce e gas con attivazione online: configuratore, contratto generato, firma OTP e invio al gestionale via API",
  stack_breve="Next.js · TypeScript · Prisma · Node.js · Docker",
  problema="Un cliente che sceglie un'offerta online spesso deve poi ricevere una chiamata, compilare moduli e rispedire documenti. Ogni passaggio manuale è un cliente perso.",
  soluzione=["**Vetrina delle offerte** luce, gas e dual con schede di dettaglio, aggiornate dal gestionale.",
   "**Percorso di attivazione** per clienti domestici e business, con contratto generato in automatico.",
   "**Firma elettronica OTP** del contratto ed email di conferma con i documenti.",
   "**Invio al gestionale** dei contratti e delle richieste di ricontatto tramite API e webhook.",
   "Pagine legali, cookie banner, SEO tecnica (sitemap, robots), checklist di deploy e rollback."],
  mermaid="""flowchart LR
    U[Visitatore] --> WEB[Sito Next.js]
    WEB --> OFF[Offerte dal gestionale]
    WEB --> ATT[Attivazione + contratto]
    ATT --> OTP[Firma OTP]
    ATT --> DB[(Database Prisma)]
    ATT -->|API / webhook| CRM[Gestionale]""",
  stack=[("Frontend","Next.js, React, TypeScript"),("Dati","Prisma ORM"),("Backend","Node.js, Express, Helmet, Nodemailer"),("Esercizio","Docker Compose, checklist di deploy")]),

 dict(slug="pec-ai-assistant-showcase", emoji="📨", titolo="PEC Assistant — webmail PEC con assistente AI",
  tag="Legge la casella PEC aziendale, classifica i messaggi e prepara le risposte con l'AI. Nulla parte senza conferma.",
  desc="Webmail PEC con classificazione, ricerca, risposte automatiche programmate e bozze AI approvate dall'operatore",
  stack_breve="TypeScript · Node.js · IMAP/SMTP · SQLite · LLM",
  problema="La PEC aziendale riceve reclami, richieste e comunicazioni ufficiali mescolate a ricevute tecniche. Smistarle e rispondere a mano richiede ore, e un errore può avere conseguenze legali.",
  soluzione=["**Webmail PEC** collegata via IMAP/SMTP al gestore, senza toccare lo stato letto/non letto in Outlook.",
   "**Esclusione automatica** delle ricevute tecniche; **classificazione** e **ricerca** full-text dei messaggi.",
   "**Bozze di risposta con AI** basate su istruzioni aziendali ed esempi approvati, con soglia di confidenza.",
   "**Revisione umana obbligatoria** per i casi legali, contrattuali, economici o con dati personali: si invia solo dopo conferma.",
   "**Risposte automatiche programmate** (es. ferie) con modalità di simulazione.",
   "Utenti, ruoli, audit log, backup e report; test automatici."],
  mermaid="""flowchart LR
    PEC[Casella PEC] -->|IMAP| SYNC[Sincronizzazione]
    SYNC --> CL[Classificazione + indice di ricerca]
    CL --> UI[Webmail operatore]
    UI --> AI[Bozza AI]
    AI --> REV{Conferma operatore}
    REV -->|SMTP| PEC""",
  stack=[("Backend","Node.js, TypeScript, Express, Zod, Pino"),("Posta","ImapFlow, mailparser, Nodemailer"),("AI","LLM via API o Ollama in locale"),("Esercizio","Docker, Plesk, avvio automatico su Windows")]),

 dict(slug="sms-gateway-showcase", emoji="💬", titolo="SMS Box — gateway SMS con consensi e controllo dei costi",
  tag="Invii SMS transazionali e campagne con gestione dei consensi, idempotenza e budget sotto controllo.",
  desc="Gateway SMS in Laravel: API con idempotenza, campagne, consensi e opposizioni, budget, riconciliazione degli esiti",
  stack_breve="PHP · Laravel · Livewire · Redis · API REST",
  problema="Mandare SMS dai gestionali aziendali sembra semplice, ma servono garanzie: niente doppi invii, rispetto delle opposizioni, costi prevedibili e stato reale di consegna.",
  soluzione=["**API interne** per contatti, preventivi e messaggi con chiave di **idempotenza** obbligatoria.",
   "**Campagne** programmate con esclusioni.",
   "**Consensi e opposizioni**: chi ha detto no non riceve più messaggi.",
   "**Budget e registro dei costi** per evitare sorprese in fattura.",
   "Code di lavoro per invio, polling degli esiti, **riconciliazione degli esiti incerti**, scadenza e pulizia dei dati.",
   "Autenticazione a due fattori, ruoli e audit log."],
  mermaid="""flowchart LR
    APP[Gestionali] -->|API + Idempotency-Key| API[Laravel API]
    API --> CS{Consenso / opposizione / budget}
    CS --> Q[(Code Redis)]
    Q --> SEND[Invio al provider SMS]
    SEND --> POLL[Esiti e riconciliazione]
    POLL --> DB[(Database)]""",
  stack=[("Applicazione","PHP, Laravel, Livewire, Sanctum"),("Code","Redis, job pianificati"),("Sicurezza","Google2FA, ruoli, audit log"),("Esercizio","Docker Compose")]),

 dict(slug="registered-mail-monitor-showcase", emoji="📮", titolo="Monitor raccomandate — preavvisi, pagamenti e contestazioni",
  tag="Traccia le raccomandate di preavviso, i pagamenti e le contestazioni con uno storico che non si cancella mai.",
  desc="Applicazione Django per seguire raccomandate di preavviso, pratiche, pagamenti e contestazioni con audit completo",
  stack_breve="Python · Django · PostgreSQL · API REST",
  problema="Le pratiche di preavviso per morosità richiedono tempi precisi e prove documentali: date di invio e consegna della raccomandata, pagamenti arrivati nel frattempo, reclami che bloccano la procedura.",
  soluzione=["**Sincronizzazione automatica** con il servizio di raccomandata elettronica: stato, date, esito postale, PDF e ricevute.",
   "**Pratiche** con decorrenza dei termini, priorità, operatore assegnato e verifiche di conformità.",
   "**Pagamenti**, **contestazioni** e **blocchi** cautelativi collegati alla pratica.",
   "**Nessuna cancellazione distruttiva**: archiviazione e audit log di ogni cambio di stato.",
   "Dashboard con archivio storico per anno e mese, analisi ed esportazioni.",
   "**API REST** per l'integrazione con il CRM dei ticket."],
  mermaid="""flowchart LR
    RACC[Servizio raccomandate] -->|sync programmata| IMP[Importer Django]
    IMP --> PR[Pratiche]
    PAG[Pagamenti] --> PR
    CON[Contestazioni / blocchi] --> PR
    PR --> DB[(PostgreSQL + audit log)]
    DB --> DASH[Dashboard e report]
    DB -->|API REST| CRM[CRM ticket]""",
  stack=[("Applicazione","Python, Django, Gunicorn, WhiteNoise"),("Dati","PostgreSQL"),("Integrazioni","Sincronizzazione HTTP, lettura PDF"),("Esercizio","Comandi di gestione e worker programmati")]),

 dict(slug="social-lead-platform-showcase", emoji="📣", titolo="Piattaforma social e lead multi-account",
  tag="Pianifica, approva e pubblica contenuti su Facebook e Instagram con l'AI, e raccoglie i lead delle campagne.",
  desc="Piattaforma multi-tenant Next.js per contenuti social assistiti da AI, approvazioni, pubblicazione Meta e raccolta lead",
  stack_breve="Next.js · TypeScript · Prisma · PostgreSQL · Docker",
  problema="Le aziende che fanno marketing sui social perdono tempo tra calendario editoriale, approvazioni via chat, pubblicazione manuale e lead dispersi tra piattaforme diverse.",
  soluzione=["**Calendario editoriale** e **flusso di approvazione** dei contenuti.",
   "**Testi suggeriti dall'AI** (modello Qwen) da rivedere prima della pubblicazione.",
   "**Pubblicazione su Facebook e Instagram** tramite Meta OAuth: nessuna password social salvata.",
   "**Raccolta lead** da form e API, integrazione con il software del call center e Google Ads.",
   "**Multi-account e white-label**, con dominio personalizzato per le landing.",
   "Credenziali cifrate, ruoli e test automatici (Vitest)."],
  mermaid="""flowchart LR
    ED[Redazione] --> APP[Next.js]
    APP --> AI[Testi AI]
    APP --> APPR{Approvazione}
    APPR --> META[Pubblicazione Meta]
    FORM[Landing e form] --> LEAD[Lead API]
    LEAD --> CC[Call center]
    APP --> DB[(PostgreSQL / Prisma)]""",
  stack=[("Applicazione","Next.js, React, TypeScript, Tailwind, Zod"),("Dati","PostgreSQL, Prisma"),("Integrazioni","Meta Graph API (OAuth), Google Ads, webhook call center"),("Esercizio","Docker, Caddy")]),

 dict(slug="recruiting-portal-showcase", emoji="🧑‍💼", titolo="Portale candidature e selezione del personale",
  tag="Candidature online con documenti, consensi privacy e QR code per le sedi, e un pannello per gestirle.",
  desc="Portale PHP per raccogliere candidature con documenti e consensi, QR code per sede e pannello di selezione",
  stack_breve="PHP · MySQL · PHPMailer · QR code",
  problema="Le candidature arrivano da email, messaggi e moduli cartacei: CV persi, consensi privacy non tracciati, nessuna visione d'insieme per chi seleziona.",
  soluzione=["**Modulo di candidatura online** con caricamento dei documenti e **consenso privacy** registrato.",
   "**QR code per sede o campagna**: il candidato arriva al modulo già precompilato.",
   "**Pannello di selezione**: elenco, filtri, gruppi, scheda candidato e download protetto dei documenti.",
   "Notifiche email, gestione delle candidature ripetute, cambio password e accesso riservato.",
   "Privacy e cookie policy integrate."],
  mermaid="""flowchart LR
    QR[QR code sede] --> FORM[Modulo candidatura]
    FORM --> API[API candidature + consenso]
    API --> DB[(MySQL)]
    API --> DOC[Documenti protetti]
    DB --> ADM[Pannello selezione]
    API --> MAIL[Notifica email]""",
  stack=[("Applicazione","PHP"),("Dati","MySQL"),("Integrazioni","PHPMailer, generazione QR code")]),
]


def readme(p: dict) -> str:
    sol = "\n".join(f"- {s}" for s in p["soluzione"])
    st = "\n".join(f"| {a} | {b} |" for a, b in p["stack"])
    return f"""# {p['emoji']} {p['titolo']}

> {p['tag']}

**Contesto:** realizzato per {SETTORE} (nome omesso per riservatezza) · **Ruolo:** analisi, progettazione e sviluppo · **Codice:** privato

---

## Il problema
{p['problema']}

## La soluzione
{sol}

## Architettura (semplificata)
```mermaid
{p['mermaid']}
```

## Stack
| Livello | Tecnologie |
|---|---|
{st}

---
### Perché il codice non è pubblico
Il software è in uso in azienda e tratta dati di clienti reali: codice, configurazioni e dati restano privati.
Questa pagina descrive cosa fa e come è costruito. Demo con **dati fittizi** su appuntamento; codice visionabile in **screen-share** o dopo **NDA**.

**Vuoi una soluzione simile per la tua azienda?** Scrivimi: analizzo il processo e propongo una versione su misura.

{CONTATTI}

© 2026 Gaspare Pettinati — Tutti i diritti riservati. Vedi [LICENSE](LICENSE).
"""


if __name__ == "__main__":
    for p in P:
        d = OUT / p["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text(readme(p), encoding="utf-8")
        (d / "LICENSE").write_text(LICENZA, encoding="utf-8")
        (d / ".descrizione").write_text(p["desc"] + "\n", encoding="utf-8")
        print("ok", p["slug"])
