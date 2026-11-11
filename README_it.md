# XAnalyze

Trova testo scritto da un modello, caratteri invisibili e difetti di
accessibilità, SEO, prestazioni e sicurezza in un sito, in un file HTML o in un
repository - e indica la riga esatta, non un punteggio.

[English](README.md) | [Українська](README_ua.md)

## A cosa serve

Vi consegnano una pagina, un tema, una web part o un repository e dovete
rispondere a tre domande: questo testo lo ha scritto un modello, il markup
contiene caratteri che nessuna tastiera produce, e la cosa è accessibile e
corretta. XAnalyze risponde a tutte e tre in una sola esecuzione e nomina il
file e la riga dietro ogni risposta.

È un solo binario con tre superfici - una finestra, un'interfaccia da terminale
e una riga di comando - sopra un unico nucleo, così le tre non possono essere in
disaccordo su cosa sia stato misurato.

## Installazione

**App macOS**

```bash
curl -L -o XAnalyze.app.zip https://github.com/vlad-demchyk/xAnalyze-/releases/latest/download/XAnalyze.app.zip
ditto -x -k XAnalyze.app.zip /Applications/
```

Al primo avvio l'app propone una volta di installarsi come `xanalyze` in
`~/.local/bin`, così CLI e TUI non richiedono un secondo download, e
`xanalyze update` aggiorna tutti e tre insieme. Il bundle non
è ancora firmato: il primo avvio richiede Control-click -> Apri.

**Solo riga di comando**

Il download è uno, l'app: finestra, CLI e TUI sono un solo programma. Per avere
il comando `xanalyze` senza aprire la finestra:

```bash
/Applications/XAnalyze.app/Contents/MacOS/XAnalyze --install-cli
```

**Dai sorgenti**

```bash
git clone https://github.com/vlad-demchyk/xAnalyze-.git && cd xAnalyze-
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py                                  # finestra
python cli.py fullscan https://example.com      # riga di comando
python cli.py                                   # interfaccia da terminale
```

**Windows 10/11, dai sorgenti**

Non c'è ancora un download per Windows: si avvia da un checkout. Serve
Python 3.13 o successivo da python.org (con il launcher `py`), in PowerShell:

```powershell
git clone https://github.com/vlad-demchyk/xAnalyze-.git; cd xAnalyze-
py -3.13 -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py                              # finestra
venv\Scripts\python cli.py fullscan https://example.com  # riga di comando
venv\Scripts\python cli.py                               # interfaccia da terminale
```

L'output è sempre UTF-8, qualunque sia la code page della console, quindi si
può reindirizzare su file o passare a un agente. Impostazioni, file di riserva
delle credenziali e sessioni dei siti con accesso stanno in
`%APPDATA%\xanalyze`, il log dell'app in `%LOCALAPPDATA%\xanalyze\logs`, le
chiavi vanno in Gestione credenziali di Windows. `xanalyze update` aggiorna
solo l'app macOS; su Windows il checkout si aggiorna con `git pull`.

La build per Windows (`dist\XAnalyze\XAnalyze.exe` per la finestra e
`xanalyze-cli.exe` per riga di comando e TUI): `pip install pyinstaller`, poi
`powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`.

## Come si usa

```bash
xanalyze                                      # interfaccia da terminale
xanalyze fullscan https://example.com         # tutto, in una sola esecuzione
xanalyze fullscan ./my-project                # lo stesso, su un repository
xanalyze scan ./src                           # solo pattern AI e caratteri
xanalyze audit ./page.html                    # solo le regole del sito
xanalyze fix ./src                            # applica le correzioni (tiene i .bak)
xanalyze runs                                 # elenco, ripresa, confronto
```

`fullscan` è la risposta a «controlla questo». Un URL viene percorso e
renderizzato; una cartella viene letta come sorgente, salvo che `--devserver`
avvii il server del progetto; un singolo file HTML viene letto come la pagina
finita che è.

### Comandi

| Comando | Cosa fa |
|---|---|
| `fullscan BERSAGLIO` | pattern AI, caratteri e tutte le regole del sito, più i report |
| `scan PERCORSI` | pattern AI e caratteri non da tastiera, senza modificare nulla |
| `audit BERSAGLIO` | solo le regole del sito: URL, file HTML o cartella |
| `fix` / `undo` | applica le correzioni esatte dei caratteri; ripristina le copie `.bak` |
| `runs` / `resume` / `compare` | l'esecuzione è un oggetto: elencarla, riprenderla, confrontarla |
| `ignore FINGERPRINT --reason TEXT` | segnare un risultato come falso positivo in `.xanalyze-ignore`, con il motivo; l'impronta è in `audit --json` e ogni esecuzione successiva dice quanti ne ha nascosti e perché |
| `login URL` | accedere a mano, in un browser vero, perché l'esecuzione veda oltre la porta; salvato solo dopo «Fatto» |
| `logs` | cosa ha fatto davvero l'esecuzione, in JSON Lines |
| `ai` | l'account dietro i passaggi con modello: `status`, `login`, `rewrite` |
| `agent-scan` / `agent-judge` | passare i candidati a un agente e riprendere i suoi verdetti |
| `clean` | filtra testo da stdin a stdout |
| `update` / `uninstall` | autoaggiornamento dall'ultima release; rimozione completa |

L'aggiornamento prepara e verifica il bundle GUI prima della sostituzione e ripristina
l'app precedente se l'installazione fallisce. Un aggiornamento parziale CLI/GUI restituisce
il codice `3` e indica il componente fallito; prima di riprovare nella TUI, verifica di nuovo.

I nuovi log nascondono credenziali negli URL, query, frammenti e campi contenenti
segreti. Su macOS/Linux, log e file di credenziali di riserva sono privati;
gli aggiornamenti delle credenziali sono atomici e serializzati tra processi.

La scansione incrementale confronta testo analizzato, opzioni, esclusioni e versione
dell'app. I verdetti AI usano la cache dedicata. Le scritture concorrenti delle cache
di scansione, browser e giudizi uniscono le modifiche sotto lock e sostituiscono il file atomicamente.

`xanalyze COMANDO --help` stampa tutte le opzioni. Quelle che vale la pena
conoscere:

| Opzione | A cosa serve |
|---|---|
| `--depth N`, `--max-pages N` | quanto lontano va la scansione e quante pagine; una pagina oltre 10 MB è segnalata come non letta e le immagini non vengono mai scaricate da indirizzi privati o locali che la scansione non ha visitato |
| `--repo PERCORSO` | il checkout dietro un sito, così un risultato nomina il file e non solo la pagina |
| `--devserver` | avvia il dev server del progetto e analizza il sito renderizzato |
| `--breakpoints all` | audit a ogni larghezza; senza, una sola (1440x900) |
| `--color-scheme dark` | mostra alla pagina `prefers-color-scheme: dark`, per verificare un tema scuro; uno schema per esecuzione |
| `--no-browser` | solo la lettura statica, e molto più veloce |
| `--detector NOME` | `offline` (predefinito, gratuito), `embedding`, `hybrid`, `ai` |
| `--category`, `--confidence` | restringere ciò che viene riportato; entrambe sono viste su un unico passaggio |
| `--within SELETTORE` | analizzare solo questa parte della pagina - un widget o una web part consegnata |
| `--report PERCORSO`, `--styled-report PERCORSO` | briefing per un agente (`.md`/`.json`) e report per una persona (`.pdf`/`.html`) |
| `--json`, `--check` | output leggibile da una macchina; codice 1 con risultati seri |
| `--progress jsonl` | un evento JSON per riga su stderr **mentre** la scansione avviene |
| `--language uk\|it\|en` | lingua del report; altrimenti dedotta dalle pagine |
| `--project NOME` | un progetto dentro una cartella che ne contiene più d'uno, per nome o percorso |
| `--start-command CMD`, `--dev-server-port N` | cosa eseguire al posto dello script rilevato, e la porta da attendere |
| `--no-session` | leggere un sito come lo vede un estraneo, ignorando l'accesso memorizzato |
| `--profile-defaults` | attivare ciò che lo stack rilevato chiede (vedi sotto) |

## Cosa controlla

**Testo scritto da un modello.** Il passaggio offline legge il ritmo delle
frasi, la struttura ripetuta e i cliché, e nomina la frase che ha riconosciuto,
così con un risultato si può discutere. Per un secondo parere ci sono un
passaggio a embedding e uno giudicato da un modello. Nulla di ciò è prova di
paternità.

**Caratteri non da tastiera.** Caratteri a larghezza zero, omoglifi, spazi
insoliti, lettere stilizzate e caratteri tipografici - ciascuno esatto e
ciascuno correggibile sul posto.

**Regole del sito**, per categoria, con il numero che la suite verifica:

`accessibility` (40), `best-practices` (13), `geo` (2), `performance` (8), `security` (10), `seo` (8)

Una regola gira dove significa qualcosa e da nessun'altra parte, e a deciderlo
è una prova: la sintassi del file (le regole JSX solo in `.jsx`/`.tsx`), a cosa
serve il documento (le regole email solo su un'email) e quale stack il progetto
ha provato su disco (la regola di escaping WordPress solo in WordPress). In un
file React le regole leggono il componente come è scritto: due elementi su rami
diversi di una condizione, di `cond &&` / `!cond &&` o in `return` separati non
sono un id duplicato, il testo nel codice (`JSON.parse`, `CSS.escape`) non è
testo, un componente del design system con la prop `label` ha un nome, e i
selettori sono il percorso JSX (`section.card > div.list > img`). Un `aria-label`,
`placeholder`, `title` o `alt` letterale in un file che traduce gli altri testi
è segnalato come `advisory` (`jsx-untranslated-literal`).

**Scritte per ciò che un audit manuale ha trovato.** Un `alt` in forma di slug
(`mappa-parlante-palmanova`, `Piazza-Grande`, una data) e non solo un nome di
file con estensione; un video YouTube, Vimeo o simile incorporato, di cui la
pagina non dice nulla su sottotitoli, trascrizione e audiodescrizione (1.2.2,
1.2.3, 1.2.5); un pulsante «carica altri» in una pagina senza live region
(4.1.3); e, su un sito multilingue scansionato, un link che nella traduzione
porta altrove rispetto all'originale (2.4.4). I controlli su video, live region
e link tradotti sono `advisory`: indicano dove deve guardare una persona, non
che la pagina sia bocciata. I link elencati in un altro ordine nella traduzione
si confrontano per parole e destinazione, non per posizione. Gli indirizzi di
ricerca e filtro il cui canonical non punta a sé stessi sono esclusi dal
controllo di reciprocità hreflang e contati in una riga; un link che
HTML_CodeSniffer segnala come immagine senza `alt` ma che ha un nome da
`aria-label`, `aria-labelledby` o `title` è un promemoria per verificare il nome,
non una violazione.

**Nel browser**, quando ce n'è uno: axe-core e HTML_CodeSniffer, la pagina nello
stato in cui la mette una persona - indicatore di focus e se si distingue dallo
sfondo (3:1), se un'intestazione fissa copre l'elemento a fuoco (2.4.11),
trappole da tastiera, ordine di focus, contenuto solo in hover, una modale
aperta, il percorso del modulo, la dimensione di ogni bersaglio del puntatore e
lo spazio attorno (2.5.8, misurati da axe-core con il riquadro e il bersaglio più
vicino nella segnalazione) - e la stessa pagina a più larghezze. Legge e non
agisce mai: nulla viene digitato, cliccato o inviato. Nell'app desktop la pagina
nascosta non può prendere il focus della finestra senza toglierlo alla finestra
principale, quindi i tre controlli sul focus riportano lì `focus-not-measured`
(visibile con `--unsettled`); la riga di comando li misura. Ogni segnalazione
porta i criteri WCAG a cui contribuisce, nel rapporto e in `--json` (`wcag`).

**Provenienza, non verdetti.** Campi IPTC/XMP e manifest C2PA in ogni immagine a
cui la pagina rimanda (di ciascuna si scaricano solo i primi 512 KB), e i fatti
del repository: file `.env` tracciati, commit col nome di un assistente,
configurazione di un assistente committata. Riportati come fatti sull'origine,
mai come difetti.

**Certezza.** Ogni risultato è `exact`, `needs-browser` o `advisory`. Ciò che non
è deciso non viene elencato per impostazione predefinita - su una pagina reale
erano 312 risultati di contrasto su 348 - e l'esecuzione dice quanti ne ha
lasciati fuori. `--unsettled` li riporta, `--confidence exact` toglie anche
quelli consultivi.

**Problemi distinti, non ripetizioni.** Il titolo del riepilogo, `counts` in
`--json`, la riga di stato della finestra e dell'interfaccia da terminale
contano ogni problema una volta: un'intestazione o uno sprite di icone sta su
ogni pagina, quindi una scansione di 381 pagine erano 15 338 risultati e circa
980 cause. Le occorrenze restano accanto (`occurrences`, `distinct` e
`problems` in `--json`, ognuna con le pagine) e ogni risultato è comunque
nell'elenco. I promemoria «controlla a mano» di HTML_CodeSniffer (nome e testo
visibile, `position: fixed`, immagine ignorata, «usa una lista») e il criterio
WCAG 4.1.1, eliminato, sono `advisory` e `minor`; ciò che il motore ha misurato,
come un rapporto di contrasto, mantiene il suo peso.

**Il server di un sito locale non è un difetto del progetto.** Su `localhost`,
`*.local`, `*.test` o un indirizzo privato, ciò che decide il server e che
l'HTTP semplice rende inevitabile non finisce nell'elenco ma viene contato:
intestazioni `Content-Security-Policy`, `X-Content-Type-Options`,
`Referrer-Policy`, `X-Frame-Options`, compressione e cache mancanti, `action`
dei moduli con `http://` e il `noindex` di una copia di sviluppo. Una scansione
di un WordPress locale aveva 365 risultati critici che erano tutti moduli con
`http://`. L'esecuzione dice quanti ne ha lasciati fuori (`environment` in
`--json`); `--include-environment` li elenca. Tutto ciò che riguarda la pagina
stessa (uno script di terze parti sincrono, un'immagine, un nome accessibile)
è riportato su un indirizzo locale come su uno pubblico, e l'audit di un
repository non cambia.

## È il bersaglio a decidere cosa chiedere

Un progetto dichiara cosa è, e da questo discende molto più dell'elenco di
cartelle da saltare. Una soluzione SPFx sa di consegnare web part e non sa su
quale sito finiranno. Un'app Vite o Next letta dal disco è fatta di template che
il bundler non ha eseguito, dove `<App />` non è un'intestazione. Un unico file
HTML autonomo non porta ad altre pagine, quindi resta un solo asse: la
larghezza.

Ognuna di queste cose diventa un parametro, e ognuno arriva con lo stack che
l'ha chiesto e con il file che quello stack l'ha provato: «attivato perché …» è
una frase con cui si può non essere d'accordo, non un default silenzioso.
**Quello che impostate voi non viene mai sovrascritto.**

La finestra e il modulo del terminale lo applicano: il controllo è attivo, la
ragione è sotto, un clic lo disattiva. La riga di comando no: è un contratto, e
un'esecuzione che avvia un dev server perché ha trovato un `vite.config.ts` non
sarebbe quella che l'autore dello script ha scritto. Lì le stesse proposte sono
stampate come righe `# [profile]` su stderr, e `--profile-defaults` chiede di
applicarle.

La stessa lettura decide quali campi esistano: `--depth` ha bisogno di un
indirizzo, `--incremental` di file su disco, e un controllo che per questo
bersaglio non raggiunge nulla non viene mostrato né letto, quindi un
`--devserver` attivato per un repository non vi segue su un singolo file.

Una cartella con più progetti viene interrogata invece che fusa in silenzio:
venti soluzioni SPFx in una cartella sono venti artefatti. `--project NOME`, e
il selettore che la finestra e il modulo del terminale mostrano, analizzano uno
solo di essi: la scansione, il file di esclusioni e il dev server lo seguono
insieme, quindi non possono finire per descrivere progetti diversi. Un
repository che ha provato qualcosa di suo resta un progetto solo: `web/` in
Bedrock è la docroot di quel progetto, non un secondo progetto.

**Un monorepo ha più di un dev server, e non sono la stessa esecuzione.** Lo
script `dev` della radice avvia, o orchestra, le applicazioni sotto di essa;
ognuna di queste ha uno script proprio. `--devserver` sceglieva in silenzio.
Ora l'esecuzione dice quale partirebbe e che indicare un progetto avvia quello
del progetto - misurato su un workspace reale, dove la radice dichiara
`workspaces: ["apps/*"]` e ognuna delle quattro applicazioni dichiara il
proprio `dev`. `--start-command` sostituisce lo script dove nessuno dei due va
bene.

## Lavoro consegnato come frammento del sito di qualcun altro

Un **tema o plugin WordPress** viene riconosciuto come lo riconosce WordPress
stesso - l'intestazione `Theme Name:` in `style.css`, `Plugin Name:` nel file PHP
principale - e i suoi template sono letti come frammenti, così nessuno chiede a
`header.php` un link canonico o un `<h1>`.

Una **web part SharePoint** è un sottoalbero di una pagina che appartiene al
tenant. `--within SELETTORE` restringe l'audit a quello e disattiva, con la
ragione stampata, tutto ciò che per costruzione legge l'intero documento. Un
suffisso di classe generato (`root-137`) non va scritto: il selettore viene
ritentato sulla radice. `--repo PERCORSO --web-parts` lavora nell'altro senso:
legge i manifest della soluzione e trova le parti di questo repository ovunque
compaiano sul sito.

Anche il markup dentro un **template literal** viene analizzato. `.ts` e `.js`
sono saltati come file - lì un `<` è un operatore - ma una stringa fra backtick
non è codice, e una web part SPFx classica ci costruisce dentro tutta la propria
interfaccia. Misurato su una soluzione reale: 72 dei suoi 168 file `.ts` e 131
risultati che nessuno aveva mai letto.

## Siti dietro un accesso

`xanalyze login https://example.com/admin` apre un browser vero sul modulo del
sito. 2FA, SSO e captcha funzionano, perché è un browser. XAnalyze non vede mai
un nome utente né una password: si conserva ciò che il sito ha dato a quel
browser, per host, leggibile solo da voi. `--no-session` legge il sito come lo
vede un estraneo; `login --list` e `login --forget HOST` gestiscono ciò che è
memorizzato. Nulla di una sessione arriva mai in un report, in un log o nel
terminale.

La scansione registra anche quando un indirizzo ha risposto con una porta invece
che con una pagina, e lo dice chiaramente: un riepilogo pulito ottenuto solo da
moduli di accesso è l'output più fuorviante che questo strumento possa produrre.

## Report

Ogni comando scrive una cartella datata, per impostazione predefinita in
`~/Documents/XAnalyze/` (`XANALYZE_REPORT_ROOT` la sposta). Un archivio rimasto
in `~/Desktop/XAnalyze/` da una versione precedente viene spostato alla prima
esecuzione, così lo storico che serve al confronto resta dove lo strumento lo
cerca.

```text
XAnalyze/example.com/2026-09-02-0930/
  report.md     briefing raggruppato per un agente
  report.pdf    report per una persona
  timings.md    tempi delle fasi
  changes.md    cosa è cambiato dall'esecuzione precedente
  state.json    stato ripristinabile
```

Ogni documento si apre nominando il comando e i parametri che hanno cambiato ciò
che è stato misurato. Un problema ripetuto è elencato una volta sola, con i suoi
luoghi annidati sotto. `--json` conserva ogni risultato, per la CI.

Per via di questo raggruppamento il riepilogo contiene due unità di misura,
quindi ogni riga dichiara la propria: una categoria conta i **problemi
distinti**, il conteggio dei caratteri conta le **occorrenze**, ed entrambi i
numeri sono stampati sotto la stessa intestazione invece che uno al posto
dell'altro. Cinque problemi tipografici su cinquantadue occorrenze sono due
fatti, non una contraddizione.

## Pilotarlo da un agente

`--json` risponde a lavoro finito. Su un sito di trenta pagine sono minuti di
silenzio, e chi ha avviato la scansione non distingue una scansione lenta da
una bloccata. `--progress jsonl` scrive un oggetto JSON per riga su **stderr**
mentre la scansione avviene, e stdout resta esattamente quello di prima:

```bash
xanalyze fullscan https://example.com --progress jsonl
```

```json
{"event":"run.start","ts":"…","command":"fullscan","target":"https://example.com","version":"0.63.0"}
{"event":"stage","ts":"…","name":"crawl","state":"begin","depth":1,"max_pages":30}
{"event":"page","ts":"…","n":3,"of":30,"url":"https://example.com/pricing","depth":1}
{"event":"stage","ts":"…","name":"crawl","state":"end","pages":12}
{"event":"notice","ts":"…","kind":"authwall","text":"2 address(es) answered with a login wall …"}
{"event":"run.end","ts":"…","exit_code":0,"counts":{…},"documents":31,"sources":12}
```

| `event` | Quando | Campi |
|---|---|---|
| `run.start` | prima riga | `command`, `target`, `version` |
| `stage` | una fase inizia, riferisce l'avanzamento o finisce | `name` (`devserver`, `scan`, `crawl`, `audit`, `browser`, `report`), `state` (`begin`, `progress`, `end`) |
| `page` | ogni pagina letta | `n`, `of`, `url`, `depth` |
| `file` | ogni file aperto | `n`, `of`, `path` |
| `notice` | tutto ciò che il terminale avrebbe detto a parole | `kind`, `text` e i campi dell'evento |
| `finding` | uno per risultato, con `--progress jsonl=findings` | `rule`, `severity`, `source`, `line`, `kind` |
| `run.end` | ultima riga | `exit_code`, `counts`, `documents`, `sources` |

Senza il flag non cambia nulla: le stesse righe leggibili, nessun JSON.
`finding` è spento finché non lo si chiede, perché su un sito grande sono
decine di migliaia di eventi.

Non è il default, e di proposito: una persona al terminale vuole le frasi, e il
progresso è già acceso - `jsonl` cambia il **formato**, non se la scansione si
racconta. Chi sta leggendo è una proprietà dell'ambiente, non del comando:
imposta `XANALYZE_PROGRESS=jsonl` una volta e ogni scansione in quella shell lo
parla; `--progress human` su un singolo comando vince comunque, così una
scansione resta sempre leggibile a occhio. Una riga che non si legge come JSON non l'ha
scritta XAnalyze - Qt scrive la propria diagnostica sullo stesso flusso -
quindi va saltata, non trattata come un errore.

**I codici di uscita** sono gli stessi per ogni comando:

| Codice | Significato |
|---|---|
| `0` | pulito - il comando ha fatto il suo lavoro e non ha nulla da segnalare |
| `1` | risultati, e solo con `--check`. `scan`/`fix`/`clean`: qualsiasi risultato. `audit`/`fullscan`: uno critico o serio |
| `2` | errore - il comando non poteva essere eseguito: un percorso inesistente, un flag non applicabile, un rilevatore che non ha potuto leggere il testo |
| `3` | incompleto - una scansione si è fermata a metà e il suo lavoro è su disco; `xanalyze resume` la continua |

## Interfacce

**Finestra** (`python main.py`, o l'app). Una schermata di impostazione per il
bersaglio e l'esecuzione, poi l'elenco dei risultati accanto a un'anteprima del
sorgente o della pagina renderizzata, con correzioni, revisione delle
sostituzioni ed esportazione del report. Due larghezze possono stare sullo
schermo insieme, per chiudere la questione «si rompe solo su mobile».

**Terminale** (`xanalyze` senza argomenti). Scan, Audit, Full Scan, Reports,
Settings, Account, Update, Logs. Frecce, scorciatoie numeriche, `Tab`, `Esc` e
`Ctrl+R` per avviare.

Le correzioni meccaniche sono selezionate per impostazione predefinita; le bozze
di un modello richiedono sempre una revisione; le scelte di giudizio, come il
testo alternativo di una fotografia, non sono mai presentate come correzioni
automatiche.

## Configurazione

Le impostazioni stanno in `~/.config/xanalyze/settings.json` (su Windows
`%APPDATA%\xanalyze\settings.json`): lingua, provider, `max_pages`, categorie di caratteri.

`.xanalyze-ignore` nella radice del progetto usa la sintassi di gitignore e può
anche silenziare per regola, selettore o impronta:

```text
vendor/
*.min.js

[rules]
meta-viewport

[fingerprints]
083bea550659aadb  # il testo del logo è già nel link
```

Scartare un risultato con il motivo è un solo comando: `xanalyze ignore
FINGERPRINT --reason "…"`, con l'impronta presa da `audit --json`. Ogni
esecuzione successiva dice quanti risultati le liste hanno nascosto e ne cita i
motivi, così un risultato nascosto non sembra mai una pagina pulita.

## Come le regole dell'audit restano oneste

- **Un corpus di verdetti verificati.** `corpus/audit/verdicts.jsonl` contiene
  difetti reali e falsi positivi noti, con la provenienza di ciascuno. Ogni
  regola serious o critical ne ha almeno uno per tipo, e i test falliscono non
  appena una regola manca il primo o segnala il secondo.
- **Precisione sui tuoi audit.** `python -m audit.precision AUDIT.json
  --template labels.jsonl` elenca i risultati da segnare come veri o falsi;
  `--labels labels.jsonl` stampa la precisione di ogni regola con il numero di
  risultati etichettati accanto, e sotto cinque scrive «not measured».
- **Gli aggiornamenti dei motori si verificano, non si accettano a scatola
  chiusa.** Dopo un aggiornamento di axe o HTML_CodeSniffer, un codice che la
  versione verificata non aveva compare come nota finché qualcuno non lo
  guarda (`python -m audit.engine_codes`).

## Template che comprende

Quattordici linguaggi di template hanno una **coppia** di fixture in
`tests/fixtures/frameworks`: lo stesso componente scritto come il suo framework
dice di scriverlo, e scritto male. La metà corretta non deve produrre risultati
e quella rotta deve produrre quelli giusti, quindi è un'affermazione misurata:

`alpine`, `angular`, `blade`, `django`, `erb`, `handlebars`, `liquid`, `php`, `razor`, `react`, `svelte`, `thymeleaf`, `twig`, `vue`

Il markup in una tecnologia non elencata viene comunque letto - il parser non lo
rifiuta - ma nulla ha dimostrato che un file corretto in quella tecnologia torni
pulito.

**Entrambi i passaggi leggono un template lato server.** Una vista
`.blade.php`, il `.php` di un tema WordPress, un file `.twig`, `.erb`, `.ejs`,
`.phtml` o `.liquid` è markup con un linguaggio server mescolato dentro, quindi
il suo testo viene letto dai passaggi sui pattern AI e sui caratteri
esattamente come lo sarebbe l'`.html` che produce, e il suo markup viene
verificato allo stesso modo. Ciò che il linguaggio di template emette -
`{{ $plan->name }}`, `<?php echo … ?>`, `@endsection` - non è testo e non viene
letto come tale. Un `.php` che è un controller e non una vista resta codice:
`$id < 10` è un confronto, non un tag.

## Stack che riconosce

Un progetto viene identificato dai propri file-marcatore, e ciò che risulta
essere decide cosa trattare come codice di altri anziché scritto qui:

`angular`, `astro`, `bedrock`, `beehiiv`, `carrd`, `craft`, `django`, `docusaurus`, `dotnet`, `drupal`, `eleventy`, `ember`, `flutter`, `gatsby`, `ghost`, `hugo`, `jekyll`, `joomla`, `laravel`, `magento`, `nextjs`, `nuxt`, `qwik`, `rails`, `remix`, `shopify`, `silverstripe`, `spfx`, `spring`, `squarespace`, `statamic`, `storybook`, `sveltekit`, `symfony`, `typo3`, `vite`, `wagtail`, `webflow`, `wix`, `wordpress`, `wordpress-plugin`, `wordpress-theme`

Il rilevamento è una prova: un profilo nomina il file che lo ha dimostrato, le
esclusioni che ne derivano sono dichiarate e non applicate in silenzio, e un
clic le annulla.

## Limiti

- Il rilevamento del testo AI dipende dal corpus. Non è prova di paternità, e i
  giudizi di un modello non sono deterministici.
- **Il rilevamento del testo copre solo ucraino, italiano e inglese.** Un
  passaggio in un'altra lingua viene dichiarato tale e lasciato senza punteggio,
  invece di essere misurato contro liste che quella lingua non la conoscono. I
  controlli sui caratteri e sul sito non dipendono dalla lingua.
- **Il passaggio offline è debole in italiano**: sulla metà trattenuta del corpus
  trova il 36% dei passaggi AI noti, contro il 55% in inglese e il 71% in
  ucraino, mentre l'embedding trova 100%, 85% e 86%. Un'esecuzione su pagine
  italiane lo dice e nomina il detector migliore.
- La scansione di una cartella non vede il contenuto che esiste solo dopo il
  rendering. Usate un URL o `--devserver`.
- Una sola larghezza non descrive il comportamento responsive. Usate
  `--breakpoints all`.
- Uno schema di colori per esecuzione: un sito con tema scuro richiede una
  seconda esecuzione con `--color-scheme dark`.
- I controlli tipografici possono segnalare punteggiatura voluta
  (`--no-typography`).
- La lettura C2PA richiede i pacchetti opzionali `c2pa-python` e `cryptography`.

## Costruire una release

```bash
make version        # cosa dice config.py
make rebuild        # l'unico bundle: finestra, CLI e TUI, a quella versione
make package        # XAnalyze.app.zip e il suo manifest, ciò che `xanalyze update` cerca
```

`make package` si rifiuta di lavorare su un bundle non aggiornato. L'archivio
non è ancora firmato né notarizzato.

## Requisiti

Python 3.13+ (la CI e la release macOS usano 3.14; 3.13 è verificato
su Windows 11), PySide6 per la finestra, QtWebEngine per il rendering,
sentence-transformers per il detector a embedding, `c2pa-python` e `cryptography`
per la lettura C2PA opzionale.

## Licenza

MIT
