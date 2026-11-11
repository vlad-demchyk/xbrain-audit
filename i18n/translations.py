"""UI string translations for uk / it / en.

Add a new UI language by adding one more dict entry — the UI code never
hardcodes strings, it always looks them up through `t(key)`.
"""
from __future__ import annotations

LANGUAGES = {"uk": "Українська", "it": "Italiano", "en": "English"}


def report_language(asked: str | None, detected: str | None = None) -> str:
    """The language a report is written in: asked for, detected, or English.

    One owner, because the three surfaces that decide this - `fullscan`,
    `audit` and the report writer - each had their own `or "en"` and none of
    them checked the value. `lang_detect` answers `other` for a page in a
    language this tool has no lists for, and `--language fr` is a value a
    person can type; both used to travel on as the report language, and both
    read as English only because every lookup here falls back to English on
    a missing key. That is an accident where a decision belongs.
    """
    for candidate in (asked, detected):
        if candidate in LANGUAGES:
            return candidate
    return "en"

_STRINGS: dict[str, dict[str, str]] = {
    # Window title only (OS title bar / dock / taskbar) — the in-app header
    # already shows the "XAnalyze" wordmark on its own (see main_window's
    # brand_name label), so this needs the name plus what the app does,
    # not the bare name again.
    "app_title": {
        "uk": "XAnalyze — сканер ознак ШІ в тексті",
        "it": "XAnalyze — scanner di contenuti IA",
        "en": "XAnalyze — AI content scanner",
    },
    "url_label": {
        "uk": "URL:",
        "it": "URL:",
        "en": "URL:",
    },
    "url_label_full": {
        "uk": "URL сторінки",
        "it": "URL della pagina",
        "en": "Page URL",
    },
    "url_placeholder": {
        "uk": "https://example.com",
        "it": "https://example.com",
        "en": "https://example.com",
    },
    "depth_label": {
        "uk": "Глибина:",
        "it": "Profondità:",
        "en": "Depth:",
    },
    "depth_label_full": {
        "uk": "Глибина обходу посилань",
        "it": "Profondità di scansione dei link",
        "en": "Link crawl depth",
    },
    "detector_label": {
        "uk": "Детектор:",
        "it": "Rilevatore:",
        "en": "Detector:",
    },
    # The window no longer asks which detector class to build - it asks which
    # account reads the text, and works the detector out from that plus the
    # method. See `MainWindow._detector_for_request`.
    "provider_label": {
        "uk": "Модель:",
        "it": "Modello:",
        "en": "Model:",
    },
    "provider_label_full": {
        "uk": "Чий акаунт читає текст і платить за прохід моделі.",
        "it": "Quale account legge il testo e paga il passaggio del modello.",
        "en": "Whose account reads the text and pays for the model pass.",
    },
    "provider_anthropic": {
        "uk": "Anthropic (свій ключ)",
        "it": "Anthropic (chiave propria)",
        "en": "Anthropic (own key)",
    },
    "provider_xformat": {
        "uk": "Акаунт xFormat",
        "it": "Account xFormat",
        "en": "xFormat account",
    },
    "provider_claude-code": {
        "uk": "Сесія Claude Code",
        "it": "Sessione Claude Code",
        "en": "Claude Code session",
    },
    "ui_language_label": {
        "uk": "Мова:",
        "it": "Lingua:",
        "en": "Lang:",
    },
    "ui_language_label_full": {
        "uk": "Мова інтерфейсу",
        "it": "Lingua dell'interfaccia",
        "en": "Interface language",
    },
    "analyze_button": {
        "uk": "Аналізувати",
        "it": "Analizza",
        "en": "Analyze",
    },
    "analyze_button_mnemonic": {
        "uk": "&Аналізувати",
        "it": "&Analizza",
        "en": "&Analyze",
    },
    "cancel_button": {
        "uk": "Скасувати",
        "it": "Annulla",
        "en": "Cancel",
    },
    "close": {"uk": "Закрити", "it": "Chiudi", "en": "Close"},
    "cancel_button_mnemonic": {
        "uk": "&Скасувати",
        "it": "A&nnulla",
        "en": "&Cancel",
    },
    "status_idle": {
        "uk": "Готово до роботи",
        "it": "Pronto",
        "en": "Ready",
    },
    "status_crawling": {
        "uk": "Обхід сторінок: {url} (рівень {depth})",
        "it": "Scansione pagina: {url} (livello {depth})",
        "en": "Crawling: {url} (depth {depth})",
    },
    "status_detecting": {
        "uk": "Аналіз тексту детектором «{detector}»…",
        "it": "Analisi del testo con «{detector}»…",
        "en": "Analyzing text with '{detector}'…",
    },
    "status_done": {
        "uk": "Готово: {pages} стор., {blocks} фрагментів, {flags} позначено",
        "it": "Fatto: {pages} pagine, {blocks} blocchi, {flags} segnalati",
        "en": "Done: {pages} pages, {blocks} blocks, {flags} flagged",
    },
    # A repository is measured in files, not pages. The web wording was
    # being used for both, so a scan of four hundred files reported "318
    # pages" - the same slip as the summary line asking a repo result for
    # `pages`.
    "status_done_repo": {
        "uk": "Готово: {pages} файлів, {blocks} фрагментів, {flags} позначено",
        "it": "Fatto: {pages} file, {blocks} blocchi, {flags} segnalati",
        "en": "Done: {pages} files, {blocks} blocks, {flags} flagged",
    },
    "repo_preview_header": {
        "uk": "Файли репозиторія", "it": "File del repository",
        "en": "Repository files",
    },
    "status_error": {
        "uk": "Помилка: {error}",
        "it": "Errore: {error}",
        "en": "Error: {error}",
    },
    "flagged_list_header": {
        "uk": "Позначені фрагменти",
        "it": "Frammenti segnalati",
        "en": "Flagged passages",
    },
    "replace_placeholder": {
        "uk": "Впишіть заміну (лише локальна чернетка)…",
        "it": "Scrivi il testo sostitutivo (solo bozza locale)…",
        "en": "Type a replacement (local draft only)…",
    },
    "replace_save": {
        "uk": "Зберегти чернетку",
        "it": "Salva bozza",
        "en": "Save draft",
    },
    "replace_note": {
        "uk": "Заміна не публікується на сайт — це лише локальний чернетковий варіант для копіювання.",
        "it": "La sostituzione non viene pubblicata sul sito — è solo una bozza locale da copiare.",
        "en": "This replacement is not published to the site — it's a local draft you can copy out.",
    },
    "confidence_low": {"uk": "низька", "it": "bassa", "en": "low"},
    "confidence_medium": {"uk": "середня", "it": "media", "en": "medium"},
    "confidence_high": {"uk": "висока", "it": "alta", "en": "high"},
    "source_page": {
        "uk": "Джерело: {url}",
        "it": "Fonte: {url}",
        "en": "Source: {url}",
    },
    "no_flags": {
        "uk": "Підозрілих фрагментів не знайдено.",
        "it": "Nessun frammento sospetto trovato.",
        "en": "No suspicious passages found.",
    },
    "detector_unavailable": {
        "uk": "Детектор недоступний: {reason}",
        "it": "Rilevatore non disponibile: {reason}",
        "en": "Detector unavailable: {reason}",
    },
    "site_preview_header": {
        "uk": "Копія сторінки",
        "it": "Anteprima della pagina",
        "en": "Page preview",
    },
    "detail_original_label": {
        "uk": "Оригінал:",
        "it": "Originale:",
        "en": "Original:",
    },
    "detail_analyze_button": {
        "uk": "Додатковий аналіз",
        "it": "Analisi aggiuntiva",
        "en": "Additional analysis",
    },
    "detail_analyze_tooltip": {
        "uk": "Запустити повторний аналіз лише цього фрагмента поточним детектором",
        "it": "Riavvia l'analisi solo di questo frammento con il rilevatore attuale",
        "en": "Re-run analysis on just this passage with the current detector",
    },
    "detail_refactor_button": {
        "uk": "Рефактор через мій AI",
        "it": "Rifattorizza con la mia IA",
        "en": "Refactor via my AI",
    },
    "detail_refactor_tooltip": {
        "uk": "Надіслати фрагмент до вашого AI-провайдера для перепису",
        "it": "Invia il frammento al tuo provider IA per la riscrittura",
        "en": "Send this passage to your AI provider for rewriting",
    },
    "detail_analyzing": {
        "uk": "Аналізую фрагмент…",
        "it": "Analisi del frammento…",
        "en": "Analyzing passage…",
    },
    "select_prompt": {
        "uk": "Виберіть фрагмент зі списку зліва",
        "it": "Seleziona un frammento dall'elenco",
        "en": "Select a passage from the list",
    },
    "suppression_note": {
        "uk": "Знахідки, про які ви вже вирішили. Особисті записи діють на всі "
              "проєкти; приберіть запис, щоб побачити цю знахідку знову при "
              "наступному скані.",
        "it": "Rilievi su cui hai già deciso. Le voci personali valgono per "
              "ogni progetto; rimuovine una per rivedere quel rilievo alla "
              "prossima scansione.",
        "en": "Findings you've already decided about. Personal entries apply "
              "to every project; remove one to see that finding again on the "
              "next scan.",
    },
    "suppression_add": {"uk": "Додати", "it": "Aggiungi", "en": "Add"},
    "suppression_remove": {
        "uk": "Прибрати вибране",
        "it": "Rimuovi selezionati",
        "en": "Remove selected",
    },
    "suppression_add_placeholder": {
        "uk": "додати…", "it": "aggiungi…", "en": "add…",
    },
    "suppression_rule_placeholder": {
        "uk": "id правила", "it": "id regola", "en": "rule id",
    },
    "suppression_empty": {"uk": "порожньо", "it": "vuoto", "en": "empty"},
    "suppression_fingerprints": {
        "uk": "Точні знахідки",
        "it": "Rilievi esatti",
        "en": "Exact findings",
    },
    "suppression_fingerprints_hint": {
        "uk": "Одна конкретна знахідка, відхилена один раз - переживає "
              "повторний скан і не впливає ні на що інше.",
        "it": "Un singolo rilievo, ignorato una volta: sopravvive a una nuova "
              "scansione e non tocca nient'altro.",
        "en": "One exact finding, dismissed once - survives a re-scan, "
              "nothing else.",
    },
    "suppression_phrases": {
        "uk": "Фрази",
        "it": "Frasi",
        "en": "Phrases",
    },
    "suppression_phrases_hint": {
        "uk": "Слово або фраза більше ніколи не позначається, ніде.",
        "it": "Una parola o frase non viene più segnalata, da nessuna parte.",
        "en": "A word or phrase never flagged again, anywhere.",
    },
    "suppression_rules": {
        "uk": "Правила",
        "it": "Regole",
        "en": "Rules",
    },
    "suppression_rules_hint": {
        "uk": "Ціла перевірка вимкнена - сигнал стилю, категорія символів або "
              "id правила доступності.",
        "it": "Un intero controllo disattivato: un segnale di stile, una "
              "categoria di caratteri o l'id di una regola di accessibilità.",
        "en": "A whole check switched off - a style signal, a character "
              "category, or an accessibility rule id.",
    },
    "suppression_paths": {
        "uk": "Шляхи",
        "it": "Percorsi",
        "en": "Paths",
    },
    "suppression_paths_hint": {
        "uk": "Файл або шаблон URL повністю виключений з аналізу.",
        "it": "Un file o un pattern di URL escluso completamente dall'analisi.",
        "en": "A file or URL pattern excluded from analysis entirely.",
    },
    "suppression_selectors": {
        "uk": "Селектори",
        "it": "Selettori",
        "en": "Selectors",
    },
    "suppression_selectors_hint": {
        "uk": "Частина сторінки виключена - CSS-селектор.",
        "it": "Una parte della pagina esclusa: un selettore CSS.",
        "en": "A part of the page excluded - a CSS selector.",
    },
    # --- Setup screen (artboard 3b) ----------------------------------------
    "setup_title": {
        "uk": "Новий прогін", "it": "Nuova scansione", "en": "New run",
    },
    "setup_subtitle": {
        "uk": "Офлайн-перевірка нічого не коштує і не надсилає текст нікуди.",
        "it": "Il controllo offline non costa nulla e non invia il testo da "
              "nessuna parte.",
        "en": "The offline check costs nothing and sends the text nowhere.",
    },
    "setup_step_source": {
        "uk": "1 · ЩО ДИВИМОСЬ", "it": "1 · CHE COSA GUARDIAMO",
        "en": "1 · WHAT WE LOOK AT",
    },
    "setup_step_reading": {
        "uk": "2 · ЯК ЧИТАЄМО", "it": "2 · COME LEGGIAMO", "en": "2 · HOW WE READ",
    },
    "setup_step_question": {
        "uk": "3 · ЩО ШУКАЄМО", "it": "3 · CHE COSA CERCHIAMO",
        "en": "3 · WHAT WE LOOK FOR",
    },
    "setup_step_judge": {
        "uk": "4 · ХТО ОЦІНЮЄ", "it": "4 · CHI VALUTA", "en": "4 · WHO JUDGES",
    },
    "setup_source_site_hint": {
        "uk": "обхід за посиланнями", "it": "seguendo i collegamenti",
        "en": "following its links",
    },
    "setup_source_repo_hint": {
        "uk": "код як написаний", "it": "il codice come è scritto",
        "en": "the code as written",
    },
    "setup_source_file_hint": {
        "uk": "одна сторінка", "it": "una sola pagina", "en": "one page",
    },
    "setup_depth_zero": {
        "uk": "0 - лише вказана сторінка",
        "it": "0 - solo la pagina indicata",
        "en": "0 - only the page you name",
    },
    "setup_reading_code": {
        "uk": "Код", "it": "Codice", "en": "Code",
    },
    "setup_reading_code_hint": {
        "uk": "розмітка, шаблони, локалі - швидко",
        "it": "markup, template, localizzazioni - veloce",
        "en": "markup, templates, locales - fast",
    },
    "setup_reading_browser": {
        "uk": "У браузері", "it": "Nel browser", "en": "In a browser",
    },
    "setup_reading_browser_hint": {
        "uk": "axe-core, фокус, виміри · +кілька с/стор.",
        "it": "axe-core, focus, misure · +alcuni s/pag.",
        "en": "axe-core, focus, measurements · +a few s/page",
    },
    "setup_reading_note": {
        "uk": "Спосіб читання випливає з джерела, його не обирають: сайт "
              "читається обома, і різниця між прочитаннями сама є знахідкою.",
        "it": "Il modo di leggere segue dalla sorgente e non si sceglie: un "
              "sito viene letto in entrambi i modi, e la differenza fra le "
              "due letture è essa stessa un rilievo.",
        "en": "How a source is read follows from what it is, and is not "
              "chosen: a site is read both ways, and the difference between "
              "the two readings is itself a finding.",
    },
    "setup_check_accessibility_hint": {
        "uk": "{count} правил · WCAG, SEO, швидкість",
        "it": "{count} regole · WCAG, SEO, velocità",
        "en": "{count} rules · WCAG, SEO, speed",
    },
    "setup_check_ai_hint": {
        "uk": "кліше, структура, символи",
        "it": "cliché, struttura, caratteri",
        "en": "clichés, structure, characters",
    },
    "setup_checks_note": {
        "uk": "Обидві читають ті самі сторінки - другий прогін не піде в мережу.",
        "it": "Entrambe leggono le stesse pagine - la seconda scansione non "
              "andrà in rete.",
        "en": "Both read the same pages - a second run will not go to the "
              "network.",
    },
    "setup_checks_one_at_least": {
        "uk": "Прогін без жодного питання нічого не шукає.",
        "it": "Una scansione senza domande non cerca nulla.",
        "en": "A run with neither question asked looks for nothing.",
    },
    "setup_method_local_hint": {
        "uk": "без мережі, без витрат", "it": "senza rete, senza costi",
        "en": "no network, no cost",
    },
    "setup_method_embedding_hint": {
        "uk": "embeddings, локально", "it": "embedding, in locale",
        "en": "embeddings, locally",
    },
    "setup_method_ai_hint": {
        "uk": "модель перевіряє й доповнює",
        "it": "il modello verifica ed estende",
        "en": "the model checks and extends",
    },
    "setup_method_needs_account": {
        "uk": "Потрібен акаунт xFormat або власний ключ.",
        "it": "Serve un account xFormat o una chiave personale.",
        "en": "Needs an xFormat account or your own key.",
    },
    "setup_summary": {
        "uk": "{source} {target}, читати {reading}, шукати {checks}, оцінює {method}",
        "it": "{source} {target}, leggere {reading}, cercare {checks}, valuta {method}",
        "en": "{source} {target}, read {reading}, look for {checks}, judged by {method}",
    },
    "setup_footer": {
        "uk": "Готово до роботи",
        "it": "Pronto",
        "en": "Ready",
    },

    "preview_empty_title": {
        "uk": "Сторінку ще не відкрито",
        "it": "Nessuna pagina ancora aperta",
        "en": "No page opened yet",
    },
    "preview_empty_body": {
        "uk": "Прев'ю показує сторінку, яку відкрив прогін. Вкажіть ціль і "
              "натисніть «Аналізувати», і вона зʼявиться тут.",
        "it": "L'anteprima mostra la pagina aperta da una scansione. Scegli "
              "un obiettivo e premi Analizza, e comparirà qui.",
        "en": "The preview shows the page a run opened. Choose a target and "
              "press Analyze, and it appears here.",
    },

    # --- Noise control (artboard 3k) ---------------------------------------
    "noise_title": {
        "uk": "Що не показувати",
        "it": "Che cosa non mostrare",
        "en": "What not to show",
    },
    "noise_where": {
        "uk": "записується у .xanalyze-ignore сканованої теки, або у ваші "
              "налаштування для скану сайту",
        "it": "scritto nel .xanalyze-ignore della cartella scansionata, o "
              "nelle tue impostazioni per la scansione di un sito",
        "en": "written to .xanalyze-ignore in the scanned folder, or to your "
              "settings for a site scan",
    },
    "settings_tab_noise": {
        "uk": "Винятки", "it": "Eccezioni", "en": "Exceptions",
    },
    "noise_count": {
        "uk": "Зараз приховано записів: {count}",
        "it": "Voci attualmente nascoste: {count}",
        "en": "Currently hidden: {count} entries",
    },
    "noise_open": {
        "uk": "Керування шумом…",
        "it": "Gestione del rumore…",
        "en": "Noise control…",
    },
    "noise_hidden": {
        "uk": "Приховані знахідки",
        "it": "Rilievi nascosti",
        "en": "Hidden findings",
    },
    "noise_hidden_hint": {
        "uk": "приберіть запис, і знахідка повернеться при наступному скані",
        "it": "rimuovi una voce e il rilievo torna alla prossima scansione",
        "en": "remove an entry and the finding comes back on the next scan",
    },
    "noise_hidden_empty": {
        "uk": "Нічого не приховано.",
        "it": "Niente di nascosto.",
        "en": "Nothing is hidden.",
    },
    "noise_restore": {
        "uk": "Повернути", "it": "Ripristina", "en": "Restore",
    },
    "noise_paths": {
        "uk": "Файли й папки", "it": "File e cartelle", "en": "Files and folders",
    },
    "noise_paths_hint": {
        "uk": ".gitignore-подібний синтаксис",
        "it": "sintassi in stile .gitignore",
        "en": "gitignore-like syntax",
    },
    "noise_rules": {
        "uk": "Вимкнені правила", "it": "Regole disattivate",
        "en": "Disabled rules",
    },
    "noise_rules_add": {
        "uk": "+ додати", "it": "+ aggiungi", "en": "+ add",
    },
    "noise_origin_personal": {
        "uk": "особистий запис",
        "it": "voce personale",
        "en": "personal entry",
    },
    "noise_origin_project": {
        "uk": ".xanalyze-ignore",
        "it": ".xanalyze-ignore",
        "en": ".xanalyze-ignore",
    },
    "noise_no_project_file": {
        "uk": "Тека для .xanalyze-ignore не вибрана, тож правки йдуть у ваші "
              "особисті налаштування.",
        "it": "Nessuna cartella scelta per .xanalyze-ignore, quindi le "
              "modifiche vanno nelle tue impostazioni personali.",
        "en": "No folder chosen for a .xanalyze-ignore, so edits go to your "
              "personal settings.",
    },
    "ignore_finding": {
        "uk": "Не показувати цю знахідку",
        "it": "Ignora questo rilievo",
        "en": "Ignore this finding",
    },
    "ignore_finding_hint": {
        "uk": "Приховати саме цю знахідку, щоб вона не поверталась при "
              "повторному скані. Запис іде у .xanalyze-ignore у сканованій "
              "теці, або у ваші налаштування, якщо теки немає (скан сайту).",
        "it": "Nascondi esattamente questo rilievo, così non riappare a una "
              "nuova scansione. Salvato in .xanalyze-ignore nella cartella "
              "scansionata, o nelle tue impostazioni quando non c'è una "
              "cartella (scansione di un sito).",
        "en": "Suppress this exact finding at the fingerprint level, so it "
              "does not reappear on a re-scan. Written to .xanalyze-ignore in "
              "the scanned folder, or to your personal settings when there is "
              "no folder to write into (a web scan).",
    },
    "audit_places": {
        "uk": "Знайдено у {count} місцях",
        "it": "Trovato in {count} punti",
        "en": "Found in {count} places",
    },
    "detail_header": {
        "uk": "Деталі знахідки",
        "it": "Dettagli del rilievo",
        "en": "Finding detail",
    },
    # --- the runs catalogue ---
    "settings_cc_model": {
        "uk": "Модель", "it": "Modello", "en": "Model",
    },
    "settings_cc_effort": {
        "uk": "Зусилля", "it": "Sforzo", "en": "Effort",
    },
    # The run summary strip under the controls (artboard 3a). The counted
    # nouns stay plural in every form: the strip is only ever shown after a
    # run, and a run with one finding still reads as a tally, not a sentence.
    # The run-in-progress column (artboard 3g). "Stages" is a section label
    # over a list, so it stays a bare noun in every language.
    "progress_title": {
        "uk": "Прогін іде", "it": "Esecuzione in corso", "en": "Run in progress",
    },
    "progress_stages": {"uk": "Етапи", "it": "Fasi", "en": "Stages"},
    "progress_log": {"uk": "Лог", "it": "Log", "en": "Log"},
    "stage_crawl": {
        "uk": "Обхід посилань", "it": "Scansione dei link", "en": "Crawling links",
    },
    "stage_extract": {
        "uk": "Витяг тексту", "it": "Estrazione del testo", "en": "Extracting text",
    },
    "stage_browser": {
        "uk": "Прохід у браузері", "it": "Passaggio nel browser",
        "en": "Browser pass",
    },
    "stage_detect": {
        "uk": "Пошук у тексті", "it": "Ricerca nel testo", "en": "Checking the text",
    },
    "stage_scan": {
        "uk": "Читання файлів", "it": "Lettura dei file", "en": "Reading files",
    },
    # The run's documents (artboard 3h). The panel names four files and
    # says which are there, so the strings that explain an absent one carry
    # the reason rather than the fact - "not written" is the part the reader
    # can already see.
    # What to do next, per empty state (artboard 3i). Verbs, because each
    # one is the move that follows from the sentence above it.
    # Two runs against each other (artboard 3n). Three sections, because
    # what was fixed, what appeared and what has not moved are acted on
    # differently - the last one is the list that says whether the current
    # approach to it is working at all.
    # What went wrong, in words (artboard 3m). The body says what it means
    # for the result, because that is the part a person decides on - the
    # evidence line beside it carries the numbers and is not translated.
    "diagnosis_blocked_title": {
        "uk": "Сайт не віддає сторінки",
        "it": "Il sito non restituisce le pagine",
        "en": "The site is not serving pages",
    },
    "diagnosis_blocked_body": {
        "uk": "На {refused} з {total} адрес сервер відмовив. Ці сторінки ніхто не "
              "прочитав, тож чистий результат по них нічого не означає.",
        "it": "Il server ha rifiutato {refused} indirizzi su {total}. Quelle "
              "pagine non sono state lette, quindi un risultato pulito su di "
              "esse non significa nulla.",
        "en": "The server refused {refused} of {total} addresses. Nobody read "
              "those pages, so a clean result on them means nothing.",
    },
    "diagnosis_unreachable_title": {
        "uk": "Частина адрес не відповіла",
        "it": "Alcuni indirizzi non hanno risposto",
        "en": "Some addresses did not answer",
    },
    "diagnosis_unreachable_body": {
        "uk": "{count} з {total} сторінок не вдалося завантажити. Решта пройшла; "
              "ці лишились непрочитаними.",
        "it": "{count} pagine su {total} non si sono caricate. Le altre sono "
              "passate; queste sono rimaste non lette.",
        "en": "{count} of {total} pages would not load. The rest went through; "
              "these stayed unread.",
    },
    "diagnosis_render_failed_title": {
        "uk": "Браузер не зміг відкрити сторінку",
        "it": "Il browser non ha aperto la pagina",
        "en": "The browser could not open the page",
    },
    "diagnosis_render_failed_body": {
        "uk": "Рендер {count} з {total} сторінок не завершився. Вони лишились "
              "тільки з кодовим проходом, тож текст, який домальовує JavaScript, "
              "там не перевірявся.",
        "it": "Il rendering di {count} pagine su {total} non e riuscito. Restano "
              "solo con la lettura del codice, quindi il testo aggiunto da "
              "JavaScript non e stato controllato.",
        "en": "Rendering did not finish for {count} of {total} pages. They are "
              "left with the code pass only, so any text JavaScript draws was "
              "not checked.",
    },
    "diagnosis_truncated_title": {
        "uk": "Обхід обрізано лімітом",
        "it": "La scansione si e fermata al limite",
        "en": "The crawl stopped at its limit",
    },
    "diagnosis_truncated_body": {
        "uk": "Прочитано {read} сторінок, а знайдено щонайменше {at_least}. "
              "Чистий результат по решті нічого не означає: їх ніхто не читав.",
        "it": "Lette {read} pagine su almeno {at_least} trovate. Un risultato "
              "pulito sulle altre non significa nulla: nessuno le ha lette.",
        "en": "Read {read} pages of at least {at_least} found. A clean result on "
              "the rest means nothing: nobody read them.",
    },
    "diagnosis_truncated_evidence": {
        "uk": "максимум сторінок за прогін: {limit}",
        "it": "massimo di pagine per esecuzione: {limit}",
        "en": "max pages per run: {limit}",
    },
    "diagnosis_media_unchecked_title": {
        "uk": "Частину зображень не перевірено",
        "it": "Alcune immagini non sono state controllate",
        "en": "Some images were not checked",
    },
    "diagnosis_media_unchecked_body": {
        "uk": "Перевірено {checked} із {found} зображень. Решту ніхто не "
              "відкривав, тож про них не сказано нічого: це не те саме, що "
              "подивитись і нічого не знайти.",
        "it": "Controllate {checked} immagini su {found}. Le altre non le ha "
              "aperte nessuno, quindi su di esse non e stato detto nulla: non "
              "e lo stesso che guardare e non trovare niente.",
        "en": "Checked {checked} of {found} images. Nobody opened the rest, so "
              "nothing has been said about them - which is not the same as "
              "looking and finding nothing.",
    },
    "diagnosis_media_unchecked_evidence": {
        "uk": "не перевірено: {unchecked}",
        "it": "non controllate: {unchecked}",
        "en": "not checked: {unchecked}",
    },
    "diagnosis_browser_incomplete_title": {
        "uk": "Браузерний прохід завершився не повністю",
        "it": "Il passaggio nel browser non e completo",
        "en": "The browser pass is incomplete",
    },
    "diagnosis_browser_incomplete_body": {
        "uk": "Не завершилось перевірок: {count}. Статичний результат лишається "
              "чинним, але чистим результатом повного аудиту це не є.",
        "it": "Controlli non completati: {count}. Il risultato statico resta "
              "valido, ma non rappresenta un audit completo e pulito.",
        "en": "Checks that did not finish: {count}. The static result remains "
              "valid, but this is not a complete clean audit.",
    },
    "diagnosis_unknown_failure_title": {
        "uk": "Прогін зупинився", "it": "L'esecuzione si e fermata",
        "en": "The run stopped",
    },
    "diagnosis_unknown_failure_body": {
        "uk": "Причина не розпізнана, тож нижче те, що сказав сам прогін.",
        "it": "La causa non e riconosciuta, quindi sotto c'e cio che ha detto "
              "l'esecuzione stessa.",
        "en": "The cause was not recognised, so below is what the run itself "
              "said.",
    },
    "diagnosis_retry": {
        "uk": "Спробувати ще раз", "it": "Riprova", "en": "Try again",
    },
    "diagnosis_raise_limit": {
        "uk": "Підняти до {n}", "it": "Alza a {n}", "en": "Raise to {n}",
    },
    "diagnosis_dismiss": {
        "uk": "Сховати", "it": "Nascondi", "en": "Dismiss",
    },
    "comparison_fixed": {
        "uk": "Виправлено", "it": "Corretto", "en": "Fixed",
    },
    "comparison_appeared": {
        "uk": "Зʼявилось", "it": "Comparso", "en": "Appeared",
    },
    "comparison_unchanged": {
        "uk": "Лишилось без змін", "it": "Invariato", "en": "Unchanged",
    },
    "comparison_places": {
        "uk": "{n} місць", "it": "{n} punti", "en": "{n} places",
    },
    "comparison_runs": {
        "uk": "{n} прогонів", "it": "{n} esecuzioni", "en": "{n} runs",
    },
    "comparison_solved": {
        "uk": "Перестали спрацьовувати повністю: {rules}",
        "it": "Non si attivano piu affatto: {rules}",
        "en": "Stopped firing entirely: {rules}",
    },
    "comparison_new_rules": {
        "uk": "Правила, яких раніше не було: {rules}",
        "it": "Regole che prima non c'erano: {rules}",
        "en": "Rules that were not there before: {rules}",
    },
    "comparison_oldest_first": {
        "uk": "Спершу те, що висить найдовше: саме воно є приводом змінити підхід, "
              "а не спробувати ще раз",
        "it": "Prima cio che dura da piu tempo: e questo il motivo per cambiare "
              "approccio, non per riprovare",
        "en": "Longest-standing first: that is what argues for changing the "
              "approach rather than trying again",
    },
    "comparison_measurements": {
        "uk": "Вимірювання, а не перевірки, тому не рахуються ні як виправлене, "
              "ні як нове: {rules}",
        "it": "Misurazioni, non controlli, quindi non contano ne come corretto "
              "ne come nuovo: {rules}",
        "en": "Measurements, not checks, so they count as neither fixed nor "
              "new: {rules}",
    },
    "comparison_measurement_unknown": {
        "uk": "вимірювання швидкодії",
        "it": "misurazione delle prestazioni",
        "en": "performance measurement",
    },
    "comparison_document": {
        "uk": "Відкрити changes.md", "it": "Apri changes.md",
        "en": "Open changes.md",
    },
    "comparison_title": {
        "uk": "Що змінилось", "it": "Cosa e cambiato", "en": "What changed",
    },
    "comparison_open": {
        "uk": "Що змінилось", "it": "Cosa e cambiato", "en": "What changed",
    },
    "empty_action_target": {
        "uk": "Обрати ціль", "it": "Scegli un obiettivo", "en": "Choose a target",
    },
    "empty_action_runs": {
        "uk": "Минулий прогін", "it": "Esecuzione precedente", "en": "A past run",
    },
    "empty_action_ai": {
        "uk": "Додати AI-прохід", "it": "Aggiungi il passaggio AI",
        "en": "Add the AI pass",
    },
    "empty_action_report": {
        "uk": "Зберегти звіт", "it": "Salva il report", "en": "Save the report",
    },
    "empty_action_open_page": {
        "uk": "Відкрити сторінку", "it": "Apri la pagina", "en": "Open the page",
    },
    "documents_title": {
        "uk": "Документи прогону", "it": "Documenti dell'esecuzione",
        "en": "Run documents",
    },
    "documents_open": {
        "uk": "Відкрити теку", "it": "Apri la cartella", "en": "Open folder",
    },
    "documents_back": {
        "uk": "До перегляду", "it": "Torna all'anteprima",
        "en": "Back to preview",
    },
    "documents_timings": {
        "uk": "Скільки тривали етапи", "it": "Quanto sono durate le fasi",
        "en": "Where the time went",
    },
    "documents_handoff": {
        "uk": "report.pdf читає людина, report.md читає агент, timings.md "
              "пояснює тривалість. Один прогін, одна тека: наступний ляже "
              "поруч і додасть changes.md.",
        "it": "report.pdf si legge, report.md lo legge un agente, timings.md "
              "spiega la durata. Un'esecuzione, una cartella: la prossima si "
              "affianca e aggiunge changes.md.",
        "en": "report.pdf is for a person, report.md is for an agent, "
              "timings.md explains the duration. One run, one folder: the "
              "next one lands beside it and adds changes.md.",
    },
    "documents_absent_first_run": {
        "uk": "перший прогін цієї цілі", "it": "prima esecuzione di questo obiettivo",
        "en": "first run of this target",
    },
    "documents_absent_not_comparable": {
        "uk": "немає порівнянного прогону", "it": "nessuna esecuzione confrontabile",
        "en": "no comparable run",
    },
    "documents_absent_no_audit": {
        "uk": "доступність не перевірялась", "it": "accessibilita non verificata",
        "en": "accessibility was not checked",
    },
    # `{noun}` rather than a fixed plural. The line reads "1 знахідок" in
    # every language otherwise, and it is read far more often since the
    # category and certainty filters made the number change under the
    # reader's hand.
    "summary_findings": {
        "uk": "{count} {noun}",
        "it": "{count} {noun}",
        "en": "{count} {noun}",
    },
    # The file column of a repository scan (artboard 3f). Files with
    # nothing in them are counted, not listed: four hundred rows with a zero
    # beside them is a directory listing.
    "repo_files_title": {"uk": "Файли", "it": "File", "en": "Files"},
    "repo_files_clean": {
        "uk": "{count} файлів без знахідок",
        "it": "{count} file senza riscontri",
        "en": "{count} files with no findings",
    },
    "summary_files": {
        "uk": "{count} файлів", "it": "{count} file", "en": "{count} files",
    },
    "summary_skipped_ignored": {
        "uk": "{count} пропущено за .xanalyze-ignore",
        "it": "{count} saltati per .xanalyze-ignore",
        "en": "{count} skipped by .xanalyze-ignore",
    },
    "summary_in_files": {
        "uk": "у {count} файлах", "it": "in {count} file",
        "en": "in {count} files",
    },
    "summary_pages": {
        "uk": "{count} стор.",
        "it": "{count} pag.",
        "en": "{count} pages",
    },
    "summary_documents": {
        "uk": "{count} документів",
        "it": "{count} documenti",
        "en": "{count} documents",
    },
    "runs_title": {
        "uk": "Прогони:",
        "it": "Esecuzioni:",
        "en": "Runs:",
    },
    "runs_empty": {
        "uk": "Ще немає збережених прогонів",
        "it": "Nessuna esecuzione registrata",
        "en": "No runs recorded yet",
    },
    "runs_resume": {
        "uk": "Продовжити",
        "it": "Riprendi",
        "en": "Resume",
    },
    "runs_pause": {
        "uk": "Пауза",
        "it": "Pausa",
        "en": "Pause",
    },
    "runs_open": {
        "uk": "Відкрити теку",
        "it": "Apri cartella",
        "en": "Open folder",
    },
    "runs_status_running": {"uk": "виконується", "it": "in corso",
                            "en": "running"},
    "runs_status_paused": {"uk": "на паузі", "it": "in pausa", "en": "paused"},
    "runs_status_failed": {"uk": "зупинено", "it": "interrotta",
                           "en": "stopped"},
    "runs_status_interrupted": {"uk": "перервано", "it": "interrotta",
                                "en": "interrupted"},
    "runs_status_done": {"uk": "завершено", "it": "completata",
                         "en": "complete"},
    "devserver_confirm": {
        "uk": "{stack}: залежності відсутні в {repo}. Встановити їх і запустити сервер?",
        "it": "{stack}: dipendenze mancanti in {repo}. Installarle e avviare il server?",
        "en": "{stack}: dependencies are missing in {repo}. Install them and start the server?",
    },
    "devserver_starting": {
        "uk": "Запускаю сервер розробки…",
        "it": "Avvio il server di sviluppo…",
        "en": "Starting the dev server…",
    },
    "devserver_ready": {
        "uk": "Сервер готовий: {url}",
        "it": "Server pronto: {url}",
        "en": "Server ready: {url}",
    },
    "devserver_failed": {
        "uk": "Сервер не запущено ({reason}); скановано як звичайний код",
        "it": "Server non avviato ({reason}); scansionato come codice statico",
        "en": "The dev server did not start ({reason}); scanned statically instead",
    },
    # The catalogue as a table (artboard 3c). Column heads, the subtitle
    # that tells two runs of one target apart, and the footer that says the
    # list is a window onto the disk rather than the whole of it.
    "runs_col_target": {"uk": "ЦІЛЬ", "it": "OBIETTIVO", "en": "TARGET"},
    "runs_col_state": {"uk": "СТАН", "it": "STATO", "en": "STATE"},
    "runs_col_stage": {"uk": "ЕТАП", "it": "FASE", "en": "STAGE"},
    "runs_col_found": {"uk": "ЗНАХІДОК", "it": "RISCONTRI", "en": "FOUND"},
    "runs_col_when": {"uk": "КОЛИ", "it": "QUANDO", "en": "WHEN"},
    "runs_kind_site": {"uk": "сайт", "it": "sito", "en": "site"},
    "runs_kind_repo": {"uk": "репозиторій", "it": "repository",
                       "en": "repository"},
    "runs_depth": {"uk": "глибина {n}", "it": "profondita {n}",
                   "en": "depth {n}"},
    "runs_source": {
        "uk": "читається з тек на диску",
        "it": "letto dalle cartelle su disco",
        "en": "read from the folders on disk",
    },
    "runs_footer": {
        "uk": "Показано {shown} останніх, решта у {root}",
        "it": "Mostrate le ultime {shown}, il resto in {root}",
        "en": "The last {shown} shown, the rest in {root}",
    },
    "runs_more": {"uk": "Ще", "it": "Altro", "en": "More"},
    "runs_report": {"uk": "Звіт", "it": "Report", "en": "Report"},
    "runs_compare": {"uk": "Порівняти", "it": "Confronta", "en": "Compare"},
    "runs_pause_requested": {
        "uk": "Пауза запрошена: прогін спиниться на межі наступного етапу",
        "it": "Pausa richiesta: si fermerà al confine della fase successiva",
        "en": "Pause requested: the run stops at its next phase boundary",
    },
    "runs_resuming": {
        "uk": "Продовжую прогін {run}…",
        "it": "Ripresa dell'esecuzione {run}…",
        "en": "Resuming run {run}…",
    },
    "runs_resume_done": {
        "uk": "Прогін завершено",
        "it": "Esecuzione completata",
        "en": "The run finished",
    },
    "runs_resume_incomplete": {
        "uk": "Прогін знову спинився: деталі в state.md у теці прогону",
        "it": "L'esecuzione si è fermata di nuovo: dettagli in state.md",
        "en": "The run stopped again: see state.md in the run folder",
    },
    "runs_resume_failed": {
        "uk": "Не вдалось продовжити: {reason}",
        "it": "Ripresa non riuscita: {reason}",
        "en": "Could not resume: {reason}",
    },
    "mode_label": {
        "uk": "Джерело:",
        "it": "Origine:",
        "en": "Source:",
    },
    "mode_web": {
        "uk": "Веб-сторінка",
        "it": "Pagina web",
        "en": "Web page",
    },
    # --- the three independent choices -----------------------------------
    #
    # Source, reading, question, judge. Four controls where there used to be
    # one, because they were never one decision.
    "source_site": {
        "uk": "Сайт", "it": "Sito", "en": "Site",
    },
    "source_repo": {
        "uk": "Репозиторій", "it": "Repository", "en": "Repository",
    },
    "source_file": {
        "uk": "Файл HTML", "it": "File HTML", "en": "HTML file",
    },
    "sign_in_title": {
        "uk": "Акаунт xFormat",
        "it": "Account xFormat",
        "en": "xFormat account",
    },
    "sign_in_hint": {
        "uk": "Вхід дає AI-оцінку за підпискою, без особистого ключа. "
              "Пароль не зберігається - лишаються тільки видані токени.",
        "it": "L'accesso abilita la valutazione AI con l'abbonamento, senza "
              "una chiave personale. La password non viene salvata: restano "
              "solo i token emessi.",
        "en": "Signing in enables the AI assessment on the subscription, with "
              "no personal key. The password is not stored - only the issued "
              "tokens are.",
    },
    "sign_in_switched": {
        "uk": "Увійшли: {detail}. AI-оцінка тепер іде за підпискою.",
        "it": "Accesso effettuato: {detail}. La valutazione AI usa "
              "l'abbonamento.",
        "en": "Signed in: {detail}. The AI assessment now runs on the "
              "subscription.",
    },
    "signed_out_message": {
        "uk": "Вийшли з акаунта. AI-оцінка доступна лише з особистим ключем.",
        "it": "Disconnesso. La valutazione AI richiede una chiave personale.",
        "en": "Signed out. The AI assessment needs a personal key now.",
    },
    "status_reusing_pages": {
        "uk": "Сторінки вже завантажені ({count}), обхід не потрібен",
        "it": "Pagine già scaricate ({count}), nessuna nuova scansione",
        "en": "Pages already fetched ({count}), no new crawl",
    },
    "reader_browser": {
        "uk": "У браузері", "it": "Nel browser", "en": "In a browser",
    },
    "reader_browser_unavailable": {
        "uk": "Репозиторій нічим не віддає сторінку, тож рендерити нічого: "
              "код читається як написаний.",
        "it": "Un repository non serve pagine, quindi non c'è nulla da "
              "renderizzare: il codice si legge come è scritto.",
        "en": "A repository serves no pages, so there is nothing to render: "
              "the code is read as written.",
    },
    "checks_label": {
        "uk": "Оцінка:", "it": "Valutazione:", "en": "Assess:",
    },
    "checks_label_full": {
        "uk": "Що шукати: дефекти доступності й сторінки, ознаки тексту, "
              "написаного моделлю, або і те, і те за один прогін.",
        "it": "Cosa cercare: difetti di accessibilità e di pagina, segni di "
              "testo scritto da un modello, o entrambi in una sola volta.",
        "en": "What to look for: accessibility and page defects, signs of "
              "model-written copy, or both in one run.",
    },
    "check_accessibility": {
        "uk": "Доступність", "it": "Accessibilità", "en": "Accessibility",
    },
    "check_ai_patterns": {
        "uk": "AI-патерни", "it": "Pattern AI", "en": "AI patterns",
    },
    "checks_both": {
        "uk": "Доступність і AI", "it": "Accessibilità e AI",
        "en": "Accessibility and AI",
    },
    "method_label": {
        "uk": "Метод:", "it": "Metodo:", "en": "Method:",
    },
    "method_label_full": {
        "uk": "Хто оцінює: локальний двигун без мережі, лише модель, або "
              "гібрид - локальний прохід, який модель перевіряє й доповнює.",
        "it": "Chi valuta: il motore locale senza rete, solo il modello, o "
              "l'ibrido - il passaggio locale che il modello verifica ed "
              "estende.",
        "en": "Who judges: the offline engine with no network, the model "
              "alone, or the hybrid - the offline pass, checked and extended "
              "by the model.",
    },
    "method_local": {
        "uk": "Локальний двигун", "it": "Motore locale", "en": "Offline engine",
    },
    "method_embedding": {
        "uk": "Семантичний аналіз", "it": "Analisi semantica", "en": "Semantic analysis",
    },
    "method_ai": {
        "uk": "AI", "it": "AI", "en": "AI",
    },
    # "Hybrid", not "both": the two engines no longer run side by side with
    # two lists of findings - the model checks what the offline pass found
    # and adds what it did not, and one merged list comes back. See
    # `detectors/hybrid.py`.
    "method_both": {
        "uk": "Гібрид: локальний і AI",
        "it": "Ibrido: locale e AI",
        "en": "Hybrid: offline and AI",
    },
    "method_ai_unavailable": {
        "uk": "Для AI потрібен ключ або вхід у акаунт xFormat. Прогін іде "
              "локальним двигуном.",
        "it": "L'AI richiede una chiave o l'accesso a un account xFormat. "
              "L'esecuzione usa il motore locale.",
        "en": "The AI pass needs a key or a signed-in xFormat account. "
              "Running the offline engine instead.",
    },
    "mode_repo": {
        "uk": "Репозиторій (код)",
        "it": "Repository (codice)",
        "en": "Repository (code)",
    },
    "fix_on_disk_button": {
        "uk": "Виправити у файлі", "it": "Correggi nel file",
        "en": "Fix in the file",
    },
    "fix_on_disk_tooltip": {
        "uk": "Записати виправлення просто у файли. Перед першою зміною "
              "зберігається копія .bak, тож повернутися можна завжди.",
        "it": "Scrive le correzioni direttamente nei file. Prima della prima "
              "modifica viene salvata una copia .bak, quindi si può sempre "
              "tornare indietro.",
        "en": "Write the corrections straight into the files. A .bak copy is "
              "saved before the first change, so going back is always "
              "possible.",
    },
    "undo_fix_button": {
        "uk": "Відкотити", "it": "Annulla", "en": "Undo",
    },
    "undo_fix_tooltip": {
        "uk": "Повернути файли до стану перед першим виправленням.",
        "it": "Riporta i file allo stato precedente alla prima correzione.",
        "en": "Put the files back the way they were before the first "
              "correction.",
    },
    # One button for two documents; the type is asked at click time. See
    # `MainWindow._on_download_clicked` for why they were not merged into one
    # document as well.
    "reader_browser_empty": {
        "uk": "Браузер відкрив документ, але не побудував жодної розмітки. "
              "Прогін не робився: порожня відповідь не є чистим результатом.",
        "it": "Il browser ha aperto il documento ma non ha costruito alcun "
              "markup. L'analisi non è stata eseguita: una risposta vuota non "
              "è un risultato pulito.",
        "en": "The browser opened the document but built no markup at all. "
              "Nothing was analysed: an empty answer is not a clean result.",
    },
    "download_button": {
        "uk": "Завантажити", "it": "Scarica", "en": "Download",
    },
    "download_tooltip": {
        "uk": "Зберегти звіт: або документ для читання й друку, або брифінг "
              "для агента. Тип запитається після натискання.",
        "it": "Salva un report: il documento da leggere e stampare, oppure il "
              "briefing per l'agente. Il tipo viene chiesto dopo il clic.",
        "en": "Save a report: either the document to read and print, or the "
              "briefing for an agent. The type is asked after the click.",
    },
    "download_which": {
        "uk": "Який звіт зберегти?",
        "it": "Quale report salvare?",
        "en": "Which report do you want?",
    },
    "export_report_button": {
        "uk": "Звіт для агента", "it": "Report per l'agente",
        "en": "Report for an agent",
    },
    "export_report_tooltip": {
        "uk": "Зберегти файл, який можна віддати Claude Code або іншому "
              "агенту: статистика, карта файлів, кожна знахідка з готовим "
              "виправленням і що змінилося з минулого разу.",
        "it": "Salva un file da passare a Claude Code o a un altro agente: "
              "statistiche, mappa dei file, ogni rilievo con la correzione "
              "pronta e che cosa è cambiato dall'ultima volta.",
        "en": "Save a file you can hand to Claude Code or another agent: "
              "statistics, a file map, every finding with its ready "
              "correction, and what changed since last time.",
    },
    "fix_nothing_ready": {
        "uk": "Серед знахідок немає таких, які можна записати автоматично.",
        "it": "Tra i rilievi non ce n'è nessuno scrivibile automaticamente.",
        "en": "None of the findings can be written automatically.",
    },
    "fix_done": {
        "uk": "Записано виправлень: {applied} у {files} файл(ах).",
        "it": "Correzioni scritte: {applied} in {files} file.",
        "en": "Wrote {applied} correction(s) in {files} file(s).",
    },
    "fix_done_by_model": {
        "uk": "Написано моделлю, тож варто прочитати: {rules}.",
        "it": "Scritte da un modello, quindi da rileggere: {rules}.",
        "en": "Written by a model, so worth reading: {rules}.",
    },
    "fix_left_alone": {
        "uk": "Не змінено: {count}. Причини:",
        "it": "Non modificati: {count}. Motivi:",
        "en": "Left alone: {count}. Why:",
    },
    "undo_done": {
        "uk": "Повернуто файлів: {files}.",
        "it": "File ripristinati: {files}.",
        "en": "Restored {files} file(s).",
    },
    "export_report_done": {
        "uk": "Звіт збережено: {path}",
        "it": "Report salvato: {path}",
        "en": "Report saved: {path}",
    },
    "app_tagline": {
        "uk": "текст, символи і аудит сторінки",
        "it": "testo, caratteri e audit della pagina",
        "en": "text, characters and page audit",
    },
    "detail_panel_title": {
        "uk": "Знахідка", "it": "Rilievo", "en": "Finding",
    },
    "detail_line": {"uk": "рядок", "it": "riga", "en": "line"},
    "detail_element": {
        "uk": "Елемент у файлі", "it": "Elemento nel file",
        "en": "The element in the file",
    },
    "detail_replacement": {
        "uk": "Готова заміна", "it": "Sostituzione pronta",
        "en": "Ready replacement",
    },
    "detail_fix_this": {
        "uk": "Виправити це", "it": "Correggi questo", "en": "Fix this one",
    },
    "detail_fix_this_tooltip": {
        "uk": "Записати цю заміну у файл. Копія .bak зберігається перед "
              "першою зміною, тож «Відкотити» поверне все як було.",
        "it": "Scrive questa sostituzione nel file. Prima della prima modifica "
              "viene salvata una copia .bak, quindi «Annulla» riporta tutto "
              "com'era.",
        "en": "Write this replacement into the file. A .bak copy is saved "
              "before the first change, so Undo puts everything back.",
    },
    "detail_needs_decision": {
        "uk": "Це рішення, а не механічна заміна - інструмент не питатиме "
              "мовчки.",
        "it": "Questa è una decisione, non una sostituzione meccanica: lo "
              "strumento non la farà in silenzio.",
        "en": "This is a decision, not a mechanical swap - the tool will not "
              "make it silently.",
    },
    "detail_decide_body": {
        "uk": "Цю заміну не можна записати без рішення:\n\n{reason}\n\n"
              "Дозволити моделі написати значення? Копія .bak зберігається "
              "перед зміною, тож відкотити можна завжди.",
        "it": "Questa sostituzione non può essere scritta senza una "
              "decisione:\n\n{reason}\n\nVuoi che sia un modello a "
              "scrivere il valore? Una copia .bak viene salvata prima della "
              "modifica, quindi si può sempre tornare indietro.",
        "en": "This replacement cannot be written without a decision:\n\n"
              "{reason}\n\nLet a model write the value? A .bak copy is "
              "saved before the change, so it can always be undone.",
    },
    "mode_file": {
        "uk": "Один HTML-файл",
        "it": "Un singolo file HTML",
        "en": "A single HTML file",
    },
    "file_path_placeholder": {
        "uk": "Шлях до сторінки, запакованої в один файл",
        "it": "Percorso della pagina raccolta in un unico file",
        "en": "Path to a page packed into one file",
    },
    "no_file_path": {
        "uk": "Виберіть HTML-файл для аналізу.",
        "it": "Scegli un file HTML da analizzare.",
        "en": "Choose an HTML file to analyse.",
    },
    "all_files": {
        "uk": "Усі файли",
        "it": "Tutti i file",
        "en": "All files",
    },
    "mode_audit": {
        "uk": "Аудит сайту",
        "it": "Audit del sito",
        "en": "Site audit",
    },
    "browser_pass_label": {
        "uk": "У браузері",
        "it": "Nel browser",
        "en": "In a browser",
    },
    "browser_pass_tooltip": {
        "uk": "Завантажити кожну сторінку у справжньому браузері та прогнати "
              "axe-core, HTML_CodeSniffer, перевірку клавіатури і фокуса та "
              "виміри завантаження. Бачить те, що домалював JavaScript, але "
              "додає кілька секунд на сторінку.",
        "it": "Carica ogni pagina in un browser reale ed esegue axe-core, "
              "HTML_CodeSniffer, il controllo di tastiera e focus e le "
              "misurazioni di caricamento. Vede ciò che ha reso JavaScript, "
              "ma aggiunge qualche secondo per pagina.",
        "en": "Load every page in a real browser and run axe-core, "
              "HTML_CodeSniffer, the keyboard and focus pass and the load "
              "measurements. Sees what JavaScript rendered, at a cost of a "
              "few seconds per page.",
    },
    "status_auditing": {
        "uk": "Аудит: {target}",
        "it": "Audit: {target}",
        "en": "Auditing {target}",
    },
    "status_browser_pass": {
        "uk": "У браузері: {url}",
        "it": "Nel browser: {url}",
        "en": "In the browser: {url}",
    },
    "empty_audit_clean_title": {
        "uk": "Перевірено, зауважень немає",
        "it": "Controllato, nessun rilievo",
        "en": "Checked, nothing flagged",
    },
    "empty_audit_clean_body": {
        "uk": "Перевірено документів: {documents}. Це означає лише те, що "
              "правила цього інструмента нічого не знайшли. Автоматична "
              "перевірка ловить меншу частину проблем доступності, тож "
              "чистий результат не є доказом доступності сторінки.",
        "it": "Documenti controllati: {documents}. Significa soltanto che le "
              "regole di questo strumento non hanno trovato nulla. Il "
              "controllo automatico intercetta solo una parte dei problemi "
              "di accessibilità: un esito pulito non è una prova.",
        "en": "Documents checked: {documents}. That means only that this "
              "tool's rules found nothing. Automated checking catches a "
              "minority of accessibility problems, so a clean result is not "
              "proof that the page is accessible.",
    },
    "empty_audit_unreadable_title": {
        "uk": "Сторінки не вдалося прочитати",
        "it": "Pagine non leggibili",
        "en": "The pages could not be read",
    },
    "empty_audit_unreadable_body": {
        "uk": "Нічого не перевірено, бо жодну сторінку не вдалося отримати:",
        "it": "Nulla è stato controllato perché nessuna pagina è stata "
              "ottenuta:",
        "en": "Nothing was checked, because no page could be fetched:",
    },
    "audit_found": {
        "uk": "Що знайдено",
        "it": "Che cosa è stato trovato",
        "en": "What was found",
    },
    "audit_why": {
        "uk": "Чому це проблема",
        "it": "Perché è un problema",
        "en": "Why it is a problem",
    },
    "audit_fix": {
        "uk": "Як виправити",
        "it": "Come correggere",
        "en": "How to fix it",
    },
    "audit_caveat": {
        "uk": "Коли це хибне спрацювання",
        "it": "Quando è un falso positivo",
        "en": "When this is a false positive",
    },
    "status_report_saved": {
        "uk": "Звіт збережено: {path}",
        "it": "Report salvato: {path}",
        "en": "Report saved: {path}",
    },
    "status_run_documents": {
        "uk": "Документи прогону: {path}",
        "it": "Documenti dell'esecuzione: {path}",
        "en": "Run documents: {path}",
    },
    "audit_also_found_by": {
        "uk": "Це саме знайшли також: {engines}",
        "it": "Trovato anche da: {engines}",
        "en": "Also found by: {engines}",
    },
    "repo_path_placeholder": {
        "uk": "Шлях до папки репозиторію",
        "it": "Percorso della cartella del repository",
        "en": "Path to repository folder",
    },
    "browse_button": {
        "uk": "Огляд…",
        "it": "Sfoglia…",
        "en": "Browse…",
    },
    "exclusions_button": {
        "uk": "Фільтр…",
        "it": "Filtro…",
        "en": "Filter…",
    },
    "exclusions_button_full": {
        "uk": "Файли й папки, які виключити з аналізу",
        "it": "File e cartelle da escludere dall'analisi",
        "en": "Files/folders to exclude from analysis",
    },
    "incremental_check": {
        "uk": "Інкрементно",
        "it": "Incrementale",
        "en": "Incremental",
    },
    "incremental_check_full": {
        "uk": "Повторно використати розбір незмінених файлів. Вміст файлів перевіряється знову, а детектор запускається для всього набору.",
        "it": "Riusa l'estrazione dei file invariati. Il contenuto viene ricontrollato e il rilevatore analizza l'intero insieme.",
        "en": "Reuse extraction for unchanged files. File contents are checked again and the detector runs on the full set.",
    },
    "scan_options_button": {
        "uk": "Скан…",
        "it": "Scansione…",
        "en": "Scan…",
    },
    "scan_options_button_full": {
        "uk": "Задати ліміт файлів, розширення та виключення",
        "it": "Imposta limite file, estensioni ed esclusioni",
        "en": "Set file limit, extensions, and exclusions",
    },
    "scan_options_title": {
        "uk": "Що сканувати",
        "it": "Cosa scansionare",
        "en": "What to scan",
    },
    "scan_max_files": {
        "uk": "Максимум файлів",
        "it": "File massimi",
        "en": "Maximum files",
    },
    "scan_extensions": {
        "uk": "Розширення",
        "it": "Estensioni",
        "en": "Extensions",
    },
    "scan_extensions_placeholder": {
        "uk": ".html, .php, .twig",
        "it": ".html, .php, .twig",
        "en": ".html, .php, .twig",
    },
    "scan_extensions_hint": {
        "uk": "Порожнє поле використовує розширення, визначені типом скану. Виключення задаються по одному на рядок.",
        "it": "Lascia vuoto per usare le estensioni previste dal tipo di scansione. Inserisci un'esclusione per riga.",
        "en": "Leave blank to use the extensions for this scan type. Enter one exclusion per line.",
    },
    "scan_exclusions": {
        "uk": "Виключити файли й папки",
        "it": "Escludi file e cartelle",
        "en": "Exclude files and folders",
    },
    "scan_extensions_invalid": {
        "uk": "Введіть розширення на кшталт .html або .php, розділяючи їх комами чи пробілами.",
        "it": "Inserisci estensioni come .html o .php, separate da virgole o spazi.",
        "en": "Enter extensions such as .html or .php, separated by commas or spaces.",
    },
    "auto_devserver_check": {
        "uk": "Автозапуск сервера",
        "it": "Avvio automatico server",
        "en": "Auto-start server",
    },
    "auto_devserver_check_full": {
        "uk": "Аналіз сам виявляє й піднімає сервер розробки репо (package.json, "
             "manage.py, Gemfile+bin/rails). Вимкнено за замовчуванням: сервер "
             "може вже бути запущений деінде",
        "it": "L'analisi rileva e avvia da sola il server di sviluppo del repo "
             "(package.json, manage.py, Gemfile+bin/rails). Disattivo per "
             "default: il server potrebbe già essere in esecuzione altrove",
        "en": "Analyze detects and starts the repo's own dev server "
             "(package.json, manage.py, Gemfile+bin/rails). Off by default: "
             "it may already be running elsewhere",
    },
    "start_server_button": {
        "uk": "Запустити сервер",
        "it": "Avvia server",
        "en": "Start server",
    },
    "start_server_button_full": {
        "uk": "Виявити й підняти сервер розробки цього репо зараз, і сканувати "
             "рендерений сайт",
        "it": "Rileva e avvia ora il server di sviluppo di questo repo, e "
             "scansiona il sito reso",
        "en": "Detect and start this repo's dev server now, and scan the "
             "rendered site",
    },
    "devserver_none_detected": {
        "uk": "Не знайдено package.json, manage.py ані Gemfile+bin/rails у цьому шляху",
        "it": "Nessun package.json, manage.py o Gemfile+bin/rails trovato in questo percorso",
        "en": "No package.json, manage.py, or Gemfile+bin/rails found at this path",
    },
    "devserver_available": {
        "uk": "Знайдено {stack}, статичний скан коду не дає найкращої точності. "
             "Вкажи URL сервера/сайту, увімкни автозапуск, або натисни "
             "«Запустити сервер»",
        "it": "Rilevato {stack}, la scansione statica del codice non dà la "
             "massima precisione. Indica l'URL del server/sito, attiva "
             "l'avvio automatico, o premi «Avvia server»",
        "en": "{stack} detected - a static code scan won't be as accurate. "
             "Give the server/site URL, turn on auto-start, or click "
             "\"Start server\"",
    },
    "exclusions_dialog_title": {
        "uk": "Файли й папки, які не аналізувати (.gitignore-подібний синтаксис)",
        "it": "File e cartelle da non analizzare (sintassi simile a .gitignore)",
        "en": "Files/folders to skip (.gitignore-style)",
    },
    "status_scanning_repo": {
        "uk": "Скануємо: {path}",
        "it": "Scansione: {path}",
        "en": "Scanning: {path}",
    },
    "generate_list_button": {
        "uk": "Сформувати список замін",
        "it": "Genera elenco sostituzioni",
        "en": "Generate replacement list",
    },
    "auto_replace_button": {
        "uk": "Замінити автоматично у файлах",
        "it": "Sostituisci automaticamente nei file",
        "en": "Auto-replace in files",
    },
    "rewriting_status": {
        "uk": "Генерую заміну {done}/{total}…",
        "it": "Generazione sostituzione {done}/{total}…",
        "en": "Generating replacement {done}/{total}…",
    },
    "confirm_auto_replace": {
        "uk": "Це запише зміни у {n} фрагмент(и/ів) прямо у файли коду (перед цим буде створено .bak-копію кожного зміненого файлу). Продовжити?",
        "it": "Questo scriverà le modifiche in {n} frammenti direttamente nei file di codice (verrà creata una copia .bak di ogni file modificato). Continuare?",
        "en": "This will write changes to {n} passage(s) directly into the code files (a .bak copy of each changed file is made first). Continue?",
    },
    "auto_replace_summary": {
        "uk": "Готово. Застосовано: {applied}. Файлів змінено: {files}. Пропущено (застаріло): {stale}. Помилки: {errors}.",
        "it": "Fatto. Applicati: {applied}. File modificati: {files}. Saltati (obsoleti): {stale}. Errori: {errors}.",
        "en": "Done. Applied: {applied}. Files changed: {files}. Skipped (stale): {stale}. Errors: {errors}.",
    },
    "export_list_prompt": {
        "uk": "Зберегти список замін у файл для ручного перегляду?",
        "it": "Salvare l'elenco delle sostituzioni in un file per la revisione manuale?",
        "en": "Save the replacement list to a file for manual review?",
    },
    "export_list_saved": {
        "uk": "Список збережено: {path}",
        "it": "Elenco salvato: {path}",
        "en": "List saved: {path}",
    },

    # --- Replacement list (artboard 3l) ------------------------------------
    # --- Action dialogs (artboard 3j) --------------------------------------
    # --- TUI: the terminal interface speaks the interface language too -----
    # The screens were written in English literals, so `ui_language` - which
    # the window and every report already honour - stopped at the terminal.
    "tui_hint_move": {
        "uk": "Стрілки або Tab - переміщення, Enter - вибір.",
        "it": "Frecce o Tab per spostarsi, Invio per scegliere.",
        "en": "Arrows or Tab to move, Enter to choose.",
    },
    "tui_menu_scan": {
        "uk": "Скан - AI-патерни й символи",
        "it": "Scansione - pattern AI e caratteri",
        "en": "Scan - AI patterns & characters",
    },
    "tui_menu_audit": {
        "uk": "Аудит - доступність, SEO, швидкодія",
        "it": "Audit - accessibilità, SEO, prestazioni",
        "en": "Audit - accessibility, SEO, performance",
    },
    "tui_menu_fullscan": {
        "uk": "Повний прогін - усе за один раз",
        "it": "Scansione completa - tutto in una volta",
        "en": "Full Scan - everything in one run",
    },
    "tui_menu_reports": {
        "uk": "Звіти - попередні прогони",
        "it": "Report - esecuzioni precedenti",
        "en": "Reports - previous analyses",
    },
    "tui_menu_settings": {
        "uk": "Налаштування - конфігурація",
        "it": "Impostazioni - configurazione",
        "en": "Settings - configuration",
    },
    "tui_menu_update": {
        "uk": "Оновлення - перевірити нову версію",
        "it": "Aggiornamento - cerca una nuova versione",
        "en": "Update - check for a new version",
    },
    "tui_menu_uninstall": {
        "uk": "Видалення - прибрати з цієї машини",
        "it": "Disinstalla - rimuovi da questa macchina",
        "en": "Uninstall - remove from this machine",
    },
    "tui_quit": {"uk": "Вийти", "it": "Esci", "en": "Quit"},
    "tui_back": {"uk": "Назад", "it": "Indietro", "en": "Back"},
    "tui_save": {"uk": "Зберегти", "it": "Salva", "en": "Save"},
    "tui_reload": {"uk": "Перечитати", "it": "Ricarica", "en": "Reload"},
    "tui_next": {"uk": "Далі", "it": "Avanti", "en": "Next"},
    "tui_previous": {"uk": "Назад по колу", "it": "Precedente", "en": "Previous"},
    "tui_errors_only": {"uk": "Лише помилки", "it": "Solo errori", "en": "Errors only"},
    "tui_show_all": {"uk": "Показати все", "it": "Mostra tutto", "en": "Show all"},
    "tui_copy": {"uk": "Копіювати", "it": "Copia", "en": "Copy"},
    "tui_palette": {"uk": "Команди", "it": "Comandi", "en": "Commands"},
    "tui_run": {"uk": "Запустити", "it": "Esegui", "en": "Run"},
    "tui_stop": {"uk": "Зупинити", "it": "Ferma", "en": "Stop"},
    "tui_target_path": {
        "uk": "Ціль (файл або тека):",
        "it": "Obiettivo (file o cartella):",
        "en": "Target (file or directory):",
    },
    "tui_target_any": {
        "uk": "Ціль (адреса, тека або файл):",
        "it": "Obiettivo (indirizzo, cartella o file):",
        "en": "Target (address, folder or file):",
    },
    "tui_need_target": {
        "uk": "Вкажіть ціль.",
        "it": "Indica un obiettivo.",
        "en": "Enter a target.",
    },
    "tui_scan_title": {
        "uk": "Скан - AI-патерни й символи",
        "it": "Scansione - pattern AI e caratteri",
        "en": "Scan - AI patterns & characters",
    },
    "tui_scan_run": {"uk": "Запустити скан", "it": "Esegui la scansione", "en": "Run Scan"},
    "tui_scan_of": {"uk": "Скан: {target}", "it": "Scansione: {target}", "en": "Scan of {target}"},
    "tui_label_detector": {"uk": "детектор", "it": "detector", "en": "detector"},
    "tui_detector_offline": {
        "uk": "Локально, безкоштовно",
        "it": "Locale, gratis",
        "en": "Offline, free",
    },
    "tui_detector_embedding": {
        "uk": "Семантично, безкоштовно",
        "it": "Semantico, gratis",
        "en": "Semantic, free",
    },
    "tui_detector_hybrid": {
        "uk": "Гібрид: локальний і AI",
        "it": "Ibrido: locale e AI",
        "en": "Hybrid: offline and AI",
    },
    "tui_detector_judge": {
        "uk": "Лише модель AI, платно",
        "it": "Solo modello AI, a pagamento",
        "en": "AI model only, paid",
    },
    "tui_detector_none": {
        "uk": "Без детектора, лише символи",
        "it": "Senza rilevatore, solo caratteri",
        "en": "No detector, characters only",
    },
    "tui_label_scope": {"uk": "область", "it": "ambito", "en": "scope"},
    "tui_label_depth": {"uk": "глибина", "it": "profondità", "en": "depth"},
    "tui_label_widths": {"uk": "ширини", "it": "larghezze", "en": "widths"},
    "tui_label_language": {"uk": "мова звіту", "it": "lingua del report", "en": "report language"},
    "tui_label_category": {"uk": "категорія", "it": "categoria", "en": "category"},
    "tui_keep_typography": {
        "uk": "Лишити типографіку (не чіпати тире й лапки)",
        "it": "Mantieni la tipografia (non toccare trattini e virgolette)",
        "en": "Keep proper typography (skip em dashes, curly quotes)",
    },
    "tui_incremental": {
        "uk": "Інкрементально - брати кеш для незмінених файлів",
        "it": "Incrementale - riusa la cache per i file non modificati",
        "en": "Incremental - reuse the cache for unchanged files",
    },
    "tui_audit_title": {
        "uk": "Аудит - доступність, SEO, швидкодія",
        "it": "Audit - accessibilità, SEO, prestazioni",
        "en": "Audit - accessibility, SEO, performance",
    },
    "tui_audit_run": {"uk": "Запустити аудит", "it": "Esegui l'audit", "en": "Run Audit"},
    "tui_audit_of": {"uk": "Аудит: {target}", "it": "Audit: {target}", "en": "Audit of {target}"},
    "tui_browser_pass": {
        "uk": "Прохід у браузері (для SPA-сайтів)",
        "it": "Passaggio nel browser (per siti SPA)",
        "en": "Browser rendering (for SPA sites)",
    },
    "tui_ai_pass": {
        "uk": "Прохід моделі (перевіряє alt-тексти, витрачає запити)",
        "it": "Passaggio del modello (controlla gli alt, consuma richieste)",
        "en": "AI pass (checks alt text, costs requests)",
    },
    "tui_autofix": {
        "uk": "Виправляти відоме (пише у файли, лишає .bak)",
        "it": "Correggi il noto (scrive nei file, lascia .bak)",
        "en": "Auto-fix known issues (writes files, keeps .bak)",
    },
    "tui_fullscan_title": {
        "uk": "Повний прогін - усе за один раз",
        "it": "Scansione completa - tutto in una volta",
        "en": "Full Scan - everything in one run",
    },
    "tui_fullscan_run": {
        "uk": "Запустити повний прогін",
        "it": "Esegui la scansione completa",
        "en": "Run Full Scan",
    },
    "tui_fullscan_of": {
        "uk": "Повний прогін: {target}",
        "it": "Scansione completa: {target}",
        "en": "Full scan of {target}",
    },
    "tui_agent_mode": {
        "uk": "Режим агента (офлайн + судить агент)",
        "it": "Modalità agente (offline + giudica l'agente)",
        "en": "Agent mode (offline + agent judges)",
    },
    "tui_no_browser": {
        "uk": "Без браузера (лише статичне читання, значно швидше)",
        "it": "Senza browser (solo lettura statica, molto più veloce)",
        "en": "No browser (static fetch only, much faster)",
    },
    "tui_devserver": {
        "uk": "Запустити dev-сервер, якщо репозиторій його має",
        "it": "Avvia il dev server se il repository ne ha uno",
        "en": "Start the dev server if the repo has one",
    },
    "tui_documents_hint": {
        "uk": "Документи лягають у теку на робочому столі, по теці на ціль.",
        "it": "I documenti finiscono in una cartella per obiettivo sulla "
              "scrivania.",
        "en": "Documents go to a folder per target on your Desktop.",
    },
    "tui_run_starting": {
        "uk": "{title}: старт…", "it": "{title}: avvio…", "en": "{title}: starting…",
    },
    "tui_run_failed": {
        "uk": "Не вдалося: {error}", "it": "Non riuscito: {error}",
        "en": "Failed: {error}",
    },
    "tui_run_done": {"uk": "Готово.", "it": "Fatto.", "en": "Done."},
    "tui_run_failed_code": {
        "uk": "Не вдалося: код виходу {code}. Причина в журналі прогону.",
        "it": "Non riuscito: codice di uscita {code}. Il motivo è nel registro dell'esecuzione.",
        "en": "Failed: exit code {code}. The reason is in the run log.",
    },
    "tui_run_other_active": {
        "uk": "Уже йде інший прогін: {title}. Дочекайтеся його завершення.",
        "it": "È già in corso un'altra esecuzione: {title}. Attendi che finisca.",
        "en": "Another run is in progress: {title}. Wait for it to finish.",
    },
    "tui_language_after_run": {
        "uk": "Мову збережено. Інтерфейс перебудується мовою, коли прогін завершиться: натисніть «Зберегти» ще раз.",
        "it": "Lingua salvata. L'interfaccia si ricostruirà nella nuova lingua quando l'esecuzione sarà finita: premi di nuovo «Salva».",
        "en": "Language saved. The interface is rebuilt in it once the run has finished: press Save again then.",
    },
    "tui_written": {"uk": "Записано:", "it": "Scritti:", "en": "Written:"},
    "tui_nothing_written": {
        "uk": "Цей прогін не записав жодного документа.",
        "it": "Questa esecuzione non ha scritto alcun documento.",
        "en": "No documents were written by this run.",
    },
    "tui_col_what": {"uk": "Що", "it": "Che cosa", "en": "What"},
    "tui_col_count": {"uk": "Скільки", "it": "Quante", "en": "Count"},
    "tui_nothing_selected": {
        "uk": "Нічого не обрано.", "it": "Niente selezionato.",
        "en": "Nothing selected.",
    },
    "tui_no_report_path": {
        "uk": "Цей прогін не записав, куди пішов його звіт.",
        "it": "Questa esecuzione non ha registrato dove è finito il report.",
        "en": "This run did not record where its report went.",
    },
    "tui_no_folder": {
        "uk": "Для цього прогону теки не записано.",
        "it": "Nessuna cartella registrata per questa esecuzione.",
        "en": "No folder recorded for this run.",
    },
    "tui_update_checking": {
        "uk": "Питаю GitHub Releases…", "it": "Interrogo GitHub Releases…",
        "en": "Checking GitHub Releases…",
    },
    "tui_update_check_failed": {
        "uk": "Перевірка не вдалася: {error}",
        "it": "Verifica non riuscita: {error}",
        "en": "Check failed: {error}",
    },
    "tui_update_available": {
        "uk": "Доступна нова версія: {version}",
        "it": "Nuova versione disponibile: {version}",
        "en": "New version available: {version}",
    },
    "tui_update_current": {
        "uk": "Уже остання версія ({version}).",
        "it": "Già aggiornato ({version}).",
        "en": "Already up to date ({version}).",
    },
    "tui_update_current_version": {
        "uk": "Поточна версія: {version}",
        "it": "Versione attuale: {version}",
        "en": "Current version: {version}",
    },
    "tui_update_confirm": {
        "uk": "Натисніть «Встановити» ще раз для підтвердження.",
        "it": "Premi «Installa» di nuovo per confermare.",
        "en": "Press Install again to confirm.",
    },
    "tui_update_installing": {
        "uk": "Встановлюю…", "it": "Installazione…", "en": "Installing…",
    },
    "tui_update_install_failed": {
        "uk": "Встановлення не вдалося: {error}",
        "it": "Installazione non riuscita: {error}",
        "en": "Install failed: {error}",
    },
    "tui_update_press_install": {
        "uk": "Натисніть «Встановити», щоб завантажити і замінити цю "
              "інсталяцію.",
        "it": "Premi «Installa» per scaricare e sostituire questa "
              "installazione.",
        "en": "Press Install to download and replace this installation.",
    },
    "tui_update_unfinished": {
        "uk": "Встановлення не завершилось (код {code}).",
        "it": "L'installazione non è terminata (codice {code}).",
        "en": "Install did not finish (exit {code}).",
    },
    "tui_update_restart": {
        "uk": "Перезапустіть xanalyze, щоб працювала нова версія.",
        "it": "Riavvia xanalyze per usare la nuova versione.",
        "en": "Restart xanalyze to run the new version.",
    },
    "tui_col_when": {"uk": "Коли", "it": "Quando", "en": "When"},
    "tui_col_target": {"uk": "Ціль", "it": "Obiettivo", "en": "Target"},
    "tui_col_mode": {"uk": "Режим", "it": "Modalità", "en": "Mode"},
    "tui_col_findings": {"uk": "Знахідок", "it": "Rilievi", "en": "Findings"},
    "tui_col_problems": {"uk": "Проблем", "it": "Problemi", "en": "Problems"},
    "tui_reports_empty": {
        "uk": "Записаних прогонів ще немає. Спершу запустіть скан, аудит або "
              "повний прогін.",
        "it": "Nessuna esecuzione registrata. Esegui prima una scansione, un "
              "audit o una scansione completa.",
        "en": "No runs recorded yet. Run a scan, audit or full scan first.",
    },
    "tui_reports_count": {
        "uk": "Записано прогонів: {n}.",
        "it": "Esecuzioni registrate: {n}.",
        "en": "{n} run(s) recorded.",
    },
    "tui_report_examined": {
        "uk": "документів прочитано: {documents}   виправлень записано: {fixed}",
        "it": "documenti letti: {documents}   correzioni scritte: {fixed}",
        "en": "documents examined: {documents}   corrections written: {fixed}",
    },
    "tui_report_path": {"uk": "звіт: {path}", "it": "report: {path}", "en": "report: {path}"},
    "tui_report_gone": {
        "uk": "   (на диску його вже немає)",
        "it": "   (non è più su disco)",
        "en": "   (no longer on disk)",
    },
    "tui_report_unrecorded": {
        "uk": "звіт: для цього прогону не записано",
        "it": "report: non registrato per questa esecuzione",
        "en": "report: not recorded for this run",
    },
    "tui_result_title": {
        "uk": "{title} - результат",
        "it": "{title} - risultato",
        "en": "{title} - result",
    },
    "tui_exit_code": {
        "uk": "код виходу {code}", "it": "codice di uscita {code}",
        "en": "exit code {code}",
    },
    "tui_no_summary": {
        "uk": "(машинного підсумку немає)",
        "it": "(nessun riepilogo leggibile dalla macchina)",
        "en": "(no machine-readable summary)",
    },
    "tui_open_gone": {
        "uk": "Цього вже немає: {path}",
        "it": "Non c'è più: {path}",
        "en": "Not there any more: {path}",
    },
    "tui_open_failed": {
        "uk": "Не вдалося відкрити: {error}",
        "it": "Impossibile aprire: {error}",
        "en": "Could not open it: {error}",
    },
    "tui_opened": {"uk": "Відкрито {name}", "it": "Aperto {name}", "en": "Opened {name}"},
    "tui_update_confirm_install": {
        "uk": "Точно встановити?", "it": "Installare davvero?",
        "en": "Really install?",
    },
    "tui_placeholder_path": {
        "uk": "./src або ./page.html", "it": "./src o ./page.html",
        "en": "./src or ./page.html",
    },
    "tui_placeholder_any": {
        "uk": "example.com або ./src", "it": "example.com o ./src",
        "en": "example.com or ./src",
    },
    "tui_placeholder_repo": {
        "uk": "example.com або ./repo", "it": "example.com o ./repo",
        "en": "example.com or ./repo",
    },
    "tui_sum_total_findings": {"uk": "знахідок усього", "it": "rilievi in totale", "en": "total findings"},
    "tui_sum_ai_patterns": {"uk": "AI-патерни", "it": "pattern AI", "en": "AI patterns"},
    "tui_sum_characters": {"uk": "символи", "it": "caratteri", "en": "characters"},
    "tui_sum_accessibility": {"uk": "доступність", "it": "accessibilità", "en": "accessibility"},
    "tui_sum_seo": {"uk": "SEO", "it": "SEO", "en": "SEO"},
    "tui_sum_performance": {"uk": "швидкодія", "it": "prestazioni", "en": "performance"},
    "tui_sum_best_practices": {"uk": "найкращі практики", "it": "buone pratiche", "en": "best practices"},
    "tui_sum_total": {"uk": "усього", "it": "totale", "en": "total"},
    "tui_sum_distinct": {"uk": "різних проблем", "it": "problemi distinti", "en": "distinct problems"},
    "tui_sum_files": {"uk": "файлів", "it": "file", "en": "files"},
    "tui_sum_documents": {"uk": "документів", "it": "documenti", "en": "documents"},
    "tui_reports_title": {"uk": "Звіти", "it": "Report", "en": "Reports"},
    "tui_open_report": {"uk": "Відкрити звіт", "it": "Apri il report", "en": "Open report"},
    "tui_open_folder": {"uk": "Відкрити теку", "it": "Apri la cartella", "en": "Open folder"},
    "tui_refresh": {"uk": "Оновити список", "it": "Aggiorna", "en": "Refresh"},
    "tui_reports_hint": {
        "uk": "Enter або o відкриває обраний звіт.",
        "it": "Invio oppure o apre il report selezionato.",
        "en": "Enter or o opens the selected report.",
    },
    "tui_set_scope": {
        "uk": "Область репозиторія", "it": "Ambito del repository",
        "en": "Repository scope",
    },
    "tui_set_method": {
        "uk": "Метод за замовчуванням", "it": "Metodo predefinito",
        "en": "Default method",
    },
    "tui_set_account": {
        "uk": "Акаунт для AI", "it": "Account per l'AI", "en": "AI account",
    },
    "tui_set_cc_model": {
        "uk": "Модель (Claude Code)", "it": "Modello (Claude Code)",
        "en": "Model (Claude Code)",
    },
    "tui_set_cc_effort": {
        "uk": "Зусилля (Claude Code)", "it": "Sforzo (Claude Code)",
        "en": "Effort (Claude Code)",
    },
    "tui_set_depth": {
        "uk": "Глибина обходу", "it": "Profondità della scansione",
        "en": "Crawl depth",
    },
    "tui_set_max_pages": {
        "uk": "Максимум сторінок за прогін", "it": "Pagine massime per scansione",
        "en": "Max pages per crawl",
    },
    "tui_session_default": {
        "uk": "Як у сесії Claude Code",
        "it": "Come nella sessione Claude Code",
        "en": "Use the Claude Code session setting",
    },
    "tui_model_sonnet": {"uk": "Sonnet", "it": "Sonnet", "en": "Sonnet"},
    "tui_model_opus": {"uk": "Opus", "it": "Opus", "en": "Opus"},
    "tui_model_haiku": {"uk": "Haiku", "it": "Haiku", "en": "Haiku"},
    "tui_effort_low": {"uk": "Низькі", "it": "Basso", "en": "Low"},
    "tui_effort_medium": {"uk": "Середні", "it": "Medio", "en": "Medium"},
    "tui_effort_high": {"uk": "Високі", "it": "Alto", "en": "High"},
    "tui_unlimited": {"uk": "Без обмеження", "it": "Illimitato", "en": "Unlimited"},
    "tui_flag_prefer_cc": {
        "uk": "Використовувати Claude Code, коли запущено в ньому",
        "it": "Usa Claude Code quando è avviato al suo interno",
        "en": "Use Claude Code when run inside it",
    },
    "tui_ro_version": {"uk": "Версія", "it": "Versione", "en": "Version"},
    "tui_ro_model": {"uk": "Модель Claude", "it": "Modello Claude", "en": "Claude model"},
    "tui_ro_categories": {
        "uk": "Категорії символів", "it": "Categorie di caratteri",
        "en": "Character categories",
    },
    "tui_ro_api": {"uk": "API xFormat", "it": "API xFormat", "en": "xFormat API"},
    "tui_col_setting": {"uk": "Налаштування", "it": "Impostazione", "en": "Setting"},
    "tui_col_value": {"uk": "Значення", "it": "Valore", "en": "Value"},
    "tui_settings_title": {"uk": "Налаштування", "it": "Impostazioni", "en": "Settings"},
    "tui_settings_saved": {
        "uk": "Збережено: {what}.",
        "it": "Salvato: {what}.",
        "en": "Saved: {what}.",
    },
    "tui_settings_nothing": {
        "uk": "Нічого не змінилось.",
        "it": "Niente è cambiato.",
        "en": "Nothing changed.",
    },
    "tui_settings_reloaded": {
        "uk": "Перечитано з диска.",
        "it": "Ricaricato dal disco.",
        "en": "Reloaded from disk.",
    },
    "tui_settings_save_failed": {
        "uk": "Не вдалося зберегти: {error}",
        "it": "Impossibile salvare: {error}",
        "en": "Could not save: {error}",
    },
    "tui_settings_language_note": {
        "uk": "Мову змінено - екрани перебудовано.",
        "it": "Lingua cambiata - schermate ricostruite.",
        "en": "Language changed - the screens were rebuilt.",
    },
    "tui_config_file": {
        "uk": "Файл налаштувань: {path}",
        "it": "File di impostazioni: {path}",
        "en": "Config file: {path}",
    },
    "tui_update_title": {"uk": "Оновлення", "it": "Aggiornamento", "en": "Update"},
    "tui_update_check": {
        "uk": "Перевірити оновлення",
        "it": "Cerca aggiornamenti",
        "en": "Check for updates",
    },
    "tui_update_install": {"uk": "Встановити", "it": "Installa", "en": "Install"},
    "tui_uninstall_title": {
        "uk": "Видалення", "it": "Disinstallazione", "en": "Uninstall",
    },
    "tui_uninstall_remove": {
        "uk": "Видалити все", "it": "Rimuovi tutto", "en": "Remove everything",
    },
    "tui_uninstall_confirm": {
        "uk": "Точно видалити все?",
        "it": "Rimuovere davvero tutto?",
        "en": "Really remove everything?",
    },
    "tui_uninstall_kept": {
        "uk": "Лишається: {what}", "it": "Restano: {what}", "en": "Kept: {what}",
    },
    "tui_uninstall_errors": {
        "uk": "Завершено з помилками: {what}",
        "it": "Terminato con errori: {what}",
        "en": "Done with errors: {what}",
    },
    "tui_uninstall_done": {
        "uk": "Видалено записів: {n}.",
        "it": "Rimosse {n} voci.",
        "en": "Uninstalled ({n} item(s)).",
    },
    "tui_uninstall_none": {
        "uk": "XAnalyze не встановлено - видаляти нема чого.",
        "it": "XAnalyze non è installato - non c'è nulla da rimuovere.",
        "en": "XAnalyze is not installed - nothing to remove.",
    },
    "rewrite_progress_title": {
        "uk": "Генерую заміну {done}/{total}",
        "it": "Genero la sostituzione {done}/{total}",
        "en": "Writing replacement {done}/{total}",
    },
    "rewrite_progress_done": {
        "uk": "✓ {name} - готово",
        "it": "✓ {name} - fatto",
        "en": "✓ {name} - done",
    },
    "rewrite_progress_writing": {
        "uk": "· {name} - пишеться…",
        "it": "· {name} - in scrittura…",
        "en": "· {name} - being written…",
    },
    "rewrite_progress_queued": {
        "uk": "· ще {n} у черзі",
        "it": "· altre {n} in coda",
        "en": "· {n} more queued",
    },
    "rewrite_progress_cost": {
        "uk": "{account} · {n} запит(ів) на цей набір",
        "it": "{account} · {n} richieste per questo gruppo",
        "en": "{account} · {n} request(s) for this batch",
    },
    "rewrite_progress_account_unknown": {
        "uk": "оплачуваний акаунт",
        "it": "account a pagamento",
        "en": "the billed account",
    },
    "rewrite_progress_stop": {
        "uk": "Зупинити", "it": "Ferma", "en": "Stop",
    },
    "rewrite_progress_stopping": {
        "uk": "Зупиняю. Те, що вже повернулось, лишається: за нього вже "
              "заплачено.",
        "it": "Interrompo. Ciò che è già tornato resta: è già stato pagato.",
        "en": "Stopping. What already came back is kept: it has been paid "
              "for.",
    },
    "write_confirm_title": {
        "uk": "Записати виправлення у файли?",
        "it": "Scrivere le correzioni nei file?",
        "en": "Write the corrections into the files?",
    },
    "write_confirm_body": {
        "uk": "Це запише зміни у {n} фрагмент(ів) прямо у файли на цій машині.",
        "it": "Questo scrive le modifiche in {n} frammento/i direttamente nei "
              "file su questa macchina.",
        "en": "This writes {n} fragment(s) straight into the files on this "
              "machine.",
    },
    "write_confirm_backup": {
        "uk": "зберегти .bak-копію кожного файла перед першою зміною",
        "it": "salva una copia .bak di ogni file prima della prima modifica",
        "en": "keep a .bak copy of every file before the first change",
    },
    "decision_title": {
        "uk": "Це рішення, а не механічна заміна",
        "it": "Questa è una decisione, non una sostituzione meccanica",
        "en": "This is a decision, not a mechanical replacement",
    },
    "decision_where": {
        "uk": "{where}",
        "it": "{where}",
        "en": "{where}",
    },
    "decision_placeholder": {
        "uk": "напишіть значення самі",
        "it": "scrivi tu il valore",
        "en": "write the value yourself",
    },
    "decision_backup_note": {
        "uk": "Копія .bak зберігається перед зміною, тож відкотити можна завжди.",
        "it": "Una copia .bak viene salvata prima della modifica, quindi si "
              "può sempre annullare.",
        "en": "A .bak copy is kept before the change, so this can always be "
              "undone.",
    },
    "decision_self": {
        "uk": "Я впишу сам", "it": "Lo scrivo io", "en": "I will write it",
    },
    "decision_decorative": {
        "uk": "Позначити декором",
        "it": "Segna come decorativa",
        "en": "Mark it decorative",
    },
    "decision_model": {
        "uk": "Хай напише модель",
        "it": "Lo scriva il modello",
        "en": "Let the model write it",
    },
    "decision_button": {
        "uk": "Вирішити", "it": "Decidi", "en": "Decide",
    },
    "write_done_title": {
        "uk": "Готово", "it": "Fatto", "en": "Done",
    },
    "write_done_applied": {
        "uk": "застосовано", "it": "applicate", "en": "applied",
    },
    "write_done_files": {
        "uk": "файлів змінено", "it": "file modificati", "en": "files changed",
    },
    "write_done_skipped": {
        "uk": "пропущено - фрагмент змінився після скану",
        "it": "saltate - il frammento è cambiato dopo la scansione",
        "en": "skipped - the fragment changed after the scan",
    },
    "write_done_errors": {
        "uk": "помилок", "it": "errori", "en": "errors",
    },
    "write_done_backups": {
        "uk": "Копії лежать поруч із файлами: {first} і ще {rest}.",
        "it": "Le copie sono accanto ai file: {first} e altre {rest}.",
        "en": "The copies are beside the files: {first} and {rest} more.",
    },
    "write_done_undo": {
        "uk": "Відкотити все", "it": "Annulla tutto", "en": "Undo everything",
    },
    "write_done_undone": {
        "uk": "Повернуто файлів: {n}.",
        "it": "File ripristinati: {n}.",
        "en": "Restored {n} file(s).",
    },
    "write_done_show": {
        "uk": "Показати {n} пропущені",
        "it": "Mostra {n} saltate",
        "en": "Show the {n} skipped",
    },
    "write_done_ok": {
        "uk": "Готово", "it": "Fatto", "en": "Done",
    },
    "replacements_source_answered": {
        "uk": "вирішено", "it": "decisa", "en": "answered",
    },
    "replacements_title": {
        "uk": "Список замін",
        "it": "Elenco delle sostituzioni",
        "en": "Replacement list",
    },
    "replacements_summary": {
        "uk": "{mechanical} механічних · {drafts} чернеток моделі · "
              "{decisions} потребують рішення",
        "it": "{mechanical} meccaniche · {drafts} bozze del modello · "
              "{decisions} richiedono una decisione",
        "en": "{mechanical} mechanical · {drafts} model drafts · "
              "{decisions} need a decision",
    },
    "replacements_save": {
        "uk": "Зберегти у файл",
        "it": "Salva su file",
        "en": "Save to file",
    },
    "replacements_write": {
        "uk": "Записати вибрані {n}",
        "it": "Scrivi le {n} selezionate",
        "en": "Write the {n} selected",
    },
    "replacements_footer": {
        "uk": "Позначено {n} з {total} · рішення й чернетки моделі не "
              "записуються без перегляду",
        "it": "Selezionate {n} su {total} · decisioni e bozze del modello non "
              "vengono scritte senza revisione",
        "en": "{n} of {total} selected · decisions and model drafts are not "
              "written without review",
    },
    "replacements_unplanned": {
        "uk": "не стали правкою: {n}",
        "it": "non diventate modifiche: {n}",
        "en": "never became an edit: {n}",
    },
    "replacements_empty": {
        "uk": "Цей прогін не залишив жодної заміни.",
        "it": "Questa esecuzione non ha lasciato alcuna sostituzione.",
        "en": "This run left nothing to replace.",
    },
    "replacements_column_where": {
        "uk": "ДЕ", "it": "DOVE", "en": "WHERE",
    },
    "replacements_column_before": {
        "uk": "БУЛО", "it": "ERA", "en": "WAS",
    },
    "replacements_column_after": {
        "uk": "СТАНЕ", "it": "DIVENTA", "en": "BECOMES",
    },
    "replacements_column_source": {
        "uk": "ДЖЕРЕЛО", "it": "ORIGINE", "en": "SOURCE",
    },
    "replacements_source_mechanical": {
        "uk": "механічне", "it": "meccanica", "en": "mechanical",
    },
    "replacements_source_draft": {
        "uk": "чернетка моделі", "it": "bozza del modello", "en": "model draft",
    },
    "replacements_source_decision": {
        "uk": "рішення", "it": "decisione", "en": "decision",
    },
    "replacements_decision": {
        "uk": "потрібне рішення: {reason}",
        "it": "serve una decisione: {reason}",
        "en": "needs a decision: {reason}",
    },
    "replacements_no_text": {
        "uk": "готової заміни немає",
        "it": "non c'è una sostituzione pronta",
        "en": "there is no ready replacement",
    },
    "replacements_fill": {
        "uk": "Хай модель заповнить {n}",
        "it": "Fai completare {n} al modello",
        "en": "Let the model answer {n}",
    },
    "replacements_filled": {
        "uk": "Модель відповіла на {n}. Ці рядки стали чернетками моделі й "
              "чекають на ваш перегляд.",
        "it": "Il modello ha risposto a {n}. Quelle righe ora sono bozze del "
              "modello e attendono la tua revisione.",
        "en": "The model answered {n}. Those rows are model drafts now, and "
              "wait for you to read them.",
    },
    "replacements_written": {
        "uk": "Записано замін: {written}, файлів: {files}",
        "it": "Sostituzioni scritte: {written}, file: {files}",
        "en": "Written: {written} replacements in {files} files",
    },
    "replacements_left": {
        "uk": "Не записано: {n}",
        "it": "Non scritte: {n}",
        "en": "Not written: {n}",
    },
    # Renamed from `source_file`, which was already the source picker's
    # "HTML file" label. Two different strings under one key, and the later
    # definition won - so the main source dropdown offered a literal
    # "Файл: {path}:{line}" as its third option, in all three languages.
    # `pyflakes` had been reporting the duplicate the whole time.
    "finding_file_line": {
        "uk": "Файл: {path}:{line}",
        "it": "File: {path}:{line}",
        "en": "File: {path}:{line}",
    },
    "no_repo_path": {
        "uk": "Вкажіть шлях до папки репозиторію",
        "it": "Specifica il percorso della cartella del repository",
        "en": "Specify a repository folder path",
    },

    # ----------------------------------------------------------- settings
    "settings_button": {
        "uk": "Налаштування…",
        "it": "Impostazioni…",
        "en": "Settings…",
    },
    "settings_button_mnemonic": {
        "uk": "&Налаштування…",
        "it": "Im&postazioni…",
        "en": "&Settings…",
    },
    "advanced_show": {
        "uk": "Більше…",
        "it": "Altro…",
        "en": "More…",
    },
    "advanced_hide": {
        "uk": "Менше",
        "it": "Meno",
        "en": "Less",
    },
    "settings_title": {
        "uk": "Налаштування",
        "it": "Impostazioni",
        "en": "Settings",
    },
    # --- Settings screen (artboards 3d, 3q) --------------------------------
    "save_button": {
        "uk": "Зберегти", "it": "Salva", "en": "Save",
    },
    "settings_keys_note": {
        "uk": "Ключі зберігаються у keychain системи, не у файлі налаштувань.",
        "it": "Le chiavi sono nel keychain di sistema, non nel file di "
              "impostazioni.",
        "en": "Keys are kept in the system keychain, not in the settings file.",
    },
    "settings_devserver_row": {
        "uk": "Запускати dev-сервер репозиторія",
        "it": "Avvia il dev server del repository",
        "en": "Start the repository's dev server",
    },
    "settings_devserver_note": {
        "uk": "вимкнено, бо ваш `npm run dev` міг уже працювати: другий "
              "сервер на іншому порті плутає, а не допомагає",
        "it": "disattivato perché il tuo `npm run dev` potrebbe essere già "
              "in esecuzione: un secondo server su un'altra porta confonde",
        "en": "off, because your own `npm run dev` may already be running: a "
              "second server on another port confuses rather than helps",
    },
    "settings_as_session": {
        "uk": "як у сесії", "it": "come la sessione", "en": "as the session",
    },
    "effort_low": {
        "uk": "низьке", "it": "basso", "en": "low",
    },
    "effort_medium": {
        "uk": "середнє", "it": "medio", "en": "medium",
    },
    "effort_high": {
        "uk": "високе", "it": "alto", "en": "high",
    },
    "settings_cat_invisible_example": {
        "uk": "U+200B, U+200D, U+FEFF",
        "it": "U+200B, U+200D, U+FEFF",
        "en": "U+200B, U+200D, U+FEFF",
    },
    "settings_cat_space_example": {
        "uk": "U+00A0, U+2009, U+202F",
        "it": "U+00A0, U+2009, U+202F",
        "en": "U+00A0, U+2009, U+202F",
    },
    "settings_cat_homoglyph_example": {
        "uk": "кирилична «а» замість латинської",
        "it": "una «а» cirillica al posto di quella latina",
        "en": "a Cyrillic \u0430 standing in for a Latin a",
    },
    "settings_cat_styled_example": {
        "uk": "математичні й «жирні» юнікод-літери",
        "it": "lettere Unicode matematiche e «in grassetto»",
        "en": "mathematical and \"bold\" Unicode letters",
    },
    "settings_cat_typography_example": {
        "uk": "— «» ’ - часто ставлять свідомо",
        "it": "— «» ’ - spesso sono voluti",
        "en": "— «» ’ - often deliberate",
    },
    "settings_cache_note": {
        "uk": "Кеш суджень моделі: {n} запис(ів) у {path}",
        "it": "Cache dei giudizi del modello: {n} voce/i in {path}",
        "en": "Model judgment cache: {n} entries in {path}",
    },
    "settings_cli_group": {
        "uk": "Команда в терміналі", "it": "Comando nel terminale",
        "en": "Command line",
    },
    "settings_cli_dev_only": {
        "uk": "Доступно лише у зібраному застосунку для macOS, не в цьому "
              "запуску з коду.",
        "it": "Disponibile solo nell'app macOS impacchettata, non in questa "
              "esecuzione dal codice.",
        "en": "Only available in the packaged macOS app, not this development "
              "run.",
    },
    "settings_cli_install": {
        "uk": "Встановити команду «xanalyze»",
        "it": "Installa il comando «xanalyze»",
        "en": "Install the 'xanalyze' command",
    },
    "cli_offer_title": {
        "uk": "Команда «xanalyze» у терміналі",
        "it": "Il comando «xanalyze» nel terminale",
        "en": "The 'xanalyze' command in your terminal",
    },
    "cli_offer_body": {
        "uk": "Цей застосунок уміє працювати і з термінала: скани, аудити та "
              "текстовий інтерфейс. Для цього потрібне посилання «xanalyze» у "
              "{dir}. Встановити зараз? Це можна зробити й пізніше в "
              "налаштуваннях.",
        "it": "Questa app funziona anche da terminale: scansioni, audit e "
              "interfaccia testuale. Serve un collegamento «xanalyze» in "
              "{dir}. Installarlo ora? Puoi farlo anche dopo, dalle "
              "impostazioni.",
        "en": "This app also works from a terminal: scans, audits and the "
              "text interface. That needs an 'xanalyze' link in {dir}. "
              "Install it now? You can also do it later in Settings.",
    },
    "cli_offer_yes": {
        "uk": "Встановити", "it": "Installa", "en": "Install",
    },
    "cli_offer_no": {
        "uk": "Пізніше", "it": "Più tardi", "en": "Later",
    },
    "cli_offer_done": {
        "uk": "Готово: {path}", "it": "Fatto: {path}", "en": "Done: {path}",
    },
    "settings_cli_remove": {
        "uk": "Прибрати команду «xanalyze»",
        "it": "Rimuovi il comando «xanalyze»",
        "en": "Remove the 'xanalyze' command",
    },
    "settings_cli_absent": {
        "uk": "Не встановлено. Додає «xanalyze» у ваш PATH, щоб запускати "
              "скани й аудити з термінала, не відкриваючи це вікно.",
        "it": "Non installato. Aggiunge «xanalyze» al tuo PATH, così puoi "
              "eseguire scansioni e audit da terminale senza aprire questa "
              "finestra.",
        "en": "Not installed. Adds 'xanalyze' to your PATH, so you can run "
              "scans and audits from a terminal without opening this window.",
    },
    "settings_cli_installed": {
        "uk": "Встановлено: {path}.",
        "it": "Installato: {path}.",
        "en": "Installed at {path}.",
    },
    "settings_cli_not_on_path": {
        "uk": " Увага: {dir} схоже не входить у ваш PATH - додайте її у файл "
              "запуску вашої оболонки, щоб команда працювала.",
        "it": " Attenzione: {dir} non sembra essere nel tuo PATH - aggiungila "
              "nel file di avvio della tua shell perché il comando funzioni.",
        "en": " Note: {dir} does not appear to be on your PATH - add it in "
              "your shell's startup file to use the command.",
    },
    "settings_clear_cache": {
        "uk": "Очистити кеш", "it": "Svuota la cache", "en": "Clear the cache",
    },
    "settings_clear_cache_confirm": {
        "uk": "Видалити {path}? Наступний прогін питатиме модель наново.",
        "it": "Eliminare {path}? La prossima esecuzione interrogherà di nuovo "
              "il modello.",
        "en": "Delete {path}? The next run will ask the model again.",
    },
    "settings_uninstall": {
        "uk": "Видалити XAnalyze з цього компʼютера",
        "it": "Rimuovi XAnalyze da questo computer",
        "en": "Remove XAnalyze from this machine",
    },
    "settings_uninstall_confirm": {
        "uk": "Буде видалено:",
        "it": "Verranno rimossi:",
        "en": "This removes:",
    },
    "settings_uninstall_kept": {
        "uk": "Лишається на місці:",
        "it": "Resta al suo posto:",
        "en": "Left in place:",
    },
    "settings_uninstall_nothing": {
        "uk": "Нічого видаляти: на цій машині сліду не знайдено.",
        "it": "Niente da rimuovere: nessuna traccia su questa macchina.",
        "en": "Nothing to remove: no trace of it on this machine.",
    },
    "settings_uninstall_done": {
        "uk": "Видалено записів: {n}.",
        "it": "Voci rimosse: {n}.",
        "en": "Removed {n} item(s).",
    },
    # The three accounts by name. `display_name` on the provider classes is
    # English and belongs to the log and the CLI; a row in a Ukrainian
    # settings screen is not the place it should surface.
    "provider_name_xformat": {
        "uk": "Акаунт xFormat",
        "it": "Account xFormat",
        "en": "xFormat account",
    },
    "provider_name_anthropic": {
        "uk": "Anthropic (свій ключ)",
        "it": "Anthropic (la tua chiave)",
        "en": "Anthropic (your own key)",
    },
    "provider_name_claude-code": {
        "uk": "Сесія Claude Code",
        "it": "Sessione Claude Code",
        "en": "Claude Code session",
    },
    "settings_who_pays": {
        "uk": "ХТО ЧИТАЄ ТЕКСТ І ПЛАТИТЬ",
        "it": "CHI LEGGE IL TESTO E CHI PAGA",
        "en": "WHO READS THE TEXT AND PAYS",
    },
    "settings_account_as": {
        "uk": "вхід виконано: {email}",
        "it": "accesso effettuato: {email}",
        "en": "signed in as {email}",
    },
    "settings_account_none": {
        "uk": "вхід не виконано",
        "it": "nessun accesso",
        "en": "nobody is signed in",
    },
    "settings_account_note": {
        "uk": "AI-прохід за підпискою · пароль не зберігається",
        "it": "passaggio AI con abbonamento · la password non viene salvata",
        "en": "the AI pass runs on the subscription · the password is not kept",
    },
    "settings_account_none_note": {
        "uk": "без входу прогін іде локальним двигуном: знахідок менше, "
              "але він нічого не коштує",
        "it": "senza accesso l'esecuzione usa il motore locale: meno rilievi, "
              "ma non costa nulla",
        "en": "without it a run uses the local engine: fewer findings, and it "
              "costs nothing",
    },
    "settings_key_in_keychain": {
        "uk": "ключ {masked} · keychain",
        "it": "chiave {masked} · keychain",
        "en": "key {masked} · keychain",
    },
    "settings_key_missing": {
        "uk": "ключа немає",
        "it": "nessuna chiave",
        "en": "no key configured",
    },
    "settings_cli_found": {
        "uk": "CLI знайдено: {path} · сесію не перевіряли",
        "it": "CLI trovata: {path} · sessione non verificata",
        "en": "CLI found at {path} · the session has not been checked",
    },
    "settings_cli_missing": {
        "uk": "claude CLI не знайдено на цій машині",
        "it": "claude CLI non trovata su questa macchina",
        "en": "the claude CLI is not on this machine",
    },
    "settings_tab_general": {
        "uk": "Загальні",
        "it": "Generali",
        "en": "General",
    },
    # Named after what the section decides, not after one of the things it
    # affects (3d): who reads the text, and whose account pays for it.
    "settings_tab_provider": {
        "uk": "Акаунт і модель",
        "it": "Account e modello",
        "en": "Account and model",
    },
    "settings_tab_advanced": {
        "uk": "Додатково",
        "it": "Avanzate",
        "en": "Advanced",
    },
    "settings_max_pages": {
        "uk": "Максимум сторінок за скан",
        "it": "Pagine massime per scansione",
        "en": "Max pages per scan",
    },
    "settings_provider": {
        "uk": "Хто оплачує переписування",
        "it": "Chi paga la riscrittura",
        "en": "Who pays for rewrites",
    },
    "settings_provider_note": {
        "uk": "Детектори працюють локально й безкоштовно. Оплачувані виклики потрібні лише для генерації замін тексту.",
        "it": "I rilevatori funzionano localmente e gratuitamente. Le chiamate a pagamento servono solo per generare le sostituzioni.",
        "en": "Detectors run locally and for free. Paid calls are only used to generate replacement text.",
    },
    "settings_api_key": {
        "uk": "API-ключ",
        "it": "Chiave API",
        "en": "API key",
    },
    "settings_model": {
        "uk": "Модель",
        "it": "Modello",
        "en": "Model",
    },
    "settings_base_url": {
        "uk": "Адреса сервера",
        "it": "URL del server",
        "en": "Server URL",
    },
    "settings_email": {
        "uk": "Пошта",
        "it": "Email",
        "en": "Email",
    },
    "settings_password": {
        "uk": "Пароль",
        "it": "Password",
        "en": "Password",
    },
    "settings_password_hint": {
        "uk": "використовується лише для входу, не зберігається",
        "it": "usata solo per l'accesso, non viene salvata",
        "en": "used only to sign in, never stored",
    },
    "settings_sign_in": {
        "uk": "Увійти",
        "it": "Accedi",
        "en": "Sign in",
    },
    "account_checking": {
        "uk": "Перевіряємо акаунт…",
        "it": "Verifica account…",
        "en": "Checking account…",
    },
    "account_checking_button": {
        "uk": "Перевірка…",
        "it": "Verifica…",
        "en": "Checking…",
    },
    "provider_checking": {
        "uk": "Перевіряємо провайдера…",
        "it": "Verifica provider…",
        "en": "Checking provider…",
    },
    "settings_sign_out": {
        "uk": "Вийти",
        "it": "Esci",
        "en": "Sign out",
    },
    "settings_check": {
        "uk": "Перевірити",
        "it": "Verifica",
        "en": "Check",
    },
    "settings_signed_in": {
        "uk": "Підключено: {detail}",
        "it": "Connesso: {detail}",
        "en": "Connected: {detail}",
    },
    "settings_not_signed_in": {
        "uk": "Не підключено: {detail}",
        "it": "Non connesso: {detail}",
        "en": "Not connected: {detail}",
    },
    "settings_signed_out": {
        "uk": "Ви вийшли з акаунта. Токени видалено.",
        "it": "Disconnesso. Token eliminati.",
        "en": "Signed out. Tokens deleted.",
    },
    "settings_quota": {
        "uk": "залишок квоти: {n}",
        "it": "quota rimanente: {n}",
        "en": "quota left: {n}",
    },
    "settings_need_credentials": {
        "uk": "Введіть пошту й пароль.",
        "it": "Inserisci email e password.",
        "en": "Enter email and password.",
    },
    "settings_storage_keyring": {
        "uk": "Токени зберігаються в системному сховищі ключів.",
        "it": "I token sono salvati nel portachiavi di sistema.",
        "en": "Tokens are stored in the OS keychain.",
    },
    "settings_storage_file": {
        "uk": "Системне сховище ключів недоступне — токени зберігаються у файлі з правами 0600. Встановіть пакет keyring для кращого захисту.",
        "it": "Portachiavi di sistema non disponibile — i token sono salvati in un file con permessi 0600. Installa il pacchetto keyring per maggiore sicurezza.",
        "en": "No OS keychain available — tokens are stored in a 0600 file. Install the 'keyring' package for stronger protection.",
    },
    "settings_endpoints_note": {
        "uk": "Відповідність полів API xformat.net. Порожньо = типові значення. Змінюйте, коли контракт API буде остаточним — код чіпати не треба.",
        "it": "Mappatura dei campi dell'API xformat.net. Vuoto = valori predefiniti. Modificala quando il contratto API sarà definitivo.",
        "en": "Field mapping for the xformat.net API. Empty = defaults. Edit this once the API contract is final — no code changes needed.",
    },
    "settings_show_defaults": {
        "uk": "Показати типові значення",
        "it": "Mostra valori predefiniti",
        "en": "Show defaults",
    },
    "settings_bad_json": {
        "uk": "Некоректний JSON: {error}",
        "it": "JSON non valido: {error}",
        "en": "Invalid JSON: {error}",
    },
    "rewrite_provider_status": {
        "uk": "Переписування: {provider}",
        "it": "Riscrittura: {provider}",
        "en": "Rewrites: {provider}",
    },
    "target_label": {
        "uk": "Що аналізувати:",
        "it": "Cosa analizzare:",
        "en": "Target:",
    },

    # ------------------------------------------- non-keyboard characters
    "fix_unicode_button": {
        "uk": "Виправити символи",
        "it": "Correggi caratteri",
        "en": "Fix characters",
    },
    "fix_unicode_tooltip": {
        "uk": "Замінити символи, яких немає на клавіатурі, на клавіатурні. Працює локально, без запитів до LLM і без витрат.",
        "it": "Sostituisce i caratteri non digitabili con quelli da tastiera. Funziona in locale, senza chiamate LLM e senza costi.",
        "en": "Replace non-keyboard characters with keyboard ones. Runs locally — no LLM calls, no cost.",
    },
    "unicode_fixed_summary": {
        "uk": "Підготовлено виправлень: {n}. Перегляньте їх у списку; у режимі репозиторію їх запише кнопка «Замінити автоматично у файлах».",
        "it": "Correzioni preparate: {n}. Rivedile nell'elenco; in modalità repository verranno scritte da «Sostituisci automaticamente nei file».",
        "en": "Prepared {n} fix(es). Review them in the list; in repository mode they're written by 'Auto-replace in files'.",
    },
    "settings_tab_unicode": {
        "uk": "Символи",
        "it": "Caratteri",
        "en": "Characters",
    },
    "settings_unicode_enabled": {
        "uk": "Шукати символи, яких немає на клавіатурі",
        "it": "Cerca caratteri non digitabili da tastiera",
        "en": "Detect characters not typed on a keyboard",
    },
    "settings_unicode_note": {
        "uk": "Ця перевірка точна й безкоштовна, тож виконується разом із обраним детектором. Символи, звичні для мови (українські «лапки», італійські è à ò), не позначаються.",
        "it": "Questo controllo è esatto e gratuito, quindi viene eseguito insieme al rilevatore scelto. I caratteri normali per la lingua (virgolette ucraine, è à ò italiane) non vengono segnalati.",
        "en": "This check is exact and free, so it runs alongside the selected detector. Characters that are normal for the language (Ukrainian «quotes», Italian è à ò) are not flagged.",
    },
    "settings_cat_invisible": {
        "uk": "Невидимі", "it": "Invisibili", "en": "Invisible",
    },
    "settings_cat_space": {
        "uk": "Пробіли", "it": "Spazi", "en": "Spaces",
    },
    "settings_cat_homoglyph": {
        "uk": "Гомогліфи", "it": "Omoglifi", "en": "Homoglyphs",
    },
    "settings_cat_styled": {
        "uk": "Стилізовані", "it": "Stilizzate", "en": "Styled",
    },
    "settings_cat_typography": {
        "uk": "Типографіка", "it": "Tipografia", "en": "Typography",
    },
    "settings_cat_typography_note": {
        "uk": "Вимкніть, якщо хочете зберегти правильне тире й лапки в українських та італійських текстах.",
        "it": "Disattiva per mantenere il trattino lungo e le virgolette corrette nei testi ucraini e italiani.",
        "en": "Turn this off to keep proper em dashes and quotation marks in Ukrainian and Italian copy.",
    },
    # ---------------------------------------------------------- explanations
    # Rendered by explanations.py from TextSpan.details. Kept as templates so
    # the same finding reads in whatever language the UI is set to, including
    # after the language is changed post-scan.
    "why_style_title": {
        "uk": "Чому це схоже на текст від AI",
        "it": "Perché sembra testo generato dall'IA",
        "en": "Why this reads as AI-written",
    },
    "why_char_title": {
        "uk": "Символ, якого немає на клавіатурі",
        "it": "Carattere che nessuna tastiera produce",
        "en": "A character no keyboard produces",
    },
    "why_char_title_invisible": {
        "uk": "Невидимий керуючий символ",
        "it": "Carattere di controllo invisibile",
        "en": "Invisible control character",
    },
    "why_char_title_space": {
        "uk": "Незвичайний пробіл",
        "it": "Spazio atipico",
        "en": "Unusual space",
    },
    "why_char_title_homoglyph": {
        "uk": "Літера з чужої абетки в середині слова",
        "it": "Lettera di un altro alfabeto dentro la parola",
        "en": "Letter from another alphabet inside the word",
    },
    "why_char_title_styled": {
        "uk": "Стилізована літера",
        "it": "Lettera stilizzata",
        "en": "Styled letter",
    },
    "why_char_title_typography": {
        "uk": "Друкарська пунктуація",
        "it": "Punteggiatura tipografica",
        "en": "Typographic punctuation",
    },
    "why_char_invisible": {
        "uk": "Символ нічого не показує на екрані, але лишається в тексті: він переживає вичитку, ламає пошук і порівняння рядків. Клавіатура його не набирає, тож він потрапив сюди з машинної обробки.",
        "it": "Non mostra nulla sullo schermo ma resta nel testo: sopravvive alla revisione e rompe ricerca e confronto di stringhe. Nessuna tastiera lo digita, quindi arriva da un passaggio automatico.",
        "en": "It shows nothing on screen yet stays in the text: it survives proofreading and breaks search and string comparison. No keyboard types it, so it arrived from machine processing.",
    },
    "why_char_space": {
        "uk": "Виглядає як звичайний пробіл, але це інший символ. Через нього рядок не переноситься там, де мав би, а пошук по фразі не знаходить її.",
        "it": "Sembra uno spazio normale ma è un altro carattere. Impedisce l'a capo dove servirebbe e la ricerca della frase non la trova.",
        "en": "It looks like a plain space but is a different character. It stops the line breaking where it should, and a search for the phrase fails to find it.",
    },
    "why_char_homoglyph": {
        "uk": "Слово написане двома абетками одночасно: ця літера з іншої, хоч виглядає так само. На екрані непомітно, але слово перестає знаходитись пошуком і підкреслюється перевіркою орфографії.",
        "it": "La parola è scritta con due alfabeti insieme: questa lettera viene dall'altro pur sembrando identica. A schermo non si nota, ma la parola sparisce dalla ricerca e il correttore la segna.",
        "en": "The word is written in two alphabets at once: this letter comes from the other one although it looks identical. Invisible on screen, but the word stops matching search and the spellchecker flags it.",
    },
    "why_char_styled": {
        "uk": "Це не звичайна літера, а її стилізований варіант із математичного або повноширинного блоку. Такі символи вставляють, щоб обійти форматування, і вони не читаються програмами читання з екрана.",
        "it": "Non è una lettera normale ma una variante stilizzata dei blocchi matematici o a larghezza intera. Si usano per aggirare la formattazione e gli screen reader non le leggono.",
        "en": "Not a plain letter but a styled variant from the mathematical or fullwidth block. These get pasted in to fake formatting, and screen readers don't read them.",
    },
    "why_char_typography": {
        "uk": "Правильна друкарська пунктуація, якої немає на клавіатурі. У професійно зверстаному тексті це норма, тож оцінка тут середня; вимкнути перевірку можна в налаштуваннях.",
        "it": "Punteggiatura tipografica corretta ma assente dalla tastiera. In un testo impaginato bene è normale, quindi il punteggio resta medio; si può disattivare nelle impostazioni.",
        "en": "Correct typographic punctuation that isn't on the keyboard. In professionally typeset copy this is normal, so it scores medium; the check can be turned off in Settings.",
    },
    "why_char_codepoints": {
        "uk": "Знайдено: {codepoints}",
        "it": "Trovato: {codepoints}",
        "en": "Found: {codepoints}",
    },
    "why_char_caveat": {
        "uk": "Це точна знахідка, а не здогад: символ або є в тексті, або його немає.",
        "it": "È un riscontro esatto, non una stima: il carattere c'è o non c'è.",
        "en": "This is an exact finding, not a guess: the character is either there or it isn't.",
    },
    "why_cliche": {
        "uk": "Слова й звороти, які мовні моделі вживають значно частіше за людей: {phrases}",
        "it": "Parole ed espressioni che i modelli linguistici usano molto più delle persone: {phrases}",
        "en": "Words and phrases language models reach for far more often than people do: {phrases}",
    },
    "why_structural": {
        "uk": "Шаблонна конструкція «не просто X, а Y» та подібні: {patterns}",
        "it": "Costruzione stereotipata «non solo X, ma anche Y» e simili: {patterns}",
        "en": "A formulaic \"not just X, but Y\"-style construction: {patterns}",
    },
    "why_uniformity": {
        "uk": "Речення майже однакової довжини ({value}). Людина зазвичай чергує довгі й короткі.",
        "it": "Frasi di lunghezza quasi uguale ({value}). Chi scrive a mano alterna lunghe e brevi.",
        "en": "Sentences are nearly all the same length ({value}). People usually mix long and short ones.",
    },
    "why_repetition": {
        "uk": "Мало різних слів на обсяг тексту ({value}): формулювання повторюються.",
        "it": "Poche parole diverse per la lunghezza del testo ({value}): le formule si ripetono.",
        "en": "Few distinct words for this much text ({value}): the phrasing repeats itself.",
    },
    "why_dashes": {
        "uk": "Тире замість ком і дужок трапляється частіше за звичне ({value}).",
        "it": "Trattini lunghi al posto di virgole e parentesi più del normale ({value}).",
        "en": "Dashes stand in for commas and brackets more often than usual ({value}).",
    },
    "why_weak_combination": {
        "uk": "Жоден окремий сигнал не сильний, але разом вони дали оцінку вище порогу.",
        "it": "Nessun singolo segnale è forte, ma insieme superano la soglia.",
        "en": "No single signal is strong, but together they pushed the score over the threshold.",
    },
    "why_style_caveat": {
        "uk": "Це слабкі сигнали, а не доказ. Ретельно написаний людиною текст теж буває рівним і насиченим кліше.",
        "it": "Sono segnali deboli, non una prova. Anche un testo curato scritto da una persona può risultare uniforme e pieno di cliché.",
        "en": "These are weak signals, not proof. Carefully written human copy is often uniform and cliché-heavy too.",
    },
    "why_model_title": {
        "uk": "Оцінка моделі ({detector})",
        "it": "Giudizio del modello ({detector})",
        "en": "Model's judgement ({detector})",
    },
    # The hybrid run's third case: one passage that both engines flagged.
    # Given its own title because "the model said" and "the offline signals
    # said" are two kinds of evidence, and a reader deciding whether to
    # rewrite a sentence is entitled to know both were present.
    "why_agreement_title": {
        "uk": "Обидва двигуни позначили цей фрагмент",
        "it": "Entrambi i motori hanno segnalato questo passaggio",
        "en": "Both engines flagged this passage",
    },
    "why_agreement_caveat": {
        "uk": "Збіг двох двигунів не є доказом: локальні сигнали слабкі за "
              "побудовою, а оцінка моделі лишається думкою.",
        "it": "L'accordo tra i due motori non è una prova: i segnali locali "
              "sono deboli per costruzione e il giudizio del modello resta "
              "un'opinione.",
        "en": "Two engines agreeing is not proof: the offline signals are "
              "weak by construction, and the model's judgement stays an "
              "opinion.",
    },
    "why_agreement_model": {
        "uk": "Модель: {reason}",
        "it": "Modello: {reason}",
        "en": "The model: {reason}",
    },
    "why_model_caveat": {
        "uk": "Це думка моделі, а не водяний знак і не доказ походження тексту.",
        "it": "È l'opinione di un modello, non una filigrana né una prova di origine.",
        "en": "This is a model's opinion, not a watermark and not proof of origin.",
    },
    "suggest_exact": {
        "uk": "Заміна визначена правилом, без запиту до моделі.",
        "it": "Sostituzione decisa da una regola, senza chiamate al modello.",
        "en": "The replacement is fixed by a rule — no model call.",
    },
    "suggest_delete": {
        "uk": "Символ просто видаляється.",
        "it": "Il carattere viene semplicemente rimosso.",
        "en": "The character is simply removed.",
    },
    "suggest_none_rule": {
        "uk": "Для цього символу правила заміни немає.",
        "it": "Per questo carattere non esiste una regola di sostituzione.",
        "en": "There is no replacement rule for this character.",
    },
    "suggest_offline_wording": {
        "uk": "Варіант заміни складено офлайн зі словника простіших формулювань.",
        "it": "L'alternativa è costruita offline da un dizionario di formulazioni più semplici.",
        "en": "The alternative is built offline from a dictionary of plainer wording.",
    },
    "suggest_needs_model": {
        "uk": "Механічної заміни немає: тут потрібне переписування, а його згенерує лише модель.",
        "it": "Nessuna sostituzione meccanica: qui serve una riscrittura, che può produrla solo un modello.",
        "en": "No mechanical replacement: this needs rewriting, and only a model can produce it.",
    },
    "detail_why_header": {
        "uk": "Чому позначено",
        "it": "Perché è stato segnalato",
        "en": "Why it was flagged",
    },
    "detail_suggestion_header": {
        "uk": "Варіант заміни (офлайн)",
        "it": "Alternativa (offline)",
        "en": "Suggested replacement (offline)",
    },
    "detail_use_suggestion": {
        "uk": "Взяти цей варіант",
        "it": "Usa questa alternativa",
        "en": "Use this suggestion",
    },
    # ------------------------------------------------------ crawl diagnostics
    # Rendered by ui/widgets.diagnostics_message from PageDiagnostics.reasons.
    # These answer "the scan finished and found nothing — why?", which is the
    # one question an empty list cannot answer on its own.
    "crawl_reason_js_rendered": {
        "uk": "Сторінка збирається в браузері. Сервер віддав лише каркас застосунку, а текст дописує JavaScript уже після завантаження. Сканер не виконує JavaScript, тож бачити там нічого.",
        "it": "La pagina si costruisce nel browser. Il server ha restituito solo lo scheletro dell'applicazione e il testo viene inserito da JavaScript dopo il caricamento. Lo scanner non esegue JavaScript, quindi non c'è nulla da leggere.",
        "en": "The page is built in the browser. The server returned only an application shell, and the copy is written in by JavaScript after load. This scanner runs no JavaScript, so there is nothing there to read.",
    },
    "crawl_reason_framework": {
        "uk": "Ознаки фреймворку: {framework}.",
        "it": "Indizi del framework: {framework}.",
        "en": "Framework markers: {framework}.",
    },
    "crawl_reason_blocked": {
        "uk": "Сервер відмовив у відповіді (код {status}): захист від ботів, стіна згоди або потрібна авторизація.",
        "it": "Il server ha rifiutato (codice {status}): protezione anti-bot, muro di consenso o autenticazione richiesta.",
        "en": "The server refused (status {status}): a bot check, a consent wall, or authentication is required.",
    },
    "crawl_reason_not_html": {
        "uk": "Це не HTML-сторінка, а {content_type}. Сканер читає текст усередині розмітки.",
        "it": "Non è una pagina HTML ma {content_type}. Lo scanner legge il testo dentro il markup.",
        "en": "This is not an HTML page but {content_type}. The scanner reads text inside markup.",
    },
    "crawl_reason_too_short": {
        "uk": "Текст на сторінці є, але кожен фрагмент коротший за поріг у 20 символів: відкинуто {dropped}. Так виглядають сторінки, де є лише навігація й підписи кнопок.",
        "it": "Il testo c'è ma ogni frammento è sotto la soglia di 20 caratteri: {dropped} scartati. È l'aspetto tipico di una pagina fatta solo di navigazione ed etichette.",
        "en": "There is text, but every piece is under the 20-character threshold: {dropped} dropped. That is what a page of navigation and button labels looks like.",
    },
    "crawl_reason_no_text": {
        "uk": "У розмітці немає текстових вузлів, придатних для читання.",
        "it": "Il markup non contiene nodi di testo leggibili.",
        "en": "The markup holds no readable text nodes.",
    },
    "crawl_reason_redirected": {
        "uk": "Запит перенаправлено на {final_url}.",
        "it": "La richiesta è stata reindirizzata a {final_url}.",
        "en": "The request was redirected to {final_url}.",
    },
    "crawl_reason_already_seen": {
        "uk": "Ця сторінка вже прочитана під іншою адресою, тож удруге її не аналізовано.",
        "it": "Questa pagina è già stata letta a un altro indirizzo, quindi non è stata analizzata di nuovo.",
        "en": "This page was already read at another address, so it was not analysed twice.",
    },
    "crawl_reason_too_large": {
        "uk": "Сторінка більша за {megabytes} МБ, тому її не прочитано: одна сторінка не має забрати всю пам'ять.",
        "it": "La pagina supera {megabytes} MB, quindi non è stata letta: una sola pagina non deve occupare tutta la memoria.",
        "en": "The page is larger than {megabytes} MB, so it was not read: one page must not take all the memory.",
    },
    "crawl_reason_error": {
        "uk": "Запит не вдався: {error}",
        "it": "Richiesta fallita: {error}",
        "en": "The request failed: {error}",
    },
    "crawl_measurements": {
        "uk": "Отримано {bytes} байт HTML, з них {ratio} видимого тексту; придатних елементів {candidates}, узято блоків {kept}.",
        "it": "Ricevuti {bytes} byte di HTML, di cui {ratio} di testo visibile; elementi utili {candidates}, blocchi presi {kept}.",
        "en": "Received {bytes} bytes of HTML, {ratio} of it visible text; {candidates} usable elements, {kept} blocks taken.",
    },
    "crawl_advice_js": {
        "uk": "Що можна зробити: відскануйте репозиторій із вихідним кодом цієї сторінки (режим «Репозиторій»), або збережіть сторінку з браузера вже відрендереною і відскануйте цей файл.",
        "it": "Cosa fare: scansiona il repository con il codice sorgente della pagina (modalità «Repository»), oppure salva la pagina già renderizzata dal browser e scansiona quel file.",
        "en": "What to do: scan the repository this page is built from (Repository mode), or save the rendered page from the browser and scan that file.",
    },
    "empty_no_scan_title": {
        "uk": "Ще нічого не проаналізовано",
        "it": "Non è stato ancora analizzato nulla",
        "en": "Nothing analysed yet",
    },
    "empty_no_scan_body": {
        "uk": "Вкажіть адресу сторінки або теку з кодом і натисніть «Аналізувати». Офлайн-перевірка нічого не коштує і не надсилає текст нікуди.",
        "it": "Indica l'indirizzo di una pagina o una cartella di codice e premi «Analizza». Il controllo offline è gratuito e non invia il testo da nessuna parte.",
        "en": "Point it at a page address or a code folder and press Analyze. The offline check costs nothing and sends the text nowhere.",
    },
    "empty_clean_title": {
        "uk": "Нічого не позначено",
        "it": "Nessuna segnalazione",
        "en": "Nothing flagged",
    },
    "empty_clean_body": {
        "uk": "Перевірено {blocks} фрагментів тексту на {pages} сторінках. Жоден не набрав достатньо сигналів. Це не доказ, що текст писала людина, — лише те, що ця перевірка нічого не знайшла.",
        "it": "Controllati {blocks} frammenti su {pages} pagine. Nessuno ha raccolto segnali sufficienti. Non prova che il testo sia umano: solo che questo controllo non ha trovato nulla.",
        "en": "Checked {blocks} pieces of text across {pages} pages. None gathered enough signal. That is not proof the text is human-written — only that this check found nothing.",
    },
    "empty_no_text_title": {
        "uk": "Сканер не отримав тексту",
        "it": "Lo scanner non ha ricevuto testo",
        "en": "The scanner received no text",
    },
    "empty_no_text_body": {
        "uk": "Сторінку завантажено, але читати не було чого. Причина:",
        "it": "La pagina è stata scaricata ma non c'era nulla da leggere. Motivo:",
        "en": "The page was fetched, but there was nothing to read. Why:",
    },
    "empty_repo_no_text_title": {
        "uk": "У цій теці не знайдено тексту в розмітці",
        "it": "Nessun testo dentro il markup in questa cartella",
        "en": "No text inside markup found in this folder",
    },
    "empty_repo_no_text_body": {
        "uk": "Переглянуто файлів: {files}. Сканер читає текст усередині тегів у .html, .htm, .xml, .jsx, .tsx, .vue і .svelte. Перевірте шлях і список винятків.",
        "it": "File esaminati: {files}. Lo scanner legge il testo dentro i tag in .html, .htm, .xml, .jsx, .tsx, .vue e .svelte. Controlla il percorso e le esclusioni.",
        "en": "Files examined: {files}. The scanner reads text inside tags in .html, .htm, .xml, .jsx, .tsx, .vue and .svelte. Check the path and the exclusion list.",
    },
    "pages_with_problems": {
        "uk": "Сторінок із проблемами: {n}",
        "it": "Pagine con problemi: {n}",
        "en": "Pages with problems: {n}",
    },
    "theme_label": {
        "uk": "Тема:",
        "it": "Tema:",
        "en": "Theme:",
    },
    "theme_auto": {
        "uk": "Як у системі",
        "it": "Come il sistema",
        "en": "Follow system",
    },
    "theme_light": {
        "uk": "Світла",
        "it": "Chiaro",
        "en": "Light",
    },
    "theme_dark": {
        "uk": "Темна",
        "it": "Scuro",
        "en": "Dark",
    },
    # ------------------------------------------------------- repository scope
    "scope_label": {
        "uk": "Читати:",
        "it": "Leggere:",
        "en": "Read:",
    },
    "scope_label_full": {
        "uk": "Який текст брати з репозиторія",
        "it": "Quale testo prendere dal repository",
        "en": "Which text to take from the repository",
    },
    "scope_content": {
        "uk": "Контент для читача",
        "it": "Contenuti per il lettore",
        "en": "Reader-facing content",
    },
    "scope_content_full": {
        "uk": "Текст між тегами плюс рядки, які потрапляють у контент з коду: атрибути placeholder, alt і title, присвоєння textContent, виклики перекладу t(\"...\") і значення ключів на кшталт title: чи description:. Коментарі не читаються.",
        "it": "Testo tra i tag più le stringhe che finiscono nei contenuti dal codice: attributi placeholder, alt e title, assegnazioni a textContent, chiamate di traduzione t(\"...\") e valori di chiavi come title: o description:. I commenti non vengono letti.",
        "en": "Text between tags plus the strings that reach the content from code: placeholder, alt and title attributes, textContent assignments, t(\"...\") translation calls, and values of keys like title: or description:. Comments are not read.",
    },
    "scope_technical": {
        "uk": "Технічний текст",
        "it": "Testo tecnico",
        "en": "Technical text",
    },
    "scope_technical_full": {
        "uk": "Коментарі та docstring-и у коді, перевірені на ті самі AI-патерни. До читача цей текст не потрапляє, тож режим вмикається окремо, і автозаміна тут переписує коментар, а не копірайт.",
        "it": "Commenti e docstring nel codice, controllati sugli stessi pattern IA. Questo testo non arriva al lettore, quindi la modalità si attiva a parte e la sostituzione automatica qui riscrive un commento, non un testo di marketing.",
        "en": "Comments and docstrings in the code, checked for the same AI patterns. None of it reaches a reader, so this mode is turned on deliberately, and auto-replace here rewrites a comment rather than copy.",
    },
    "scope_both": {
        "uk": "І контент, і коментарі",
        "it": "Contenuti e commenti",
        "en": "Content and comments",
    },
    "scope_both_full": {
        "uk": "Обидва набори одночасно. Кожна знахідка підписана типом, щоб було видно, що саме буде переписано.",
        "it": "Entrambi insieme. Ogni riscontro è etichettato per tipo, così si vede cosa verrà riscritto.",
        "en": "Both sets at once. Every finding is labelled with its kind, so it stays clear what would be rewritten.",
    },
    "kind_markup": {
        "uk": "розмітка",
        "it": "markup",
        "en": "markup",
    },
    "kind_injected": {
        "uk": "рядок у коді",
        "it": "stringa nel codice",
        "en": "string in code",
    },
    "kind_technical": {
        "uk": "коментар",
        "it": "commento",
        "en": "comment",
    },
    "confirm_auto_replace_technical": {
        "uk": "Серед них коментарів у коді: {n}. Їх буде переписано у вихідних файлах.",
        "it": "Tra questi ci sono {n} commenti nel codice. Verranno riscritti nei file sorgente.",
        "en": "{n} of these are code comments. They will be rewritten in the source files.",
    },

    # ------------------------------------------------- accessibility findings
    # One entry per rule, in three pieces: what was found, why it matters to
    # the person using the page, and how to fix it. The "why" deliberately
    # describes the consequence rather than quoting a success criterion
    # number - "1.1.1" tells a developer nothing about why to care.
    "a11y_image_alt_title": {
        "uk": "Зображення без атрибута alt",
        "it": "Immagine senza attributo alt",
        "en": "Image with no alt attribute",
    },
    "a11y_image_alt_found": {
        "uk": "Знайдено: <img src=\"{src}\"> без alt.",
        "it": "Trovato: <img src=\"{src}\"> senza alt.",
        "en": "Found: <img src=\"{src}\"> with no alt.",
    },
    "a11y_image_alt_why": {
        "uk": "Програма читання з екрана оголосить лише слово «зображення» і піде далі. Якщо картинка щось значить, читач втратить цей зміст повністю; якщо вона декоративна, він почує зайвий шум. За розміткою неможливо визначити, що з двох, тому виправлення мусить бути свідомим.",
        "it": "Uno screen reader annuncerà solo «immagine» e proseguirà. Se l'immagine ha un significato, chi ascolta lo perde del tutto; se è decorativa, sente rumore inutile. Dal markup non si capisce quale dei due casi sia, quindi la correzione va scelta consapevolmente.",
        "en": "A screen reader announces just \"image\" and moves on. If the picture carries meaning, the listener loses it entirely; if it is decorative, they hear noise. The markup cannot say which, so the fix has to be a deliberate choice.",
    },
    "a11y_image_alt_fix": {
        "uk": "Якщо зображення несе зміст - опишіть його: alt=\"голова команди на сцені\". Якщо воно декоративне - поставте порожній alt=\"\", і воно буде пропущене. Порожній alt і відсутній alt - це різні речі.",
        "it": "Se l'immagine ha un contenuto, descrivilo: alt=\"la responsabile del team sul palco\". Se è decorativa, metti alt=\"\" vuoto e verrà saltata. alt vuoto e alt assente non sono la stessa cosa.",
        "en": "If the image carries content, describe it: alt=\"the team lead on stage\". If it is decorative, give it an empty alt=\"\" and it will be skipped. An empty alt and a missing alt are not the same thing.",
    },
    "a11y_image_alt_filename_title": {
        "uk": "Замість опису в alt стоїть імʼя файлу або слаг",
        "it": "Nell'alt c'è il nome del file o uno slug invece della descrizione",
        "en": "The alt text is a file name or a slug, not a description",
    },
    "a11y_image_alt_filename_found": {
        "uk": "Знайдено: alt=\"{alt}\".",
        "it": "Trovato: alt=\"{alt}\".",
        "en": "Found: alt=\"{alt}\".",
    },
    "a11y_image_alt_filename_why": {
        "uk": "Атрибут є, тож автоматичні перевірки мовчать, але читач чує «логотип два ікс крапка пеенге» або «мапа дефіс парламанте дефіс пальманова». Це гірше за відсутній alt: помилка захована, а користі нуль. Слаг у alt зазвичай означає, що поле заповнив CMS, а не людина.",
        "it": "L'attributo c'è, quindi i controlli automatici tacciono, ma chi ascolta sente «logo due per ics punto png» o «mappa trattino parlante trattino example». È peggio di un alt assente: l'errore è nascosto e l'utilità è zero. Uno slug nell'alt di solito vuol dire che il campo l'ha riempito il CMS, non una persona.",
        "en": "The attribute is there, so automated checks stay quiet, but the listener hears \"logo dash two x dot p n g\" or \"mappa dash parlante dash example\". That is worse than a missing alt: the error is hidden and the value is nil. A slug in alt usually means the CMS filled the field, not a person.",
    },
    "a11y_image_alt_filename_fix": {
        "uk": "Напишіть, що на зображенні або яку функцію воно виконує, а не як називається файл. Для логотипа це назва компанії: alt=\"xFormat\". Якщо зображення суто декоративне, поставте порожній alt=\"\" і нічого не вигадуйте.",
        "it": "Scrivi cosa mostra l'immagine o che funzione ha, non come si chiama il file. Per un logo è il nome dell'azienda: alt=\"xFormat\". Se l'immagine è solo decorativa, metti alt=\"\" vuoto e non inventare nulla.",
        "en": "Write what the image shows or what it does, not what the file is called. For a logo that is the company name: alt=\"xFormat\". If the image is purely decorative, give it an empty alt=\"\" and do not invent a description.",
    },
    "a11y_control_name_title": {
        "uk": "Елемент керування без доступного імені",
        "it": "Controllo senza nome accessibile",
        "en": "Control with no accessible name",
    },
    "a11y_embedded_video_alternatives_title": {
        "uk": "Вбудоване відео: перевірте субтитри, транскрипт і аудіоопис",
        "it": "Video incorporato: verifica sottotitoli, trascrizione e audiodescrizione",
        "en": "Embedded video: check captions, transcript and audio description",
    },
    "a11y_embedded_video_alternatives_found": {
        "uk": "Знайдено: відео {provider} у <iframe> ({src}). Транскрипт на сторінці: {transcript}.",
        "it": "Trovato: video {provider} in un <iframe> ({src}). Trascrizione nella pagina: {transcript}.",
        "en": "Found: a {provider} video in an <iframe> ({src}). Transcript on the page: {transcript}.",
    },
    "a11y_embedded_video_alternatives_why": {
        "uk": "Розмітка містить лише адресу плеєра, тому інструмент не бачить, чи є в самого відео субтитри. Автоматичні субтитри помиляються саме на власних назвах і термінах, а людина, яка не бачить кадру, втрачає все, що показано і не сказано вголос. Це не вирок, а місце, яке мусить перевірити людина.",
        "it": "Il markup contiene solo l'indirizzo del player, quindi lo strumento non vede se il video ha i sottotitoli. I sottotitoli automatici sbagliano proprio sui nomi propri e sui termini, e chi non vede lo schermo perde tutto ciò che è mostrato e non detto. Non è un verdetto: è un punto che una persona deve controllare.",
        "en": "The markup holds only the player's address, so the tool cannot see whether the video has captions. Automatic captions fail precisely on proper names and terms, and a person who cannot see the frame loses everything that is shown but not said aloud. This is not a verdict but a place a person has to check.",
    },
    "a11y_embedded_video_alternatives_fix": {
        "uk": "Перевірте відео на хостингу: завантажте перевірені вручну субтитри (1.2.2), додайте під відео повну транскрипцію (1.2.3) і, для відео з важливим зображенням, аудіоопис або його версію (1.2.5). Якщо відео суто декоративне й без звуку, закрийте знахідку.",
        "it": "Controlla il video sulla piattaforma: carica sottotitoli verificati a mano (1.2.2), pubblica sotto il video la trascrizione completa (1.2.3) e, se l'immagine porta informazione, un'audiodescrizione o una versione audiodescritta (1.2.5). Se il video è solo decorativo e senza audio, chiudi la segnalazione.",
        "en": "Check the video on its host: upload hand-verified captions (1.2.2), publish the full transcript under the video (1.2.3) and, where the picture carries information, an audio description or a described version (1.2.5). If the video is purely decorative and silent, close the finding.",
    },
    "a11y_status_message_live_region_title": {
        "uk": "Повідомлення про стан без live region",
        "it": "Messaggi di stato senza live region",
        "en": "Status messages with no live region",
    },
    "a11y_status_message_live_region_found": {
        "uk": "Знайдено: <{element}> для підвантаження результатів, а на сторінці немає жодного aria-live, role=\"status\", role=\"alert\" чи <output>.",
        "it": "Trovato: <{element}> che carica altri risultati, ma la pagina non ha alcun aria-live, role=\"status\", role=\"alert\" né <output>.",
        "en": "Found: a <{element}> that loads more results, and the page has no aria-live, role=\"status\", role=\"alert\" or <output> anywhere.",
    },
    "a11y_status_message_live_region_why": {
        "uk": "Після натискання контент змінюється без перезавантаження, а програма читання з екрана мовчить: ні «завантаження», ні «показано 12 з 40», ні «більше результатів немає». Людина не знає, що щось сталося. Інструмент не бачить, що пише скрипт, тому це лише вказівка, що області оголошень на сторінці немає взагалі.",
        "it": "Dopo il clic il contenuto cambia senza ricaricare la pagina e lo screen reader tace: né «caricamento», né «mostrati 12 su 40», né «nessun altro risultato». La persona non sa che è successo qualcosa. Lo strumento non vede cosa scrive lo script, quindi è solo l'indizio che nella pagina non esiste alcuna area di annuncio.",
        "en": "After the click the content changes without a page load and a screen reader says nothing: not \"loading\", not \"showing 12 of 40\", not \"no more results\". The person does not know anything happened. The tool cannot see what the script writes, so this is only the signal that the page has no announcement area at all.",
    },
    "a11y_status_message_live_region_fix": {
        "uk": "Додайте порожню live region поза контейнером, який замінюється: <p role=\"status\" aria-live=\"polite\" class=\"visually-hidden\"></p>. Скрипт пише в неї «Завантаження...», потім «Показано N з M», потім «Більше результатів немає», і окремо повідомляє про помилку.",
        "it": "Aggiungi una live region vuota fuori dal contenitore che viene sostituito: <p role=\"status\" aria-live=\"polite\" class=\"visually-hidden\"></p>. Lo script vi scrive «Caricamento...», poi «Mostrati N di M», poi «Nessun altro risultato», e segnala a parte l'errore.",
        "en": "Add an empty live region outside the container that gets replaced: <p role=\"status\" aria-live=\"polite\" class=\"visually-hidden\"></p>. The script writes \"Loading...\", then \"Showing N of M\", then \"No more results\" into it, and announces an error separately.",
    },
    "a11y_control_name_found": {
        "uk": "Знайдено: <{element}> без тексту, aria-label, title і без повʼязаного <label>.",
        "it": "Trovato: <{element}> senza testo, aria-label, title né <label> collegata.",
        "en": "Found: <{element}> with no text, aria-label, title, or associated <label>.",
    },
    "a11y_control_name_why": {
        "uk": "Кнопку чи поле буде оголошено просто як «кнопка» або «редагування тексту», без жодної підказки, що воно робить. Кнопку лише з іконкою людина, яка не бачить екран, натиснути свідомо не може - це блокує задачу, а не ускладнює її.",
        "it": "Il pulsante o il campo verrà annunciato solo come «pulsante» o «casella di testo», senza alcun indizio su cosa faccia. Un pulsante con la sola icona non è utilizzabile consapevolmente da chi non vede lo schermo: blocca l'operazione, non la complica.",
        "en": "The button or field is announced as just \"button\" or \"edit text\", with no hint of what it does. An icon-only button cannot be used deliberately by someone who does not see the screen — that blocks the task rather than slowing it down.",
    },
    "a11y_control_name_fix": {
        "uk": "Для кнопки з іконкою додайте aria-label=\"Закрити\". Для поля - <label for=\"…\">, повʼязану через id. Для посилання - видимий текст усередині. Видимий текст кращий за aria-label, бо ним користуються і зрячі.",
        "it": "Per un pulsante con icona aggiungi aria-label=\"Chiudi\". Per un campo, una <label for=\"…\"> collegata tramite id. Per un link, testo visibile all'interno. Il testo visibile è preferibile ad aria-label, perché serve anche a chi vede.",
        "en": "For an icon button add aria-label=\"Close\". For a field, a <label for=\"…\"> tied to its id. For a link, visible text inside it. Visible text beats aria-label, because sighted users get it too.",
    },
    "a11y_link_text_vague_title": {
        "uk": "Текст посилання не описує ціль",
        "it": "Il testo del link non descrive la destinazione",
        "en": "Link text does not describe its destination",
    },
    "a11y_link_text_vague_found": {
        "uk": "Знайдено: «{text}» -> {href}.",
        "it": "Trovato: «{text}» -> {href}.",
        "en": "Found: \"{text}\" -> {href}.",
    },
    "a11y_link_text_vague_why": {
        "uk": "Програми читання з екрана дозволяють витягнути список усіх посилань сторінки окремо від тексту. У такому списку пʼятнадцять рядків «детальніше» - це пʼятнадцять однакових варіантів, з яких неможливо вибрати.",
        "it": "Gli screen reader permettono di estrarre l'elenco di tutti i link della pagina, fuori dal testo. In quell'elenco quindici righe «leggi di più» sono quindici scelte identiche fra cui è impossibile scegliere.",
        "en": "Screen readers can pull up a list of every link on the page, out of context. In that list, fifteen rows reading \"read more\" are fifteen identical choices with nothing to choose between.",
    },
    "a11y_link_text_vague_fix": {
        "uk": "Напишіть у самому посиланні, куди воно веде: «Тарифи і ціни» замість «детальніше». Якщо дизайн вимагає короткого напису, лишіть його видимим, а повний опис дайте через aria-label.",
        "it": "Scrivi nel link stesso dove porta: «Piani e prezzi» invece di «leggi di più». Se il design impone una scritta breve, lasciala visibile e metti la descrizione completa in aria-label.",
        "en": "Say in the link itself where it goes: \"Plans and pricing\" instead of \"read more\". If the design needs the short label, keep it visible and put the full description in aria-label.",
    },
    "a11y_html_lang_title": {
        "uk": "Мова документа не вказана",
        "it": "La lingua del documento non è dichiarata",
        "en": "The document language is not declared",
    },
    "a11y_html_lang_found": {
        "uk": "У теґа <html> немає атрибута lang.",
        "it": "Il tag <html> non ha l'attributo lang.",
        "en": "The <html> tag has no lang attribute.",
    },
    "a11y_html_lang_why": {
        "uk": "Синтезатор мовлення обирає вимову за мовою документа. Без неї український текст читатиметься правилами тієї мови, яка стоїть у системі користувача, і стане нерозбірливим. Це також ламає перенос слів і автоматичний переклад.",
        "it": "Il sintetizzatore vocale sceglie la pronuncia in base alla lingua del documento. Senza, un testo italiano viene letto con le regole della lingua di sistema dell'utente e diventa incomprensibile. Rompe anche sillabazione e traduzione automatica.",
        "en": "A speech synthesiser picks its pronunciation from the document language. Without it, the text is read using the rules of whatever language the user's system is set to, and becomes unintelligible. It also breaks hyphenation and machine translation.",
    },
    "a11y_html_lang_fix": {
        "uk": "Додайте код мови до кореневого теґа: <html lang=\"uk\">. Якщо на сторінці є фрагмент іншою мовою, позначте і його: <span lang=\"en\">.",
        "it": "Aggiungi il codice lingua al tag radice: <html lang=\"it\">. Se nella pagina c'è un brano in un'altra lingua, marca anche quello: <span lang=\"en\">.",
        "en": "Add the language code to the root tag: <html lang=\"en\">. If part of the page is in another language, mark that too: <span lang=\"uk\">.",
    },
    "a11y_document_title_title": {
        "uk": "Сторінка без заголовка <title>",
        "it": "Pagina senza <title>",
        "en": "Page has no <title>",
    },
    "a11y_document_title_found": {
        "uk": "Теґ <title> відсутній або порожній.",
        "it": "Il tag <title> manca o è vuoto.",
        "en": "The <title> tag is missing or empty.",
    },
    "a11y_document_title_why": {
        "uk": "Заголовок - перше, що оголошується при відкритті сторінки, і єдине, що відрізняє вкладки одна від одної. Без нього людина з десятьма відкритими вкладками не має способу зрозуміти, де вона.",
        "it": "Il titolo è la prima cosa annunciata all'apertura della pagina e l'unica che distingue una scheda dall'altra. Senza, chi ha dieci schede aperte non ha modo di capire dove si trova.",
        "en": "The title is the first thing announced when the page opens, and the only thing that tells one tab from another. Without it, someone with ten tabs open has no way to tell where they are.",
    },
    "a11y_document_title_fix": {
        "uk": "Додайте <title>, що починається з унікальної частини: «Тарифи - xFormat», а не «xFormat - Тарифи». Перші слова чути раніше за решту.",
        "it": "Aggiungi un <title> che inizi con la parte unica: «Prezzi - xFormat», non «xFormat - Prezzi». Le prime parole si sentono prima delle altre.",
        "en": "Add a <title> that starts with the unique part: \"Pricing - xFormat\", not \"xFormat - Pricing\". The first words are heard first.",
    },
    "a11y_heading_order_title": {
        "uk": "Пропущений рівень заголовка",
        "it": "Livello di intestazione saltato",
        "en": "A heading level was skipped",
    },
    "a11y_heading_order_found": {
        "uk": "Знайдено: після h{from} одразу h{to} - «{text}».",
        "it": "Trovato: dopo h{from} arriva subito h{to} - «{text}».",
        "en": "Found: h{from} is followed directly by h{to} - \"{text}\".",
    },
    "a11y_heading_order_why": {
        "uk": "Заголовки - це зміст сторінки, яким незрячі користувачі перегортають її, як зрячі очима. Стрибок з h2 на h4 читається як «тут пропущено цілий розділ», і людина шукає те, чого немає.",
        "it": "Le intestazioni sono l'indice con cui chi non vede scorre la pagina, come gli altri fanno con gli occhi. Un salto da h2 a h4 si legge come «qui manca una sezione», e la persona cerca qualcosa che non esiste.",
        "en": "Headings are the outline blind users skim with, the way sighted users skim with their eyes. A jump from h2 to h4 reads as \"a whole section is missing here\", and the person goes looking for something that is not there.",
    },
    "a11y_heading_order_fix": {
        "uk": "Знижуйте рівень по одному. Якщо рівень обрано заради розміру шрифту - лишіть правильний рівень і задайте розмір стилями.",
        "it": "Scendi di un livello per volta. Se il livello è stato scelto per la dimensione del carattere, tieni il livello corretto e imposta la dimensione con i CSS.",
        "en": "Step down one level at a time. If the level was picked for its font size, keep the correct level and set the size in CSS.",
    },
    "a11y_page_has_h1_title": {
        "uk": "На сторінці немає рівно одного h1",
        "it": "La pagina non ha esattamente un h1",
        "en": "The page does not have exactly one h1",
    },
    "a11y_page_has_h1_found": {
        "uk": "Знайдено заголовків h1: {count}.",
        "it": "Intestazioni h1 trovate: {count}.",
        "en": "h1 headings found: {count}.",
    },
    "a11y_page_has_h1_why": {
        "uk": "h1 називає сторінку цілком. Якщо його немає, у переліку заголовків немає верхівки і незрозуміло, про що сторінка; якщо їх кілька, структура читається як кілька документів, склеєних разом.",
        "it": "L'h1 dà il nome all'intera pagina. Se manca, l'elenco delle intestazioni non ha un vertice e non si capisce di cosa tratti la pagina; se ce ne sono più d'uno, la struttura si legge come più documenti incollati insieme.",
        "en": "The h1 names the whole page. With none, the heading outline has no top and the page's subject is unclear; with several, the structure reads as several documents glued together.",
    },
    "a11y_page_has_h1_fix": {
        "uk": "Лишіть один h1 - головний заголовок сторінки, а решту опустіть до h2.",
        "it": "Tieni un solo h1, l'intestazione principale della pagina, e porta gli altri a h2.",
        "en": "Keep one h1 — the page's main heading — and move the others down to h2.",
    },
    "a11y_tabindex_positive_title": {
        "uk": "Додатний tabindex ламає порядок фокуса",
        "it": "Un tabindex positivo rompe l'ordine di focus",
        "en": "A positive tabindex breaks the focus order",
    },
    "a11y_tabindex_positive_found": {
        "uk": "Знайдено: <{element} tabindex=\"{value}\">.",
        "it": "Trovato: <{element} tabindex=\"{value}\">.",
        "en": "Found: <{element} tabindex=\"{value}\">.",
    },
    "a11y_tabindex_positive_why": {
        "uk": "Будь-який додатний tabindex висмикує елемент з природного порядку і ставить його попереду всього, що має tabindex 0 - зокрема попереду посилання «перейти до вмісту». Один такий атрибут перебудовує клавіатурний шлях усієї сторінки.",
        "it": "Qualsiasi tabindex positivo estrae l'elemento dall'ordine naturale e lo mette davanti a tutto ciò che ha tabindex 0, incluso il link «vai al contenuto». Un solo attributo così riorganizza il percorso da tastiera dell'intera pagina.",
        "en": "Any positive tabindex pulls the element out of document order and puts it ahead of everything with tabindex 0 — including the skip link. One such attribute re-orders the keyboard path of the whole page.",
    },
    "a11y_tabindex_positive_fix": {
        "uk": "Поставте tabindex=\"0\" і впорядкуйте елементи в самій розмітці: порядок фокуса має збігатися з порядком читання. tabindex=\"-1\" лишіть для елементів, на які фокус ставить лише скрипт.",
        "it": "Metti tabindex=\"0\" e ordina gli elementi nel markup: l'ordine di focus deve coincidere con quello di lettura. Lascia tabindex=\"-1\" solo per elementi messi a fuoco via script.",
        "en": "Set tabindex=\"0\" and order the elements in the markup itself: focus order should match reading order. Keep tabindex=\"-1\" for elements only ever focused by script.",
    },
    "a11y_duplicate_id_title": {
        "uk": "Ідентифікатор повторюється",
        "it": "Identificatore duplicato",
        "en": "Duplicate identifier",
    },
    "a11y_duplicate_id_found": {
        "uk": "Знайдено: id=\"{id}\" зустрічається більше одного разу.",
        "it": "Trovato: id=\"{id}\" compare più di una volta.",
        "en": "Found: id=\"{id}\" occurs more than once.",
    },
    "a11y_duplicate_id_why": {
        "uk": "Атрибути for, aria-labelledby і aria-describedby знаходять лише перший елемент із таким id. Через дублікат усі підписи мовчки прикріплюються до одного елемента, а другий лишається без імені - при цьому розмітка виглядає правильною.",
        "it": "Gli attributi for, aria-labelledby e aria-describedby trovano solo il primo elemento con quell'id. Con un duplicato tutte le etichette si attaccano silenziosamente a un solo elemento e l'altro resta senza nome, mentre il markup sembra corretto.",
        "en": "The for, aria-labelledby and aria-describedby attributes resolve to the first element with that id only. A duplicate silently attaches every reference to one element and leaves the other unnamed — while the markup looks correct.",
    },
    "a11y_duplicate_id_fix": {
        "uk": "Зробіть ідентифікатори унікальними в межах документа. Для повторюваних компонентів додавайте суфікс від даних, а не порядковий номер, який може збігтися.",
        "it": "Rendi gli identificatori unici nel documento. Per i componenti ripetuti aggiungi un suffisso derivato dai dati, non un numero progressivo che può ripetersi.",
        "en": "Make identifiers unique within the document. For repeated components, derive the suffix from the data rather than from a counter that can collide.",
    },
    "a11y_aria_reference_broken_title": {
        "uk": "Посилання aria вказує в нікуди",
        "it": "Un riferimento aria punta nel vuoto",
        "en": "An aria reference points at nothing",
    },
    "a11y_aria_reference_broken_found": {
        "uk": "Знайдено: {attribute} посилається на id, яких немає: {missing}.",
        "it": "Trovato: {attribute} rimanda a id inesistenti: {missing}.",
        "en": "Found: {attribute} references ids that do not exist: {missing}.",
    },
    "a11y_aria_reference_broken_why": {
        "uk": "Зламане aria-labelledby гірше за його відсутність: браузер не підставляє запасний варіант, тож елемент лишається зовсім без імені, а розмітка при цьому виглядає так, ніби доступність продумана.",
        "it": "Un aria-labelledby rotto è peggio della sua assenza: il browser non applica alcun ripiego, quindi l'elemento resta del tutto senza nome mentre il markup sembra curato sul fronte accessibilità.",
        "en": "A broken aria-labelledby is worse than none: the browser applies no fallback, so the element ends up with no name at all — while the markup looks like accessibility was considered.",
    },
    "a11y_aria_reference_broken_fix": {
        "uk": "Звірте id: часта причина - елемент рендериться за умовою, а посилання лишилось. Якщо цілі немає, замініть на aria-label з текстом.",
        "it": "Verifica gli id: causa frequente è un elemento reso condizionalmente mentre il riferimento è rimasto. Se la destinazione non esiste, sostituisci con aria-label testuale.",
        "en": "Check the ids: the usual cause is an element rendered conditionally while the reference stayed. If the target does not exist, replace it with a plain aria-label.",
    },
    "a11y_button_type_title": {
        "uk": "Кнопка у формі без type",
        "it": "Pulsante nel form senza type",
        "en": "Button in a form with no type",
    },
    "a11y_button_type_found": {
        "uk": "Знайдено: <button> усередині <form> без атрибута type.",
        "it": "Trovato: <button> dentro <form> senza attributo type.",
        "en": "Found: <button> inside a <form> with no type attribute.",
    },
    "a11y_button_type_why": {
        "uk": "Усередині форми кнопка за замовчуванням має type=\"submit\". Тому кнопка «очистити» чи «показати пароль» відправляє форму при натисканні Enter - найчастіше саме з клавіатури, тобто саме в тих, хто мишею не користується.",
        "it": "Dentro un form il pulsante ha per default type=\"submit\". Così un pulsante «pulisci» o «mostra password» invia il form premendo Invio, cioè proprio da tastiera, cioè proprio a chi non usa il mouse.",
        "en": "Inside a form a button defaults to type=\"submit\". So a \"clear\" or \"show password\" button submits the form on Enter — which is the keyboard path, which is exactly the people who do not use a mouse.",
    },
    "a11y_button_type_fix": {
        "uk": "Вкажіть type явно: type=\"button\" для дій, що не відправляють форму, type=\"submit\" для тієї єдиної, що відправляє.",
        "it": "Indica type esplicitamente: type=\"button\" per le azioni che non inviano, type=\"submit\" per quell'unico che invia.",
        "en": "Set type explicitly: type=\"button\" for actions that do not submit, type=\"submit\" for the one that does.",
    },
    "a11y_media_captions_title": {
        "uk": "Відео чи аудіо без субтитрів",
        "it": "Video o audio senza sottotitoli",
        "en": "Video or audio with no captions",
    },
    "a11y_media_captions_found": {
        "uk": "Знайдено: <{element}> з доріжками субтитрів: {tracks}.",
        "it": "Trovato: <{element}> con tracce di sottotitoli: {tracks}.",
        "en": "Found: <{element}> with caption tracks: {tracks}.",
    },
    "a11y_media_captions_why": {
        "uk": "Без субтитрів увесь зміст запису недоступний людям, які не чують, і будь-кому, хто дивиться без звуку. Якщо це єдине місце, де сказано щось важливе, воно просто відсутнє для частини аудиторії.",
        "it": "Senza sottotitoli tutto il contenuto della registrazione è inaccessibile a chi non sente e a chiunque guardi senza audio. Se è l'unico posto in cui viene detta una cosa importante, per una parte del pubblico semplicemente non esiste.",
        "en": "Without captions the entire content of the recording is unavailable to people who do not hear, and to anyone watching with the sound off. If it is the only place something important is said, it simply is not there for part of the audience.",
    },
    "a11y_media_captions_fix": {
        "uk": "Додайте <track kind=\"captions\" srclang=\"uk\" src=\"…\" default>. Для аудіо дайте текстову розшифровку поруч із плеєром - вона ще й індексується пошуком.",
        "it": "Aggiungi <track kind=\"captions\" srclang=\"it\" src=\"…\" default>. Per l'audio metti una trascrizione accanto al player: viene anche indicizzata dai motori di ricerca.",
        "en": "Add <track kind=\"captions\" srclang=\"en\" src=\"…\" default>. For audio, put a transcript next to the player — it gets indexed by search engines too.",
    },
    "a11y_media_autoplay_title": {
        "uk": "Автовідтворення без керування",
        "it": "Riproduzione automatica senza controlli",
        "en": "Autoplay with no controls",
    },
    "a11y_media_autoplay_found": {
        "uk": "Знайдено: <{element} autoplay> без controls і без muted.",
        "it": "Trovato: <{element} autoplay> senza controls e senza muted.",
        "en": "Found: <{element} autoplay> with no controls and no muted.",
    },
    "a11y_media_autoplay_why": {
        "uk": "Звук, якого людина не просила і який неможливо зупинити, перекриває мовлення програми читання з екрана. Користувач при цьому не чує навіть того, як знайти кнопку зупинки - бо вона теж озвучується.",
        "it": "Un suono non richiesto e non arrestabile copre la voce dello screen reader. L'utente non sente nemmeno come trovare il pulsante di stop, perché anche quello viene pronunciato a voce.",
        "en": "Sound the visitor did not ask for and cannot stop covers the screen reader's own speech. They cannot even hear how to find the stop button, because that is announced by speech too.",
    },
    "a11y_media_autoplay_fix": {
        "uk": "Приберіть autoplay, або додайте controls, або запускайте без звуку (muted) і дайте кнопку ввімкнення звуку.",
        "it": "Togli autoplay, oppure aggiungi controls, oppure avvia senza audio (muted) offrendo un pulsante per attivarlo.",
        "en": "Drop autoplay, or add controls, or start muted and offer a button to turn the sound on.",
    },
    "a11y_table_headers_title": {
        "uk": "Таблиця даних без заголовків стовпців",
        "it": "Tabella di dati senza intestazioni",
        "en": "Data table with no header cells",
    },
    "a11y_table_headers_found": {
        "uk": "Знайдено: <table> з {rows} рядками і жодного <th>.",
        "it": "Trovato: <table> con {rows} righe e nessun <th>.",
        "en": "Found: a <table> with {rows} rows and no <th>.",
    },
    "a11y_table_headers_why": {
        "uk": "Зряча людина зіставляє клітинку зі стовпцем поглядом угору. Незряча читає таблицю по клітинці, і без <th> кожне значення оголошується голим числом без назви стовпця: «10» замість «Ціна: 10».",
        "it": "Chi vede associa la cella alla colonna con un'occhiata verso l'alto. Chi non vede legge cella per cella e, senza <th>, ogni valore viene annunciato come numero nudo senza il nome della colonna: «10» invece di «Prezzo: 10».",
        "en": "A sighted reader matches a cell to its column with a glance upwards. A blind reader goes cell by cell, and without <th> every value is announced as a bare number with no column name: \"10\" instead of \"Price: 10\".",
    },
    "a11y_table_headers_fix": {
        "uk": "Замініть клітинки шапки на <th scope=\"col\">, а заголовки рядків - на <th scope=\"row\">. Додайте <caption> з призначенням таблиці. Якщо таблиця використана для верстки - краще перейти на CSS-сітку, а тимчасово поставити role=\"presentation\".",
        "it": "Sostituisci le celle di intestazione con <th scope=\"col\"> e quelle di riga con <th scope=\"row\">. Aggiungi una <caption> che dica a cosa serve la tabella. Se la tabella serve per l'impaginazione, passa a una griglia CSS e nel frattempo metti role=\"presentation\".",
        "en": "Turn header cells into <th scope=\"col\"> and row headers into <th scope=\"row\">. Add a <caption> saying what the table is for. If the table is doing layout, move to a CSS grid and mark it role=\"presentation\" meanwhile.",
    },
    "a11y_viewport_zoom_title": {
        "uk": "Масштабування сторінки заблоковане",
        "it": "Lo zoom della pagina è bloccato",
        "en": "Page zoom is blocked",
    },
    "a11y_viewport_zoom_found": {
        "uk": "Знайдено: <meta name=\"viewport\" content=\"{content}\">.",
        "it": "Trovato: <meta name=\"viewport\" content=\"{content}\">.",
        "en": "Found: <meta name=\"viewport\" content=\"{content}\">.",
    },
    "a11y_viewport_zoom_why": {
        "uk": "Це один рядок, який робить сайт непридатним для всіх, хто збільшує текст - а це не лише люди зі слабким зором, а й будь-хто на сонці або в дорозі. Обхідного шляху в користувача немає.",
        "it": "È una riga sola che rende il sito inutilizzabile per chiunque ingrandisca il testo, non solo chi ha problemi di vista ma anche chi legge al sole o in movimento. L'utente non ha alcuna via d'uscita.",
        "en": "It is a single line that makes the site unusable for anyone who enlarges text — not only people with low vision but anyone in bright sun or on the move. The user has no way around it.",
    },
    "a11y_viewport_zoom_fix": {
        "uk": "Приберіть user-scalable=no і maximum-scale. Робочий варіант: content=\"width=device-width, initial-scale=1\".",
        "it": "Togli user-scalable=no e maximum-scale. Versione corretta: content=\"width=device-width, initial-scale=1\".",
        "en": "Remove user-scalable=no and maximum-scale. The working version is content=\"width=device-width, initial-scale=1\".",
    },
    "a11y_contrast_inline_title": {
        "uk": "Замалий контраст тексту",
        "it": "Contrasto del testo insufficiente",
        "en": "Text contrast is too low",
    },
    "a11y_contrast_inline_found": {
        "uk": "Знайдено: {foreground} на {background}, співвідношення {ratio} замість потрібних {required}.",
        "it": "Trovato: {foreground} su {background}, rapporto {ratio} invece dei {required} richiesti.",
        "en": "Found: {foreground} on {background}, ratio {ratio} against the required {required}.",
    },
    "a11y_contrast_inline_why": {
        "uk": "Світло-сірий на білому виглядає стримано на моніторі дизайнера і зникає на дешевому екрані, при яскравому світлі й для більшості людей за сорок. Порогом 4.5:1 позначено межу, за якою текст перестає читатися, а не смак.",
        "it": "Il grigio chiaro su bianco sembra sobrio sul monitor del designer e sparisce su uno schermo economico, in piena luce e per la maggior parte delle persone oltre i quarant'anni. La soglia 4.5:1 segna il punto in cui il testo smette di essere leggibile, non una questione di gusto.",
        "en": "Light grey on white looks restrained on a designer's monitor and disappears on a cheap screen, in bright light, and for most people over forty. The 4.5:1 threshold marks where text stops being readable — it is not a matter of taste.",
    },
    "a11y_contrast_inline_fix": {
        "uk": "Затемніть текст або освітліть тло, доки співвідношення не буде щонайменше 4.5:1 для звичайного тексту і 3:1 для великого (від 24px, або 19px жирним).",
        "it": "Scurisci il testo o schiarisci lo sfondo finché il rapporto non è almeno 4.5:1 per il testo normale e 3:1 per quello grande (da 24px, o 19px in grassetto).",
        "en": "Darken the text or lighten the background until the ratio is at least 4.5:1 for body text and 3:1 for large text (24px and up, or 19px bold).",
    },
    "a11y_viewport_fixed_width_title": {
        "uk": "Елемент зафіксований шириною, що ширша за телефон",
        "it": "Elemento bloccato a una larghezza più ampia dello schermo del telefono",
        "en": "An element is pinned to a width wider than a phone",
    },
    "a11y_viewport_fixed_width_found": {
        "uk": "Знайдено оголошення width: {width_px}px при ширині екрана телефону близько {mobile_viewport}px.",
        "it": "Trovata una dichiarazione width: {width_px}px con uno schermo telefonico di circa {mobile_viewport}px.",
        "en": "Found a width declaration of {width_px}px against a phone viewport of about {mobile_viewport}px.",
    },
    "a11y_viewport_fixed_width_why": {
        "uk": "Фіксована ширина у сотні пікселів означає, що на телефоні елемент виходить за екран, і сторінку доводиться гортати вбік, читаючи текст шматками. WCAG 1.4.10 вимагає, щоб уміст перебудовувався без горизонтальної прокрутки - заміна width на max-width лишає широкий макет на великому екрані і дозволяє стиснення на малому.",
        "it": "Una larghezza fissa di centinaia di pixel fa sì che su telefono l'elemento esca dallo schermo e la pagina vada fatta scorrere di lato per leggere il testo a pezzi. La WCAG 1.4.10 richiede che il contenuto si riorganizzi senza scorrimento orizzontale: sostituire width con max-width mantiene il layout largo sul grande schermo e permette la compressione su quello piccolo.",
        "en": "A fixed width of hundreds of pixels means that on a phone the element runs off the screen and the page has to be scrolled sideways to read text in fragments. WCAG 1.4.10 requires content to reflow without horizontal scrolling - swapping width for max-width keeps the wide layout on large screens while allowing it to shrink on small ones.",
    },
    "a11y_viewport_fixed_width_fix": {
        "uk": "Замініть width на max-width для цього значення, або задайте ширину у відсотках чи через flex/grid, якщо фіксовані пікселі не потрібні за задумом.",
        "it": "Sostituisci width con max-width per questo valore, oppure imposta la larghezza in percentuale o tramite flex/grid se i pixel fissi non sono necessari al progetto.",
        "en": "Replace width with max-width for this value, or size the element in percentages or via flex/grid if fixed pixels are not part of the design.",
    },
    "a11y_viewport_tiny_font_title": {
        "uk": "Розмір шрифту менший за читабельний",
        "it": "Dimensione del font inferiore alla soglia leggibile",
        "en": "Font size below the readable threshold",
    },
    "a11y_viewport_tiny_font_found": {
        "uk": "Знайдено font-size {font_px}px при рекомендованому мінімумі {minimum_recommended}px.",
        "it": "Trovato font-size {font_px}px contro un minimo consigliato di {minimum_recommended}px.",
        "en": "Found font-size {font_px}px against a recommended minimum of {minimum_recommended}px.",
    },
    "a11y_viewport_tiny_font_why": {
        "uk": "Шрифт менший за 10px на телефоні не читається без жесту збільшення, а користувачі старшого віку просто відкладають таку сторінку. Браузерний мінімум не рятує: він застосовується не скрізь, а зум всієї сторінки ламає макет. WCAG 1.4.4 вимагає, щоб текст масштабувався до 200% без втрати умісту.",
        "it": "Un font sotto i 10px su telefono non si legge senza gesti di zoom, e gli utenti meno giovani semplicemente abbandonano la pagina. Il minimo del browser non basta: non si applica ovunque e lo zoom dell'intera pagina rompe il layout. La WCAG 1.4.4 richiede che il testo sia ridimensionabile fino al 200% senza perdita di contenuto.",
        "en": "Text under 10px on a phone cannot be read without pinch-zooming, and older users simply put such a page down. The browser's minimum size does not save you: it does not apply everywhere, and full-page zoom breaks the layout. WCAG 1.4.4 requires text to resize up to 200% without loss of content.",
    },
    "a11y_viewport_tiny_font_fix": {
        "uk": "Підніміть розмір щонайменше до 10-12px; справжній дрібний текст (юридичні примітки, підписи) робіть читабельним, а не формально присутнім.",
        "it": "Porta la dimensione ad almeno 10-12px; il testo volutamente piccolo (note legali, didascalie) deve restare leggibile, non solo formalmente presente.",
        "en": "Raise the size to at least 10-12px; deliberately small text (legal notes, captions) should stay readable, not merely present.",
    },
    "a11y_viewport_touch_target_title": {
        "uk": "Кнопка чи посилання завмалі для пальця",
        "it": "Pulsante o link troppo piccolo per un dito",
        "en": "A button or link is too small for a finger",
    },
    "a11y_viewport_touch_target_found": {
        "uk": "Знайдено інтерактивний елемент із оголошеними розмірами {declared} при мінімумі WCAG {wcag_minimum}px (рекомендовано близько {recommended}px).",
        "it": "Trovato un elemento interattivo con dimensioni dichiarate {declared} contro un minimo WCAG di {wcag_minimum}px (consigliati circa {recommended}px).",
        "en": "Found an interactive element with declared sizes of {declared} against the WCAG minimum of {wcag_minimum}px (about {recommended}px recommended).",
    },
    "a11y_viewport_touch_target_why": {
        "uk": "Ціль у 20 пікселів промахується пальцем особливо в дорозі: поруч стоїть сусідня ціль, і натискання потрапляє не туди. Стандарт 2.5.8 задає межу 24px, але мобільні платформи радять близько 44px, бо реальний палець ширше за курсор.",
        "it": "Un bersaglio di 20 pixel viene mancato col dito soprattutto in movimento: il bersaglio vicino è adiacente e il tocco finisce nel posto sbagliato. Lo standard 2.5.8 fissa il minimo a 24px, ma le piattaforme mobili consigliano circa 44px, perché un dito reale è più largo di un cursore.",
        "en": "A 20-pixel target gets missed by a finger especially on the move: neighbouring targets sit close together and taps land on the wrong one. Standard 2.5.8 sets the floor at 24px, but mobile platforms recommend around 44px because a real finger is wider than a cursor.",
    },
    "a11y_viewport_touch_target_fix": {
        "uk": "Збільшіть саму ціль або додайте прозорий відступ навколо (padding), щоб загальна область дотику була щонайменше 24px, а краще 44px.",
        "it": "Ingrandisci il bersaglio stesso oppure aggiungi un margine trasparente intorno (padding) affinché l'area totale di tocco sia almeno 24px, meglio ancora 44px.",
        "en": "Enlarge the target itself or add transparent spacing around it (padding) so the total touch area is at least 24px, better still 44px.",
    },
    # ---------------------------------------------------------------- SEO
    "a11y_seo_title_length_title": {
        "uk": "Заголовок сторінки поза робочою довжиною",
        "it": "Titolo della pagina fuori dalla lunghezza utile",
        "en": "Page title outside the useful length",
    },
    "a11y_seo_title_length_found": {
        "uk": "Заголовок має {length} символів при робочому діапазоні {min}-{max}: «{title}».",
        "it": "Il titolo ha {length} caratteri, l'intervallo utile è {min}-{max}: «{title}».",
        "en": "The title is {length} characters against a useful range of {min}-{max}: \"{title}\".",
    },
    "a11y_seo_title_length_why": {
        "uk": "Заголовок є першим рядком у результатах пошуку, у вкладці браузера і у закладці. Надто короткий не відрізняє сторінку від сусідніх, надто довгий обрізається, і обрізається саме кінець, де зазвичай стоїть найточніше слово. Це не штраф від пошуковика, а межа показу: те, що не вміщується, просто не бачить жодна людина.",
        "it": "Il titolo è la prima riga nei risultati di ricerca, nella scheda del browser e nei preferiti. Troppo corto non distingue la pagina dalle altre, troppo lungo viene troncato, e viene troncata proprio la fine, dove di solito sta la parola più precisa. Non è una penalità del motore di ricerca, è un limite di visualizzazione: ciò che non entra non lo legge nessuno.",
        "en": "The title is the first line in a search result, in the browser tab and in a bookmark. Too short and it does not tell this page apart from its neighbours; too long and it is truncated - and what gets cut is the end, where the most specific word usually sits. This is not a ranking penalty, it is a display limit: what does not fit is seen by nobody.",
    },
    "a11y_seo_title_length_fix": {
        "uk": "Тримайте {min}-{max} символів і ставте на початок те, що відрізняє цю сторінку, а назву сайту в кінець: «Оренда авто в Києві - Назва». Заголовок має описувати сторінку, а не сайт.",
        "it": "Resta tra {min} e {max} caratteri e metti all'inizio ciò che distingue questa pagina, il nome del sito alla fine: «Noleggio auto a Kiev - Nome». Il titolo descrive la pagina, non il sito.",
        "en": "Keep it between {min} and {max} characters, and put what makes this page different first, the site name last: \"Car hire in Kyiv - Brand\". The title describes the page, not the site.",
    },
    "a11y_seo_meta_description_title": {
        "uk": "Опис сторінки відсутній або поза робочою довжиною",
        "it": "Meta description assente o fuori dalla lunghezza utile",
        "en": "Meta description missing or outside the useful length",
    },
    "a11y_seo_meta_description_found": {
        "uk": "Довжина meta description: {length} символів при діапазоні {min}-{max}. Нуль означає, що тега немає взагалі.",
        "it": "Lunghezza della meta description: {length} caratteri, intervallo utile {min}-{max}. Zero significa che il tag non c'è affatto.",
        "en": "Meta description length: {length} characters against a range of {min}-{max}. Zero means the tag is absent entirely.",
    },
    "a11y_seo_meta_description_why": {
        "uk": "Це другий рядок у результатах пошуку і текст, який показує кожен месенджер при вставленні посилання. Коли опису немає, пошуковик збирає уривок сам з першого-ліпшого тексту сторінки, і це часто меню або юридична примітка. Тобто рядок усе одно буде показаний, питання лише в тому, писали його ви чи ні.",
        "it": "È la seconda riga nei risultati di ricerca e il testo che ogni messaggistica mostra quando si incolla il link. Se la description manca, il motore compone lo snippet da solo prendendo il primo testo disponibile, che spesso è il menu o una nota legale. La riga viene mostrata comunque: l'unica domanda è se l'hai scritta tu.",
        "en": "This is the second line of a search result and the text every chat app shows when someone pastes the link. With no description the engine writes the snippet itself from whatever text comes first, which is often the menu or a legal notice. The line gets shown either way; the only question is whether you wrote it.",
    },
    "a11y_seo_meta_description_fix": {
        "uk": "Додайте <meta name=\"description\" content=\"…\"> на {min}-{max} символів: одне-два речення про те, що людина отримає саме на цій сторінці. Не переказ заголовка і не список ключових слів.",
        "it": "Aggiungi <meta name=\"description\" content=\"…\"> di {min}-{max} caratteri: una o due frasi su cosa trova la persona proprio in questa pagina. Non una parafrasi del titolo né un elenco di parole chiave.",
        "en": "Add a <meta name=\"description\" content=\"…\"> of {min}-{max} characters: one or two sentences about what a person gets on this particular page. Not a restatement of the title, and not a keyword list.",
    },
    "a11y_seo_canonical_title": {
        "uk": "Канонічне посилання відсутнє або їх кілька",
        "it": "Link canonical assente o duplicato",
        "en": "Canonical link missing or duplicated",
    },
    "a11y_seo_canonical_found": {
        "uk": "Тегів <link rel=\"canonical\"> на сторінці: {count}. Правильна кількість - рівно один.",
        "it": "Tag <link rel=\"canonical\"> nella pagina: {count}. Il numero corretto è esattamente uno.",
        "en": "Number of <link rel=\"canonical\"> tags on the page: {count}. The correct number is exactly one.",
    },
    "a11y_seo_canonical_why": {
        "uk": "Та сама сторінка майже завжди доступна за кількома адресами: з www і без, з параметрами відстеження, зі слешем у кінці і без. Без канонічного посилання пошуковик рахує їх різними сторінками і ділить вагу між ними. Два канонічні теги гірші за жодного: система обирає один сама або ігнорує обидва, і цей вибір сайту вже не належить.",
        "it": "La stessa pagina è quasi sempre raggiungibile a più indirizzi: con e senza www, con parametri di tracciamento, con e senza slash finale. Senza canonical il motore le considera pagine diverse e divide il peso tra loro. Due tag canonical sono peggio di nessuno: il sistema ne sceglie uno da solo o li ignora entrambi, e quella scelta non appartiene più al sito.",
        "en": "The same page is nearly always reachable at several addresses: with and without www, with tracking parameters, with and without a trailing slash. With no canonical the engine treats them as separate pages and splits the weight between them. Two canonicals are worse than none: the system picks one itself or ignores both, and that choice no longer belongs to the site.",
    },
    "a11y_seo_canonical_fix": {
        "uk": "Лишіть один тег у <head> із повною абсолютною адресою тієї версії, яку вважаєте основною: <link rel=\"canonical\" href=\"https://example.com/page\">. Відносний шлях тут не працює надійно.",
        "it": "Lascia un solo tag nel <head> con l'indirizzo assoluto completo della versione che consideri principale: <link rel=\"canonical\" href=\"https://example.com/page\">. Un percorso relativo qui non è affidabile.",
        "en": "Leave one tag in <head> with the full absolute address of the version you consider primary: <link rel=\"canonical\" href=\"https://example.com/page\">. A relative path is not reliable here.",
    },
    "a11y_seo_noindex_title": {
        "uk": "Сторінка закрита від індексації",
        "it": "Pagina esclusa dall'indicizzazione",
        "en": "Page blocked from indexing",
    },
    "a11y_seo_noindex_found": {
        "uk": "Знайдено директиву robots зі значенням: {content}.",
        "it": "Trovata una direttiva robots con valore: {content}.",
        "en": "Found a robots directive with the value: {content}.",
    },
    "a11y_seo_noindex_why": {
        "uk": "Це найдорожча помилка з усіх у цьому списку, і водночас найтихіша: сторінка виглядає нормально, працює нормально і просто відсутня в пошуку. Майже завжди це директива з тестового середовища, яка поїхала в реліз разом із кодом. Поки вона діє, решта роботи над цією сторінкою не має значення.",
        "it": "È l'errore più costoso di questo elenco e insieme il più silenzioso: la pagina sembra normale, funziona normalmente e semplicemente non esiste nella ricerca. Quasi sempre è una direttiva dell'ambiente di test finita in produzione insieme al codice. Finché è attiva, tutto il resto del lavoro su questa pagina non conta.",
        "en": "This is the most expensive mistake in the list and also the quietest: the page looks fine, works fine, and is simply absent from search. It is nearly always a staging directive that shipped along with the code. While it holds, none of the other work on this page matters.",
    },
    "a11y_seo_noindex_fix": {
        "uk": "Якщо сторінка публічна - приберіть цей тег або поставте content=\"index, follow\". Якщо вона справді має бути прихованою, лишіть, але переконайтесь, що це свідоме рішення для саме цієї адреси, а не глобальний шаблон.",
        "it": "Se la pagina è pubblica, rimuovi il tag o metti content=\"index, follow\". Se deve davvero restare nascosta, lascialo, ma verifica che sia una scelta consapevole per questo indirizzo e non un template globale.",
        "en": "If the page is public, remove the tag or set content=\"index, follow\". If it genuinely should stay hidden, keep it, but check that this is a deliberate decision for this address and not a global template.",
    },
    "a11y_seo_x_robots_noindex_title": {
        "uk": "Сторінку закрито від індексації HTTP-заголовком",
        "it": "La pagina è esclusa dall'indicizzazione dall'header HTTP",
        "en": "An HTTP header blocks the page from indexing",
    },
    "a11y_seo_x_robots_noindex_found": {
        "uk": "Заголовок {header} містить директиву: {content}.",
        "it": "L'header {header} contiene la direttiva: {content}.",
        "en": "The {header} header contains the directive: {content}.",
    },
    "a11y_seo_x_robots_noindex_why": {
        "uk": "Пошукові системи читають цю директиву з HTTP-відповіді ще до аналізу розмітки. Якщо сторінка має бути публічною, вона не потрапить у пошук, навіть коли в HTML немає meta robots.",
        "it": "I motori leggono questa direttiva nella risposta HTTP prima ancora del markup. Se la pagina deve essere pubblica, non apparirà nella ricerca anche senza un meta robots nell'HTML.",
        "en": "Search engines read this directive from the HTTP response before they analyse the markup. A public page will stay out of search even when its HTML has no meta robots tag.",
    },
    "a11y_seo_x_robots_noindex_fix": {
        "uk": "Для публічної сторінки приберіть noindex або none з конфігурації сервера, CDN чи застосунку. Лишайте директиву лише для адрес, які справді не повинні бути в пошуку.",
        "it": "Per una pagina pubblica rimuovi noindex o none dalla configurazione del server, CDN o applicazione. Mantieni la direttiva solo per URL che non devono davvero apparire nella ricerca.",
        "en": "For a public page, remove noindex or none from the server, CDN or application configuration. Keep it only for URLs that genuinely must stay out of search.",
    },
    "a11y_seo_crawl_http_error_title": {
        "uk": "Під час обходу сторінка повернула HTTP-помилку",
        "it": "Durante la scansione la pagina ha restituito un errore HTTP",
        "en": "The page returned an HTTP error during the crawl",
    },
    "a11y_seo_crawl_http_error_found": {
        "uk": "Сервер відповів статусом HTTP {status}.",
        "it": "Il server ha risposto con stato HTTP {status}.",
        "en": "The server responded with HTTP status {status}.",
    },
    "a11y_seo_crawl_http_error_why": {
        "uk": "Сторінка з помилкою не може бути надійно прочитана чи проіндексована. Це виміряний результат конкретної відповіді, а не припущення про адресу поза межами обходу.",
        "it": "Una pagina in errore non può essere letta o indicizzata in modo affidabile. È il risultato misurato di questa risposta, non un'ipotesi su un URL fuori dalla scansione.",
        "en": "A page in error cannot be reliably read or indexed. This is the measured result for this response, not a guess about a URL outside the crawl.",
    },
    "a11y_seo_crawl_http_error_fix": {
        "uk": "Відновіть сторінку або налаштуйте коректний редирект на актуальну адресу. Якщо ресурс навмисно прибрано, видаліть внутрішні посилання на нього та поверніть коректну відповідь для його стану.",
        "it": "Ripristina la pagina oppure configura un reindirizzamento corretto verso l'URL attuale. Se la risorsa è stata rimossa intenzionalmente, elimina i link interni e restituisci la risposta adatta al suo stato.",
        "en": "Restore the page or configure a correct redirect to its current URL. If the resource was intentionally removed, remove internal links to it and return the response appropriate to its state.",
    },
    "a11y_seo_robots_root_disallowed_title": {
        "uk": "robots.txt забороняє обхід усього сайту",
        "it": "robots.txt vieta la scansione dell'intero sito",
        "en": "robots.txt disallows crawling the whole site",
    },
    "a11y_seo_robots_root_disallowed_found": {
        "uk": "Група User-agent: * містить Disallow: {path}.",
        "it": "Il gruppo User-agent: * contiene Disallow: {path}.",
        "en": "The User-agent: * group contains Disallow: {path}.",
    },
    "a11y_seo_robots_root_disallowed_why": {
        "uk": "Це явно забороняє звичайним пошуковим роботам обходити весь шлях сайту. Висновок стосується лише глобальної директиви, а не правил для окремого бота.",
        "it": "Questo vieta esplicitamente ai crawler generici di esplorare l'intero percorso del sito. Il rilievo riguarda solo la direttiva globale, non le regole per un bot specifico.",
        "en": "This explicitly prevents generic search crawlers from visiting the site's whole path. The finding concerns only the global directive, not rules for a specific bot.",
    },
    "a11y_seo_robots_root_disallowed_fix": {
        "uk": "Якщо сайт має бути доступним для пошуку, приберіть Disallow: / з групи User-agent: *. Лишайте його лише для приватного або тимчасового середовища.",
        "it": "Se il sito deve essere disponibile nella ricerca, rimuovi Disallow: / dal gruppo User-agent: *. Mantienilo solo per un ambiente privato o temporaneo.",
        "en": "If the site should be available to search, remove Disallow: / from the User-agent: * group. Keep it only for a private or temporary environment.",
    },
    "a11y_seo_sitemap_http_error_title": {
        "uk": "Оголошена sitemap повертає HTTP-помилку",
        "it": "La sitemap dichiarata restituisce un errore HTTP",
        "en": "A declared sitemap returns an HTTP error",
    },
    "a11y_seo_sitemap_http_error_found": {
        "uk": "robots.txt оголошує цю sitemap, але сервер відповів HTTP {status}.",
        "it": "robots.txt dichiara questa sitemap, ma il server ha risposto HTTP {status}.",
        "en": "robots.txt declares this sitemap, but the server responded with HTTP {status}.",
    },
    "a11y_seo_sitemap_http_error_why": {
        "uk": "Пошуковий робот, що прочитав цей запис у robots.txt, не може отримати оголошену карту URL. Це факт відповіді для адреси, яку сам сайт вказав.",
        "it": "Un crawler che legge questa riga in robots.txt non può ottenere la mappa URL dichiarata. È un fatto della risposta per l'indirizzo indicato dal sito stesso.",
        "en": "A crawler that reads this robots.txt entry cannot fetch the declared URL map. This is a response fact for an address the site itself named.",
    },
    "a11y_seo_sitemap_http_error_fix": {
        "uk": "Відновіть sitemap або змініть її URL у robots.txt на актуальний. Перевірте відповідь без авторизації та після редиректів.",
        "it": "Ripristina la sitemap oppure aggiorna il suo URL in robots.txt. Verifica la risposta senza autenticazione e dopo i reindirizzamenti.",
        "en": "Restore the sitemap or update its URL in robots.txt. Verify the response without authentication and after redirects.",
    },
    "a11y_seo_sitemap_invalid_title": {
        "uk": "Оголошена sitemap не є коректним XML",
        "it": "La sitemap dichiarata non è XML valido",
        "en": "A declared sitemap is not valid XML",
    },
    "a11y_seo_sitemap_invalid_found": {
        "uk": "Адреса sitemap віддає текст, який XML-парсер не може прочитати.",
        "it": "L'indirizzo della sitemap restituisce testo che il parser XML non riesce a leggere.",
        "en": "The sitemap URL returns text the XML parser cannot read.",
    },
    "a11y_seo_sitemap_invalid_why": {
        "uk": "HTTP 200 ще не означає, що карта URL придатна для обробки. Ця перевірка підтверджує синтаксис XML, але не підміняє перевірку всіх URL у карті.",
        "it": "HTTP 200 non significa ancora che la mappa URL sia elaborabile. Questo controllo conferma la sintassi XML, ma non sostituisce la verifica di ogni URL nella mappa.",
        "en": "HTTP 200 does not yet mean the URL map can be processed. This check confirms XML syntax, but does not substitute for validating every URL in the map.",
    },
    "a11y_seo_sitemap_invalid_fix": {
        "uk": "Виправте XML, щоб він мав один кореневий елемент і коректно екранував спеціальні символи. Після виправлення знову перевірте саме оголошену адресу.",
        "it": "Correggi l'XML affinché abbia un solo elemento radice ed esegua correttamente l'escape dei caratteri speciali. Dopo la correzione verifica di nuovo l'indirizzo dichiarato.",
        "en": "Fix the XML so it has one root element and properly escapes special characters. Afterward, verify the declared address again.",
    },
    "a11y_seo_internal_link_failed_title": {
        "uk": "Внутрішнє посилання веде на сторінку з HTTP-помилкою",
        "it": "Un link interno porta a una pagina con errore HTTP",
        "en": "An internal link points to a page with an HTTP error",
    },
    "a11y_seo_internal_link_failed_found": {
        "uk": "Посилання {href} веде на {target}, де обходом отримано HTTP {status}.",
        "it": "Il link {href} porta a {target}, dove la scansione ha ricevuto HTTP {status}.",
        "en": "The link {href} points to {target}, where the crawl received HTTP {status}.",
    },
    "a11y_seo_internal_link_failed_why": {
        "uk": "Відвідувач і пошуковий робот переходять за цим посиланням у відповідь з помилкою. Висновок зроблено лише тому, що ціль уже була фактично отримана цим самим обходом.",
        "it": "Il visitatore e il crawler seguono questo link fino a una risposta in errore. La conclusione viene riportata solo perché la destinazione è stata già ricevuta dalla stessa scansione.",
        "en": "Visitors and crawlers follow this link to an error response. It is reported only because the same crawl already fetched the destination.",
    },
    "a11y_seo_internal_link_failed_fix": {
        "uk": "Замініть URL на актуальну сторінку, відновіть ціль або налаштуйте редирект. Не маскуйте проблему посиланням на головну сторінку, якщо вона не є змістовною заміною.",
        "it": "Sostituisci l'URL con la pagina attuale, ripristina la destinazione o configura un reindirizzamento. Non mascherare il problema con un link alla home se non è una sostituzione pertinente.",
        "en": "Replace the URL with the current page, restore the destination or configure a redirect. Do not mask the problem with a home-page link when it is not a relevant replacement.",
    },
    "a11y_i18n_composite_admin_text_title": {
        "uk": "Складене значення віддане на переклад цілком",
        "it": "Un valore composito è dato in traduzione per intero",
        "en": "A composite value is handed over for translation whole",
    },
    "a11y_i18n_composite_admin_text_found": {
        "uk": 'Ключ "{key}" оголошений у <admin-texts>, але код розбирає це значення на частини ({call} у {where}), тобто в ньому зберігається запис, а не рядок.',
        "it": 'La chiave "{key}" è dichiarata in <admin-texts>, ma il codice scompone quel valore ({call} in {where}): dentro c\'è un record, non una stringa.',
        "en": 'The key "{key}" is declared in <admin-texts>, yet the code takes that value apart ({call} in {where}): what it holds is a record, not a string.',
    },
    "a11y_i18n_composite_admin_text_why": {
        "uk": "Оголошення в <admin-texts> означає «перекладай це значення». Якщо значення є записом - рядки виду «підпис|URL» або JSON - перекладачеві віддають ще й роздільники, URL і саму структуру. Один загублений роздільник прибирає елемент зі сторінки без жодної помилки, а зміна порядку елементів зсуває всі переклади. Крім того, URL стають редагованими з екрана перекладу, де їх ніхто не чекає.",
        "it": "Dichiarare una chiave in <admin-texts> significa «traduci questo valore». Se il valore è un record - righe tipo «etichetta|URL» oppure JSON - al traduttore si consegnano anche i separatori, gli URL e la struttura stessa. Un separatore perso rimuove l'elemento dalla pagina senza alcun errore, e riordinare gli elementi disallinea tutte le traduzioni. In più gli URL diventano modificabili dalla schermata di traduzione, dove nessuno se li aspetta.",
        "en": "Declaring a key in <admin-texts> says 'translate this value'. When the value is a record - lines like 'label|URL', or JSON - the translator is handed the separators, the URLs and the structure as well. One lost separator removes the item from the page with no error at all, and reordering the items shifts every translation. The URLs also become editable from the translation screen, where nobody expects them.",
    },
    "a11y_i18n_composite_admin_text_fix": {
        "uk": "Приберіть цей ключ із <admin-texts> і реєструйте на переклад окремі частини запису, по одному рядку на підпис, лишивши URL і технічні поля поза перекладом. Якщо запис за природою є списком посилань, розгляньте штатне меню замість поля з опціями: меню перекладається власним потоком і не має цієї крихкості.",
        "it": "Togli questa chiave da <admin-texts> e registra per la traduzione le singole parti del record, una stringa per etichetta, lasciando fuori URL e campi tecnici. Se il record è per natura un elenco di link, valuta un menu invece di un campo opzione: un menu si traduce con il proprio flusso e non ha questa fragilità.",
        "en": "Remove this key from <admin-texts> and register the parts of the record instead, one string per label, leaving URLs and technical fields out of translation. If the record is really a list of links, consider a menu rather than an option field: a menu is translated by its own flow and does not carry this fragility.",
    },
    "a11y_i18n_taxonomy_not_declared_title": {
        "uk": "Таксономія не оголошена перекладною",
        "it": "La tassonomia non è dichiarata traducibile",
        "en": "The taxonomy is not declared translatable",
    },
    "a11y_i18n_taxonomy_not_declared_found": {
        "uk": 'Код проєкту використовує таксономію "{taxonomy}" ({where}), але вона не оголошена в <taxonomies> у wpml-config.xml.',
        "it": 'Il codice del progetto usa la tassonomia "{taxonomy}" ({where}), ma non è dichiarata in <taxonomies> in wpml-config.xml.',
        "en": 'The project code uses the "{taxonomy}" taxonomy ({where}) but does not declare it in <taxonomies> in wpml-config.xml.',
    },
    "a11y_i18n_taxonomy_not_declared_why": {
        "uk": "Без оголошення WPML лишає таксономію в режимі за замовчуванням «не перекладати», і це не половинчастий переклад, а повна його відсутність: get_terms() віддає терміни мовою оригіналу в усіх мовах, на кожній сторінці, де вони перелічені. Помітити це в розмітці неможливо, і жоден обсяг перекладу в адмінці цього не змінює, поки не змінено саме налаштування.",
        "it": "Senza la dichiarazione WPML lascia la tassonomia nella modalità predefinita «non tradurre», e non è una traduzione a metà ma la sua assenza completa: get_terms() restituisce i termini nella lingua di origine in tutte le lingue, su ogni pagina che li elenca. Nel markup non si vede, e nessuna quantità di traduzione fatta in admin lo cambia finché non si cambia l'impostazione.",
        "en": "Without the declaration WPML leaves the taxonomy on its default «do not translate», and that is not a half-translation but the absence of one: get_terms() returns source-language terms in every language, on every page that lists them. Nothing in the markup shows it, and no amount of translating in the admin changes it until the setting itself changes.",
    },
    "a11y_i18n_taxonomy_not_declared_fix": {
        "uk": "Додайте <taxonomy translate=\"1\">{taxonomy}</taxonomy> у блок <taxonomies> у wpml-config.xml, а для службової таксономії, невидимої користувачеві, поставте translate=\"0\" явно. Оголошення лише дозволяє переклад: самі терміни після цього треба перекласти й привʼязати до перекладених записів.",
        "it": "Aggiungi <taxonomy translate=\"1\">{taxonomy}</taxonomy> nel blocco <taxonomies> di wpml-config.xml; per una tassonomia di servizio, mai esposta all'utente, metti translate=\"0\" in modo esplicito. La dichiarazione abilita soltanto la traduzione: i termini vanno poi tradotti e associati ai contenuti tradotti.",
        "en": "Add <taxonomy translate=\"1\">{taxonomy}</taxonomy> to the <taxonomies> block in wpml-config.xml, and for a service taxonomy never shown to a reader set translate=\"0\" explicitly. The declaration only enables translation: the terms themselves still have to be translated and attached to the translated content.",
    },
    "a11y_seo_untranslated_content_title": {
        "uk": "Текст лишився мовою іншої версії",
        "it": "Il testo è rimasto nella lingua di un'altra versione",
        "en": "The text stayed in another version's language",
    },
    "a11y_seo_untranslated_content_found": {
        "uk": 'На цій сторінці «{text}» дослівно збігається з версією "{language}", хоча решта сторінки перекладена: {translated} інших відповідних місць відрізняються. Місце: {where}.',
        "it": 'Su questa pagina «{text}» coincide alla lettera con la versione "{language}", benché il resto della pagina sia tradotto: {translated} altri punti corrispondenti differiscono. Posizione: {where}.',
        "en": 'On this page "{text}" matches the "{language}" version word for word, although the rest of the page is translated: {translated} other matching places differ. Position: {where}.',
    },
    "a11y_seo_untranslated_content_why": {
        "uk": "Однаковий рядок сам по собі нічого не означає: сторінка могла бути ідентичною цілком. Тут інакше - навколо нього все перекладено, тому саме цей фрагмент лишився позаду. Такі місця зазвичай приходять не з контенту, а з коду: підпис, узятий не з системи перекладу, або значення, скопійоване з оригіналу без прив'язки до мови. Читач бачить чужу мову посеред своєї, а пошук отримує сторінку, яка частково дублює іншу мовну версію.",
        "it": "Una stringa identica di per sé non significa nulla: la pagina poteva essere identica per intero. Qui è diverso: tutto intorno è tradotto, quindi è proprio questo frammento a essere rimasto indietro. Questi punti di solito non vengono dai contenuti ma dal codice: un'etichetta che non passa dal sistema di traduzione, o un valore copiato dall'originale senza legame con la lingua. Il lettore vede un'altra lingua in mezzo alla propria e i motori ricevono una pagina che duplica in parte un'altra versione linguistica.",
        "en": "An identical string means nothing on its own: the page could have been identical throughout. Here it is different - everything around it is translated, so this fragment is the one left behind. Such places usually come from the code rather than the content: a label that does not pass through the translation system, or a value copied from the original with no tie to the language. A reader sees another language in the middle of their own, and search engines get a page that partly duplicates another language version.",
    },
    "a11y_seo_untranslated_content_fix": {
        "uk": "Знайдіть, звідки береться цей рядок. Якщо він приходить із коду, проведіть його через ту саму систему перекладу, що й решту інтерфейсу; якщо з контенту, допишіть переклад у цій мовній версії. Виняток, який тут очікуваний: власні назви, назви організацій і адреси лишаються мовою оригіналу навмисно, і такі знахідки треба просто закрити.",
        "it": "Trova da dove arriva questa stringa. Se viene dal codice, falla passare dallo stesso sistema di traduzione del resto dell'interfaccia; se viene dai contenuti, inserisci la traduzione in questa versione linguistica. L'eccezione attesa: nomi propri, denominazioni di enti e indirizzi restano di proposito nella lingua originale, e queste segnalazioni vanno semplicemente chiuse.",
        "en": "Find where this string comes from. If it comes from the code, route it through the same translation system as the rest of the interface; if it comes from the content, add the translation in this language version. The expected exception: proper nouns, organisation names and addresses stay in the source language on purpose, and those findings should simply be closed.",
    },
    "a11y_link_target_differs_across_translations_title": {
        "uk": "Посилання в перекладі веде не туди, куди в оригіналі",
        "it": "Il link nella traduzione porta altrove rispetto all'originale",
        "en": "A link in the translation goes somewhere other than in the original",
    },
    "a11y_link_target_differs_across_translations_found": {
        "uk": 'Посилання "{text}" веде на {href}, а те саме за позицією посилання у версії "{language}" ("{other_text}") веде на {target}.',
        "it": 'Il link "{text}" porta a {href}, mentre lo stesso link per posizione nella versione "{language}" ("{other_text}") porta a {target}.',
        "en": 'The link "{text}" goes to {href}, while the link in the same position in the "{language}" version ("{other_text}") goes to {target}.',
    },
    "a11y_link_target_differs_across_translations_why": {
        "uk": "Читач бачить те саме слово, а потрапляє на іншу сторінку: у прикладі з аудиту «назва міста» в англійській і німецькій версіях вело до сусіднього села. Нічого не зламано технічно, тож жодна перевірка однієї сторінки цього не бачить, а людина, яка користується програмою читання з екрана, не має способу це помітити, поки не перейде.",
        "it": "Chi legge vede la stessa parola e finisce su un'altra pagina: nell'esempio dell'audit «il nome della città» nelle versioni inglese e tedesca portava a un paese vicino. Tecnicamente nulla è rotto, quindi nessun controllo su una singola pagina lo vede, e chi usa uno screen reader non ha modo di accorgersene prima di seguire il link.",
        "en": "The reader sees the same word and lands on a different page: in the audit's example \"the town's name\" led to a neighbouring village in the English and German versions. Nothing is technically broken, so no single-page check sees it, and a screen reader user has no way to notice until they follow the link.",
    },
    "a11y_link_target_differs_across_translations_fix": {
        "uk": "Звірте обидві адреси. Якщо різниця випадкова, виправте її в мовній версії, де вона хибна. Якщо вона навмисна (інший сайт для іншої мови), закрийте знахідку: інструмент бачить, що адреси різні, але не те, яка з них задумана.",
        "it": "Confronta i due indirizzi. Se la differenza è casuale, correggila nella versione linguistica sbagliata. Se è voluta (un altro sito per un'altra lingua), chiudi la segnalazione: lo strumento vede che gli indirizzi sono diversi, non quale dei due sia quello inteso.",
        "en": "Compare the two addresses. If the difference is accidental, fix it in the language version that is wrong. If it is deliberate (a different site for a different language), close the finding: the tool can see that the addresses differ, not which one was meant.",
    },
    "a11y_seo_slug_not_translated_title": {
        "uk": "Адреса лишилась мовою оригіналу",
        "it": "L'indirizzo è rimasto nella lingua originale",
        "en": "The address stayed in the original language",
    },
    "a11y_seo_slug_not_translated_found": {
        "uk": 'Шлях цієї сторінки збігається з версією "{language}" ({target}), хоча сайт перекладає адреси: {translated} інших пар мовних версій мають різні шляхи.',
        "it": 'Il percorso di questa pagina coincide con la versione "{language}" ({target}), benché il sito traduca gli indirizzi: {translated} altre coppie di versioni linguistiche hanno percorsi diversi.',
        "en": 'This page shares its path with the "{language}" version ({target}), although the site does translate addresses: {translated} other pairs of language versions have different paths.',
    },
    "a11y_seo_slug_not_translated_why": {
        "uk": "Однакові адреси в різних мовах самі по собі не є дефектом: чимало сайтів свідомо тримають один набір слагів. Дефект тут інший - сайт перекладає адреси, але не всі, тому частина сторінок віддає користувачеві й пошуку шлях чужою мовою. Це також розходиться з рештою сайту, тобто виглядає як забута сторінка, а не як рішення.",
        "it": "Indirizzi identici in lingue diverse non sono di per sé un difetto: molti siti mantengono di proposito un solo set di slug. Il difetto qui è un altro: il sito traduce gli indirizzi, ma non tutti, quindi alcune pagine mostrano all'utente e ai motori un percorso in un'altra lingua. È anche incoerente con il resto del sito, quindi sembra una pagina dimenticata e non una scelta.",
        "en": "Identical addresses across languages are not a defect in themselves: plenty of sites keep one set of slugs on purpose. The defect here is different - the site does translate addresses but not all of them, so some pages hand the reader and the search engine a path in another language. It is also inconsistent with the rest of the site, which makes it look like a page that was missed rather than a decision.",
    },
    "a11y_seo_slug_not_translated_fix": {
        "uk": "Перекладіть слаг цієї сторінки так само, як зроблено для решти, і поставте 301 зі старої адреси, якщо сторінка вже проіндексована. Якщо ж рішення протилежне і слаги мають лишатись однаковими, приведіть до цього весь сайт: непослідовність гірша за будь-який із двох варіантів.",
        "it": "Traduci lo slug di questa pagina come è stato fatto per le altre e imposta un 301 dal vecchio indirizzo se la pagina è già indicizzata. Se invece la scelta è opposta e gli slug devono restare uguali, applicala a tutto il sito: l'incoerenza è peggiore di entrambe le opzioni.",
        "en": "Translate this page's slug the way the others were done, and add a 301 from the old address if the page is already indexed. If the decision is the opposite one and slugs are meant to stay identical, apply that across the site: the inconsistency is worse than either choice.",
    },
    "a11y_seo_hreflang_not_reciprocal_title": {
        "uk": "Crawled hreflang-версія не посилається у відповідь",
        "it": "La versione hreflang scansionata non rimanda indietro",
        "en": "The crawled hreflang version does not link back",
    },
    "a11y_seo_hreflang_not_reciprocal_found": {
        "uk": "Для мови {language} оголошено {target}, але в отриманій цільовій сторінці немає посилання назад.",
        "it": "Per la lingua {language} è dichiarato {target}, ma la pagina di destinazione ricevuta non ha un link di ritorno.",
        "en": "The {language} alternate declares {target}, but the fetched target page has no link back.",
    },
    "a11y_seo_hreflang_not_reciprocal_why": {
        "uk": "Це перевірка лише пари сторінок, які реально потрапили в цей обхід. Взаємні hreflang-посилання допомагають пошуковій системі підтвердити, що обидві адреси належать до одного мовного набору.",
        "it": "È un controllo solo della coppia di pagine realmente inclusa in questa scansione. I link hreflang reciproci aiutano il motore a confermare che entrambi gli URL appartengono allo stesso insieme linguistico.",
        "en": "This checks only the page pair actually reached by this crawl. Reciprocal hreflang links help a search engine confirm that both URLs belong to the same language set.",
    },
    "a11y_seo_hreflang_not_reciprocal_fix": {
        "uk": "Додайте на цільову сторінку <link rel=\"alternate\" hreflang=\"…\" href=\"…\">, що повертає на цю адресу. Перевірте обидві сторінки після публікації, включно з нормалізацією URL.",
        "it": "Aggiungi nella pagina di destinazione <link rel=\"alternate\" hreflang=\"…\" href=\"…\"> che riporti a questo URL. Verifica entrambe le pagine dopo la pubblicazione, inclusa la normalizzazione degli URL.",
        "en": "Add a <link rel=\"alternate\" hreflang=\"…\" href=\"…\"> on the target page that returns to this URL. Verify both pages after publishing, including URL normalisation.",
    },
    "a11y_seo_hreflang_parameterised_skipped_title": {
        "uk": "Пошук і фільтри не перевірялися на взаємний hreflang",
        "it": "Ricerca e filtri esclusi dal controllo hreflang reciproco",
        "en": "Search and filter pages left out of the hreflang reciprocity check",
    },
    "a11y_seo_hreflang_parameterised_skipped_found": {
        "uk": "Пропущено адрес із параметрами: {count}. Приклади: {examples}.",
        "it": "Indirizzi con parametri esclusi: {count}. Esempi: {examples}.",
        "en": "Addresses with parameters left out: {count}. For example: {examples}.",
    },
    "a11y_seo_hreflang_parameterised_skipped_why": {
        "uk": "Адреса з параметрами (пошук, фільтр, сортування) вважається окремою сторінкою, лише коли її canonical вказує на неї саму. У цих адрес такого canonical немає, тому вони є видами іншої сторінки, і відсутність зворотного hreflang для них не є дефектом.",
        "it": "Un indirizzo con parametri (ricerca, filtro, ordinamento) conta come pagina a sé solo se il suo canonical punta a sé stesso. Questi indirizzi non lo fanno: sono viste di un'altra pagina, e un hreflang senza ritorno su di essi non è un difetto.",
        "en": "An address with parameters (search, filter, sort) counts as a page of its own only when its canonical names itself. These do not, so they are views of another page, and a missing return hreflang on them is not a defect.",
    },
    "a11y_seo_hreflang_parameterised_skipped_fix": {
        "uk": "Нічого не потрібно. Якщо якась із цих адрес справді окрема сторінка, дайте їй canonical на саму себе, і наступний аудит перевірить її hreflang.",
        "it": "Non serve nulla. Se uno di questi indirizzi è davvero una pagina a sé, dagli un canonical verso sé stesso e il prossimo audit ne controllerà l'hreflang.",
        "en": "Nothing is needed. If one of these addresses really is a page of its own, give it a canonical that names itself and the next audit will check its hreflang.",
    },
    "a11y_link_fragment_missing_title": {
        "uk": "Посилання веде на місце, якого на сторінці немає",
        "it": "Il link punta a un punto che nella pagina non esiste",
        "en": "The link points at a place that is not on the page",
    },
    "a11y_link_fragment_missing_found": {
        "uk": "Знайдено посилання «{text}» на {href}: елемента з таким id на сторінці немає.",
        "it": "Trovato il link «{text}» verso {href}: nella pagina non c'è un elemento con quell'id.",
        "en": "Found the link \"{text}\" to {href}: no element on the page has that id.",
    },
    "a11y_link_fragment_missing_why": {
        "uk": "Браузер не покаже помилки: сторінка просто залишиться на місці. Для односторінкового сайту це вся навігація - пункт меню перестає працювати, і жоден звичайний аудит не скаже чому. Найчастіша причина - id перейменували, а посилання ні.",
        "it": "Il browser non mostra alcun errore: la pagina semplicemente resta dov'è. In un sito di una sola pagina questa è tutta la navigazione: la voce di menu smette di funzionare e nessun audit ordinario dice perché. La causa più frequente è un id rinominato senza aggiornare il link.",
        "en": "The browser shows no error: the page simply stays where it is. On a single-page site this is the whole navigation - the menu item stops working, and nothing in an ordinary audit says why. The usual cause is an id that was renamed while the link was not.",
    },
    "a11y_link_fragment_missing_fix": {
        "uk": "Або поставте id на цільову секцію (<section id=\"pricing\">), або виправте адресу в посиланні. Якщо секцію прибрали навмисно - приберіть і пункт меню, інакше він лишиться пасткою.",
        "it": "Metti l'id sulla sezione di destinazione (<section id=\"pricing\">) oppure correggi l'indirizzo nel link. Se la sezione è stata rimossa di proposito, togli anche la voce di menu: altrimenti resta una trappola.",
        "en": "Either give the target section the id (<section id=\"pricing\">) or correct the link. If the section was removed on purpose, remove the menu item too - otherwise it stays a trap.",
    },
    # ------------------------------------------------------- email and WP
    "a11y_email_font_no_fallback_title": {
        "uk": "Шрифт без запасної родини",
        "it": "Font senza famiglia di riserva",
        "en": "A font with no fallback family",
    },
    "a11y_email_font_no_fallback_found": {
        "uk": "Знайдено font-family: {value} - жодної загальної родини в кінці переліку.",
        "it": "Trovato font-family: {value}, senza alcuna famiglia generica alla fine dell'elenco.",
        "en": "Found font-family: {value} - no generic family at the end of the list.",
    },
    "a11y_email_font_no_fallback_why": {
        "uk": "Поштові клієнти не завантажують вебшрифти: Outlook і Gmail покажуть тим, що вже є в системі. Якщо в переліку немає загальної родини, вибір робить клієнт, і зазвичай це Times New Roman - лист виглядає інакше, ніж макет.",
        "it": "I client di posta non scaricano i webfont: Outlook e Gmail useranno ciò che è già installato. Se nell'elenco non c'è una famiglia generica, la scelta la fa il client, di solito Times New Roman: l'email non somiglia più al progetto grafico.",
        "en": "Mail clients do not download webfonts: Outlook and Gmail render with what is already installed. With no generic family in the list the client picks, and it usually picks Times New Roman - the email stops looking like the design.",
    },
    "a11y_email_font_no_fallback_fix": {
        "uk": "Допишіть у кінець переліку загальну родину: font-family: {value}, Arial, sans-serif. Порядок важливий - клієнт бере перший шрифт, який має.",
        "it": "Aggiungi una famiglia generica in fondo all'elenco: font-family: {value}, Arial, sans-serif. L'ordine conta: il client usa il primo font che possiede.",
        "en": "Add a generic family at the end of the list: font-family: {value}, Arial, sans-serif. Order matters - the client takes the first font it has.",
    },
    "a11y_email_link_no_colour_title": {
        "uk": "Посилання без власного кольору",
        "it": "Link senza un colore proprio",
        "en": "A link with no colour of its own",
    },
    "a11y_email_link_no_colour_found": {
        "uk": "Знайдено посилання «{text}» без color у власному стилі.",
        "it": "Trovato il link «{text}» senza color nello stile inline.",
        "en": "Found the link \"{text}\" with no color in its own style.",
    },
    "a11y_email_link_no_colour_why": {
        "uk": "Клієнт перефарбує посилання сам: Gmail дає синє з підкресленням, застосунок Пошта на iOS - фіолетове для відвіданих, а частина клієнтів у темній темі змінює і колір тексту навколо. Кнопка бренду перетворюється на типове посилання.",
        "it": "Il client ricolora il link da sé: Gmail lo rende blu sottolineato, Mail su iOS lo mostra viola se visitato e alcuni client in tema scuro cambiano anche il testo attorno. Un pulsante con i colori del marchio diventa un link qualunque.",
        "en": "The client repaints it: Gmail gives blue and underlined, Mail on iOS shows visited links purple, and some clients in dark mode change the surrounding text too. A brand-coloured button turns into a default link.",
    },
    "a11y_email_link_no_colour_fix": {
        "uk": "Задайте колір просто в елементі: <a style=\"color:#0b5cad; text-decoration:underline\">. Правило в <style> працює в Gmail і Apple Mail, але Outlook.com вирізає <style> цілком, тому інлайн надійніший.",
        "it": "Imposta il colore direttamente sull'elemento: <a style=\"color:#0b5cad; text-decoration:underline\">. Una regola nel <style> funziona in Gmail e Apple Mail, ma Outlook.com rimuove del tutto <style>, quindi l'inline è più sicuro.",
        "en": "Set the colour on the element itself: <a style=\"color:#0b5cad; text-decoration:underline\">. A rule in <style> works in Gmail and Apple Mail, but Outlook.com strips <style> entirely, so inline is the safer form.",
    },
    "a11y_email_no_preheader_title": {
        "uk": "У листі немає тексту прев'ю (preheader)",
        "it": "L'email non ha un testo di anteprima (preheader)",
        "en": "The email has no preview text (preheader)",
    },
    "a11y_email_no_preheader_found": {
        "uk": "У документі немає прихованого блоку з текстом прев'ю.",
        "it": "Nel documento non c'è un blocco nascosto con il testo di anteprima.",
        "en": "The document has no hidden block carrying preview text.",
    },
    "a11y_email_no_preheader_why": {
        "uk": "Рядок під темою листа в поштовій скриньці клієнт бере з першого тексту в тілі. У шаблоні це майже завжди «Переглянути у браузері» або рядок про відписку - тобто найпомітніше місце в скриньці зайняте текстом для тих, хто лист читати не хоче.",
        "it": "La riga sotto l'oggetto, nella casella di posta, il client la prende dal primo testo nel corpo. In un template è quasi sempre «Visualizza nel browser» o la riga di disiscrizione: il punto più visibile della casella è occupato dal testo per chi l'email non la vuole.",
        "en": "The line under the subject in the inbox is taken from the first text in the body. In a template that is almost always \"View in browser\" or the unsubscribe line - the most visible spot in the inbox, spent on the text written for people who do not want the email.",
    },
    "a11y_email_no_preheader_fix": {
        "uk": "Додайте першим у <body> прихований блок на 40-90 символів, що продовжує тему листа: <div style=\"display:none; max-height:0; overflow:hidden; mso-hide:all\">…</div>. Далі корисно поставити такий самий блок із нерозривними пробілами, щоб клієнт не дотягував текст із верстки.",
        "it": "Metti come primo elemento del <body> un blocco nascosto di 40-90 caratteri che prosegue l'oggetto: <div style=\"display:none; max-height:0; overflow:hidden; mso-hide:all\">…</div>. Subito dopo conviene aggiungere un blocco uguale di spazi unificatori, così il client non recupera testo dal layout.",
        "en": "Put a hidden block of 40-90 characters first in the <body>, continuing the subject line: <div style=\"display:none; max-height:0; overflow:hidden; mso-hide:all\">…</div>. Following it with a block of non-breaking spaces stops the client pulling text out of the layout.",
    },
    "a11y_wp_unescaped_output_title": {
        "uk": "Змінна виводиться в розмітку без екранування",
        "it": "Una variabile viene stampata nel markup senza escaping",
        "en": "A variable is printed into the markup unescaped",
    },
    "a11y_wp_unescaped_output_found": {
        "uk": "Знайдено вивід {value} без esc_html(), esc_attr() чи esc_url().",
        "it": "Trovata la stampa di {value} senza esc_html(), esc_attr() o esc_url().",
        "en": "Found {value} printed with no esc_html(), esc_attr() or esc_url().",
    },
    "a11y_wp_unescaped_output_why": {
        "uk": "WordPress не екранує вивід за вас. Усе, що є в цій змінній - поле мета, параметр запиту, значення опції, яке може задати редактор, - потрапляє на сторінку як розмітка, тож <script> або onerror усередині виконається у браузері кожного відвідувача. Змінна могла бути очищена раніше в коді, тому це порада перевірити, а не вирок.",
        "it": "WordPress non fa l'escaping dell'output al posto tuo. Tutto ciò che sta in quella variabile - un campo meta, un parametro della richiesta, un'opzione modificabile da un redattore - finisce nella pagina come markup, quindi un <script> o un onerror al suo interno viene eseguito nel browser di ogni visitatore. La variabile potrebbe essere già stata ripulita più sopra, perciò questo è un invito a verificare, non una condanna.",
        "en": "WordPress does not escape output for you. Whatever is in that variable - a meta field, a query argument, an option an editor can set - is written into the page as markup, so a <script> or an onerror inside it runs in every visitor's browser. The variable may have been sanitised earlier in the file, so this asks you to check rather than declaring a hole.",
    },
    "a11y_wp_unescaped_output_fix": {
        "uk": "Екрануйте в місці виводу, де це видно: esc_html() для тексту, esc_attr() всередині атрибута, esc_url() для адреси, wp_kses_post() коли розмітка потрібна. Це і є правило WordPress Coding Standards: escape late.",
        "it": "Fai l'escaping nel punto in cui stampi, dove si vede: esc_html() per il testo, esc_attr() dentro un attributo, esc_url() per un indirizzo, wp_kses_post() quando serve del markup. È la regola dei WordPress Coding Standards: escape late.",
        "en": "Escape at the point of output, where it can be seen: esc_html() for text, esc_attr() inside an attribute, esc_url() for a URL, wp_kses_post() where markup is genuinely needed. That is the WordPress coding standards rule: escape late.",
    },
    # --------------------------------------------------------------- JSX
    # Checks that exist only because the file is a React source file. The
    # wording of each fix follows `eslint-plugin-jsx-a11y`, whose errors the
    # developer reading this has already seen in their editor.
    "a11y_jsx_label_not_associated_title": {
        "uk": "Мітка <label> ні з чим не звʼязана",
        "it": "L'etichetta <label> non è associata a nulla",
        "en": "The <label> is associated with nothing",
    },
    "a11y_jsx_label_not_associated_found": {
        "uk": "Знайдено <label> з текстом «{text}»: немає ні htmlFor, ні поля всередині.",
        "it": "Trovato un <label> con il testo «{text}»: senza htmlFor e senza campo all'interno.",
        "en": "Found a <label> reading \"{text}\": no htmlFor and no field inside it.",
    },
    "a11y_jsx_label_not_associated_why": {
        "uk": "Такий підпис є звичайним текстом поруч із полем. Програма читання з екрана оголосить поле без назви, а клік по підпису не поставить у нього курсор - тобто зона натискання зменшується до самого поля.",
        "it": "Una didascalia così è solo testo accanto al campo. Uno screen reader annuncia il campo senza nome e il clic sull'etichetta non porta il cursore nel campo: l'area cliccabile si riduce al campo stesso.",
        "en": "A caption like this is just text next to the field. A screen reader announces the field with no name, and clicking the caption does not focus it, so the target area shrinks to the field itself.",
    },
    "a11y_jsx_label_not_associated_fix": {
        "uk": "Додайте htmlFor={{id}} з тим самим id, що й у поля, або загорніть поле всередину <label>. У JSX атрибут пишеться htmlFor, а не for.",
        "it": "Aggiungi htmlFor={{id}} con lo stesso id del campo, oppure racchiudi il campo dentro <label>. In JSX l'attributo si scrive htmlFor, non for.",
        "en": "Add htmlFor={{id}} matching the field's id, or wrap the field inside the <label>. In JSX the attribute is htmlFor, not for.",
    },
    "a11y_jsx_click_without_key_title": {
        "uk": "Обробник кліку, до якого не дістатись з клавіатури",
        "it": "Gestore di clic irraggiungibile da tastiera",
        "en": "A click handler no keyboard can reach",
    },
    "a11y_jsx_click_without_key_found": {
        "uk": "Знайдено <{element}> з onClick і без жодного обробника клавіш (onKeyDown, onKeyUp, onKeyPress).",
        "it": "Trovato <{element}> con onClick e senza alcun gestore di tastiera (onKeyDown, onKeyUp, onKeyPress).",
        "en": "Found <{element}> with onClick and no key handler at all (onKeyDown, onKeyUp, onKeyPress).",
    },
    "a11y_jsx_click_without_key_why": {
        "uk": "Кнопка і посилання самі перетворюють Enter і пробіл на клік. Звичайний елемент - ні, тому дія існує лише для миші: людина з клавіатурою, зі скрін-рідером або з голосовим керуванням виконати її не може.",
        "it": "Pulsanti e link trasformano da soli Invio e barra spaziatrice in un clic. Un elemento qualsiasi no, quindi l'azione esiste solo per il mouse: chi usa tastiera, screen reader o comandi vocali non può eseguirla.",
        "en": "A button or a link turns Enter and Space into a click by itself. A plain element does not, so the action exists for a mouse only: someone on a keyboard, a screen reader or voice control cannot perform it.",
    },
    "a11y_jsx_click_without_key_fix": {
        "uk": "Найкраще - зробити елемент <button type=\"button\">: він дає і фокус, і клавіші, і роль. Якщо розмітку змінити не можна, додайте onKeyDown, який реагує на Enter і Space, разом із role і tabIndex={{0}}.",
        "it": "La soluzione migliore è usare <button type=\"button\">: dà focus, tastiera e ruolo insieme. Se il markup non si può cambiare, aggiungi un onKeyDown che reagisce a Invio e barra spaziatrice, insieme a role e tabIndex={{0}}.",
        "en": "Best fix: make it a <button type=\"button\"> - that gives focus, keys and role at once. If the markup cannot change, add an onKeyDown handling Enter and Space, together with a role and tabIndex={{0}}.",
    },
    "a11y_jsx_noninteractive_handler_title": {
        "uk": "Дія на елементі, який ніхто не оголошує контролом",
        "it": "Azione su un elemento che nessuno annuncia come controllo",
        "en": "An action on something nothing announces as a control",
    },
    "a11y_jsx_noninteractive_handler_found": {
        "uk": "Знайдено <{element}> з onClick. Роль: {role}; у порядку табуляції: {focusable}.",
        "it": "Trovato <{element}> con onClick. Ruolo: {role}; nell'ordine di tabulazione: {focusable}.",
        "en": "Found <{element}> with onClick. Role: {role}; in the tab order: {focusable}.",
    },
    "a11y_jsx_noninteractive_handler_why": {
        "uk": "Клікабельний <div> залишається для скрін-рідера групою тексту: він не оголошується як кнопка, на нього не переводять фокус клавішею Tab і його не знайти в списку елементів керування. Обробник клавіш сам по собі цього не змінює.",
        "it": "Un <div> cliccabile resta, per uno screen reader, un gruppo di testo: non viene annunciato come pulsante, non riceve il focus con Tab e non compare nell'elenco dei controlli. Aggiungere solo un gestore di tastiera non cambia questo.",
        "en": "A clickable <div> stays a group of text to a screen reader: it is not announced as a button, Tab does not stop on it, and it is missing from the controls list. A key handler alone does not change that.",
    },
    "a11y_jsx_noninteractive_handler_fix": {
        "uk": "Замініть елемент на <button type=\"button\">. Якщо це неможливо, поставте одночасно role=\"button\" і tabIndex={{0}} - одне без другого залишає половину роботи.",
        "it": "Sostituisci l'elemento con <button type=\"button\">. Se non è possibile, metti insieme role=\"button\" e tabIndex={{0}}: uno senza l'altro lascia il lavoro a metà.",
        "en": "Replace the element with <button type=\"button\">. If that is impossible, give it both role=\"button\" and tabIndex={{0}} - either one alone leaves half the job undone.",
    },
    "a11y_jsx_tabindex_on_static_title": {
        "uk": "Зупинка в порядку табуляції без жодної дії",
        "it": "Una fermata nell'ordine di tabulazione senza alcuna azione",
        "en": "A stop in the tab order with nothing behind it",
    },
    "a11y_jsx_tabindex_on_static_found": {
        "uk": "Знайдено <{element}> з tabIndex={value} і без дії на цьому елементі.",
        "it": "Trovato <{element}> con tabIndex={value} e senza alcuna azione sull'elemento.",
        "en": "Found <{element}> with tabIndex={value} and no action on the element.",
    },
    "a11y_jsx_tabindex_on_static_why": {
        "uk": "Клавіша Tab має вести по тому, що можна зробити. Кожна зайва зупинка на тексті подовжує шлях до справжніх контролів, а людина на ній не отримує нічого: фокус стоїть, робити нічого.",
        "it": "Il tasto Tab dovrebbe percorrere ciò che si può fare. Ogni fermata superflua su del testo allunga il percorso verso i controlli veri e non offre nulla: il focus è lì e non c'è niente da fare.",
        "en": "Tab should walk what can be done. Every extra stop on plain text lengthens the path to the real controls and gives the person nothing when they arrive: focus is there, and there is nothing to do.",
    },
    "a11y_jsx_tabindex_on_static_fix": {
        "uk": "Приберіть tabIndex. Якщо елемент справді має бути дією - зробіть його <button>; якщо це ціль для програмного фокуса (модальне вікно, повідомлення), правильне значення tabIndex={{-1}}.",
        "it": "Rimuovi tabIndex. Se l'elemento deve davvero essere un'azione, rendilo un <button>; se è un bersaglio per il focus da codice (una finestra modale, un messaggio), il valore corretto è tabIndex={{-1}}.",
        "en": "Remove the tabIndex. If the element really is an action, make it a <button>; if it is a target for scripted focus (a dialog, a message), the correct value is tabIndex={{-1}}.",
    },
    "a11y_jsx_untranslated_literal_title": {
        "uk": "Текст для людини записано літералом у файлі, який решту перекладає",
        "it": "Testo per la persona scritto come letterale in un file che traduce il resto",
        "en": "Text a person reads written as a literal in a file that translates the rest",
    },
    "a11y_jsx_untranslated_literal_found": {
        "uk": "{attribute}=\"{value}\" не проходить через переклад, хоча інші тексти цього файлу проходять.",
        "it": "{attribute}=\"{value}\" non passa dalla traduzione, mentre gli altri testi di questo file sì.",
        "en": "{attribute}=\"{value}\" is not translated, while the other texts of this file are.",
    },
    "a11y_jsx_untranslated_literal_why": {
        "uk": "У версії застосунку іншою мовою цей текст лишиться тим самим. Скрін-рідер прочитає його з вимовою мови сторінки, і людина почує набір незрозумілих звуків або назву, якої не впізнає.",
        "it": "Nella versione dell'app in un'altra lingua questo testo resta uguale. Uno screen reader lo legge con la pronuncia della lingua della pagina, e la persona sente suoni incomprensibili o un nome che non riconosce.",
        "en": "In the app's version in another language this text stays the same. A screen reader reads it with the page language's pronunciation, and the person hears noise or a name they do not recognise.",
    },
    "a11y_jsx_untranslated_literal_fix": {
        "uk": "Передайте текст через ту саму функцію перекладу, що й решту (t(\"…\")), або через проп чи контекст, який задає застосунок. Якщо це назва бренду чи приклад, однаковий у всіх мовах, знахідку можна лишити.",
        "it": "Fai passare il testo dalla stessa funzione di traduzione del resto (t(\"…\")), oppure da una prop o un contesto che l'app imposta. Se è un marchio o un esempio uguale in tutte le lingue, la segnalazione si può ignorare.",
        "en": "Pass the text through the same translation function as the rest (t(\"…\")), or through a prop or context the app sets. If it is a brand name or an example that is the same in every language, it can stay.",
    },
    "a11y_jsx_autofocus_title": {
        "uk": "autoFocus переносить фокус до того, як сторінку прочитали",
        "it": "autoFocus sposta il focus prima che la pagina sia stata letta",
        "en": "autoFocus moves focus before the page has been read",
    },
    "a11y_jsx_autofocus_found": {
        "uk": "Знайдено <{element}> з autoFocus.",
        "it": "Trovato <{element}> con autoFocus.",
        "en": "Found <{element}> with autoFocus.",
    },
    "a11y_jsx_autofocus_why": {
        "uk": "Скрін-рідер починає читати від сфокусованого елемента, тож усе вище - зокрема пояснення, для чого ця форма, - буде пропущене. Людина з екранним збільшувачем раптово опиняється в іншій частині сторінки.",
        "it": "Uno screen reader inizia a leggere dall'elemento con il focus, quindi tutto ciò che sta sopra - compresa la spiegazione di che cosa serve il modulo - viene saltato. Chi usa un ingranditore si ritrova all'improvviso in un'altra parte della pagina.",
        "en": "A screen reader starts reading from the focused element, so everything above it - including what the form is for - is skipped. Someone using a magnifier is moved to a different part of the page without asking.",
    },
    "a11y_jsx_autofocus_fix": {
        "uk": "Приберіть autoFocus і ставте фокус тоді, коли людина сама відкрила саме цей елемент: модальне вікно, крок майстра, поле пошуку на сторінці пошуку. Це рішення залежить від сторінки, тому знахідка є порадою, а не помилкою.",
        "it": "Togli autoFocus e sposta il focus quando è la persona ad aprire proprio quell'elemento: una finestra modale, un passaggio di procedura guidata, il campo di ricerca in una pagina di ricerca. È una scelta che dipende dalla pagina, perciò qui è un consiglio, non un errore.",
        "en": "Remove autoFocus and set focus when the person themselves opened that element: a dialog, a wizard step, the search field on a search page. The call depends on the page, which is why this is advice rather than an error.",
    },
    "a11y_jsx_anchor_not_a_link_title": {
        "uk": "Посилання без адреси, яке працює лише мишею",
        "it": "Un link senza indirizzo, utilizzabile solo con il mouse",
        "en": "A link with no address, usable by mouse only",
    },
    "a11y_jsx_anchor_not_a_link_found": {
        "uk": "Знайдено <a> з onClick і href={href}.",
        "it": "Trovato <a> con onClick e href={href}.",
        "en": "Found an <a> with onClick and href={href}.",
    },
    "a11y_jsx_anchor_not_a_link_why": {
        "uk": "Без href браузер не вважає це посиланням: елемент не отримує фокус клавішею Tab і не оголошується як посилання. href=\"#\" робить те саме, лише додатково прокручує сторінку вгору.",
        "it": "Senza href il browser non lo considera un link: l'elemento non riceve il focus con Tab e non viene annunciato come link. href=\"#\" fa lo stesso, in più riporta la pagina in cima.",
        "en": "With no href the browser does not treat this as a link: it takes no Tab focus and is not announced as a link. href=\"#\" does the same thing and additionally scrolls the page to the top.",
    },
    "a11y_jsx_anchor_not_a_link_fix": {
        "uk": "Якщо це перехід - поставте справжній href (у React Router - <Link to=\"…\">). Якщо це дія на цій самій сторінці - це кнопка: <button type=\"button\">.",
        "it": "Se è una navigazione, metti un href vero (con React Router, <Link to=\"…\">). Se è un'azione sulla stessa pagina, è un pulsante: <button type=\"button\">.",
        "en": "If it navigates, give it a real href (in React Router, <Link to=\"…\">). If it acts on this page, it is a button: <button type=\"button\">.",
    },
    "a11y_jsx_dangerous_html_title": {
        "uk": "Розмітка вставляється в сторінку через dangerouslySetInnerHTML",
        "it": "Markup inserito nella pagina tramite dangerouslySetInnerHTML",
        "en": "Markup written into the page through dangerouslySetInnerHTML",
    },
    "a11y_jsx_dangerous_html_found": {
        "uk": "Знайдено <{element}> з dangerouslySetInnerHTML.",
        "it": "Trovato <{element}> con dangerouslySetInnerHTML.",
        "en": "Found <{element}> with dangerouslySetInnerHTML.",
    },
    "a11y_jsx_dangerous_html_why": {
        "uk": "Цей рядок парситься як HTML, тому <script> або onerror усередині нього виконається. Значення зазвичай приходить іздалеку - з CMS, з API, з рендерера Markdown, - і файл, який його виводить, не є тим файлом, який його очищає.",
        "it": "Quella stringa viene interpretata come HTML, quindi un <script> o un onerror al suo interno viene eseguito. Il valore di solito arriva da lontano - un CMS, un'API, un renderer Markdown - e il file che lo mostra non è il file che lo ripulisce.",
        "en": "That string is parsed as HTML, so a <script> or an onerror inside it runs. The value usually arrives from somewhere else - a CMS field, an API, a Markdown renderer - and the file that renders it is not the file that sanitises it.",
    },
    "a11y_jsx_dangerous_html_fix": {
        "uk": "Перевірте, звідки береться значення, і очищайте його бібліотекою на кшталт DOMPurify безпосередньо перед вставкою. Якщо потрібен лише текст - виведіть його як текст: React екранує його сам.",
        "it": "Verifica da dove arriva il valore e ripuliscilo con una libreria come DOMPurify subito prima dell'inserimento. Se serve solo testo, mostralo come testo: React lo esegue l'escape da solo.",
        "en": "Check where the value comes from and sanitise it with something like DOMPurify immediately before it is inserted. If only text is needed, render it as text: React escapes that for you.",
    },
    "a11y_geo_article_schema_title": {
        "uk": "Стаття не має машиночитаного типу",
        "it": "L'articolo non ha un tipo leggibile dalla macchina",
        "en": "The article has no machine-readable type",
    },
    "a11y_geo_article_schema_found": {
        "uk": "На сторінці є <article>, але немає JSON-LD або microdata з типом Article, NewsArticle чи BlogPosting.",
        "it": "La pagina contiene <article>, ma non JSON-LD o microdata con tipo Article, NewsArticle o BlogPosting.",
        "en": "The page contains <article>, but has no JSON-LD or microdata of type Article, NewsArticle or BlogPosting.",
    },
    "a11y_geo_article_schema_why": {
        "uk": "Це не прогноз цитування чи позицій. Це сигнал для редакційної перевірки: тип у розмітці прямо пояснює пошуку й асистентам, що сторінка є статтею, а не загальною вебсторінкою.",
        "it": "Non è una previsione di citazioni o posizioni. È un segnale per la revisione editoriale: il tipo nel markup dice direttamente a motori e assistenti che la pagina è un articolo e non una pagina generica.",
        "en": "This is not a citation or ranking prediction. It is an editorial-review signal: the markup type tells search engines and assistants directly that the page is an article rather than a generic web page.",
    },
    "a11y_geo_article_schema_fix": {
        "uk": "Якщо це редакційний матеріал, додайте правдивий JSON-LD Article, NewsArticle або BlogPosting. Не додавайте тип лише заради перевірки: він має відповідати видимому вмісту сторінки.",
        "it": "Se è contenuto editoriale, aggiungi JSON-LD veritiero Article, NewsArticle o BlogPosting. Non aggiungere il tipo solo per superare il controllo: deve corrispondere al contenuto visibile.",
        "en": "If this is editorial content, add truthful Article, NewsArticle or BlogPosting JSON-LD. Do not add a type merely to pass the check: it must match the page's visible content.",
    },
    "a11y_geo_article_provenance_title": {
        "uk": "У статті бракує машиночитаного авторства або дати",
        "it": "All'articolo manca autore o data leggibili dalla macchina",
        "en": "The article lacks machine-readable authorship or a date",
    },
    "a11y_geo_article_provenance_found": {
        "uk": "Не знайдено: {missing}.",
        "it": "Non trovato: {missing}.",
        "en": "Not found: {missing}.",
    },
    "a11y_geo_article_provenance_why": {
        "uk": "Це кандидат для редакційної перевірки, а не твердження, що даних немає у видимому тексті. Семантичні авторство й дата допомагають системам зіставити матеріал з джерелом та його актуальністю без здогадування з верстки.",
        "it": "È un candidato per la revisione editoriale, non l'affermazione che i dati manchino dal testo visibile. Autore e data semantici aiutano i sistemi ad associare il contenuto alla fonte e alla sua attualità senza indovinare dal layout.",
        "en": "This is an editorial-review candidate, not a claim that the data is absent from visible prose. Semantic author and date values help systems associate content with its source and freshness without guessing from layout.",
    },
    "a11y_geo_article_provenance_fix": {
        "uk": "Додайте справжнього автора й дату публікації в JSON-LD Article або semantic HTML, наприклад <time datetime=\"2026-08-31\">. Не вигадуйте автора, дату чи дату оновлення.",
        "it": "Aggiungi autore reale e data di pubblicazione in JSON-LD Article o HTML semantico, per esempio <time datetime=\"2026-08-31\">. Non inventare autore, data o data di aggiornamento.",
        "en": "Add the real author and publication date in Article JSON-LD or semantic HTML, for example <time datetime=\"2026-08-31\">. Do not invent an author, date or update date.",
    },
    "a11y_seo_open_graph_title": {
        "uk": "Немає розмітки для прев'ю посилання",
        "it": "Manca il markup per l'anteprima del link",
        "en": "No markup for link previews",
    },
    "a11y_seo_open_graph_found": {
        "uk": "Відсутні теги Open Graph: {missing}.",
        "it": "Tag Open Graph mancanti: {missing}.",
        "en": "Missing Open Graph tags: {missing}.",
    },
    "a11y_seo_open_graph_why": {
        "uk": "Коли посиланням діляться в месенджері чи соцмережі, картку прев'ю збирають саме з цих тегів. Без них показується гола адреса або випадковий уривок з випадковою картинкою зі сторінки. Різниця у кліках тут велика, і вона стосується найтеплішого трафіку - того, що прийшов за особистою рекомендацією.",
        "it": "Quando il link viene condiviso in una chat o sui social, l'anteprima si costruisce proprio da questi tag. Senza di essi si vede l'indirizzo nudo oppure un frammento casuale con un'immagine casuale della pagina. La differenza nei clic è grande e riguarda il traffico più caldo: quello arrivato per raccomandazione personale.",
        "en": "When a link is shared in a chat app or on social media, the preview card is built from exactly these tags. Without them the recipient sees a bare address, or a random excerpt with a random image from the page. The difference in clicks is large, and it applies to the warmest traffic there is - the kind that arrives on a personal recommendation.",
    },
    "a11y_seo_open_graph_fix": {
        "uk": "Додайте в <head> три теги: og:title, og:description і og:image з абсолютною адресою картинки приблизно 1200x630. Заголовок і опис можуть відрізнятися від пошукових - тут вони пишуться для людини, яка вже отримала посилання від знайомого.",
        "it": "Aggiungi nel <head> tre tag: og:title, og:description e og:image con l'URL assoluto di un'immagine di circa 1200x630. Titolo e descrizione possono differire da quelli per la ricerca: qui si scrive per una persona che ha già ricevuto il link da un conoscente.",
        "en": "Add three tags to <head>: og:title, og:description and og:image with an absolute image URL around 1200x630. The title and description may differ from the search ones - here you are writing for someone who already got the link from a person they know.",
    },
    "a11y_seo_structured_data_title": {
        "uk": "На сторінці немає структурованих даних",
        "it": "Nella pagina non ci sono dati strutturati",
        "en": "No structured data on the page",
    },
    "a11y_seo_structured_data_found": {
        "uk": "Не знайдено ані JSON-LD (<script type=\"application/ld+json\">), ані мікророзмітки itemscope.",
        "it": "Non è stato trovato né JSON-LD (<script type=\"application/ld+json\">) né microdata itemscope.",
        "en": "Neither JSON-LD (<script type=\"application/ld+json\">) nor itemscope microdata was found.",
    },
    "a11y_seo_structured_data_why": {
        "uk": "Структуровані дані є єдиним способом сказати машині прямо, чим є ця сторінка: статтею, товаром, рецептом, організацією, подією. Без них і пошуковик, і асистент здогадуються з тексту. Саме з цієї розмітки збираються розширені результати з ціною, рейтингом чи датою, і саме її читають AI-відповіді, коли вирішують, кого процитувати.",
        "it": "I dati strutturati sono l'unico modo per dire a una macchina, in modo esplicito, che cosa è questa pagina: un articolo, un prodotto, una ricetta, un'organizzazione, un evento. Senza di essi sia il motore di ricerca sia l'assistente devono indovinare dal testo. Da questo markup nascono i risultati arricchiti con prezzo, valutazione o data, ed è quello che leggono le risposte AI quando decidono chi citare.",
        "en": "Structured data is the only way to tell a machine outright what this page is: an article, a product, a recipe, an organisation, an event. Without it both the search engine and the assistant have to guess from the prose. Rich results with a price, a rating or a date are built from this markup, and it is what AI answers read when deciding whom to cite.",
    },
    "a11y_seo_structured_data_fix": {
        "uk": "Додайте один блок JSON-LD із типом, що відповідає сторінці: Article для тексту, Product для товару, Organization для головної. Описуйте лише те, що справді є на сторінці - розмітка, яка обіцяє рейтинг, якого користувач не бачить, карається окремо.",
        "it": "Aggiungi un blocco JSON-LD con il tipo che corrisponde alla pagina: Article per un testo, Product per un prodotto, Organization per la home. Descrivi solo ciò che è davvero nella pagina: un markup che promette una valutazione invisibile all'utente viene sanzionato a parte.",
        "en": "Add one JSON-LD block with the type that matches the page: Article for a text, Product for an item, Organization for the home page. Describe only what is actually on the page - markup promising a rating the visitor cannot see is penalised in its own right.",
    },
    "a11y_seo_image_dimensions_title": {
        "uk": "Зображення без заданих розмірів",
        "it": "Immagine senza dimensioni dichiarate",
        "en": "Image with no declared dimensions",
    },
    "a11y_seo_image_dimensions_found": {
        "uk": "У <img src=\"{src}\"> немає ані width і height, ані aspect-ratio у стилях.",
        "it": "In <img src=\"{src}\"> mancano sia width e height sia aspect-ratio negli stili.",
        "en": "The <img src=\"{src}\"> has neither width and height nor an aspect-ratio in its styles.",
    },
    "a11y_seo_image_dimensions_why": {
        "uk": "Поки картинка не завантажилась, браузер не знає, скільки місця їй лишити, тому не лишає нічого. Коли вона приходить, увесь текст під нею стрибає вниз. Людина в цей момент уже читає або тягнеться до кнопки, і натискає не туди. Це найпоширеніша причина поганого показника стабільності макета.",
        "it": "Finché l'immagine non è caricata il browser non sa quanto spazio riservarle, quindi non ne riserva affatto. Quando arriva, tutto il testo sotto salta verso il basso. In quel momento la persona sta già leggendo o sta per premere un pulsante, e finisce per premere altrove. È la causa più comune di un cattivo punteggio di stabilità del layout.",
        "en": "Until the image loads the browser does not know how much room to leave for it, so it leaves none. When it arrives, everything below jumps down. By then the person is already reading, or reaching for a button, and taps the wrong thing. This is the most common cause of a poor layout-stability score.",
    },
    "a11y_seo_image_dimensions_fix": {
        "uk": "Вкажіть справжні пікселі оригіналу в width і height: <img src=\"…\" width=\"800\" height=\"600\">. CSS далі може розтягувати картинку як завгодно - атрибути потрібні лише для співвідношення сторін, за яким браузер резервує місце заздалегідь.",
        "it": "Indica i pixel reali dell'originale in width e height: <img src=\"…\" width=\"800\" height=\"600\">. Il CSS può poi ridimensionare l'immagine come vuoi: gli attributi servono solo per il rapporto d'aspetto con cui il browser riserva lo spazio in anticipo.",
        "en": "Give the real pixel size of the original in width and height: <img src=\"…\" width=\"800\" height=\"600\">. CSS can still scale the image however you like - the attributes only supply the aspect ratio the browser uses to reserve the space up front.",
    },
    "a11y_seo_empty_link_title": {
        "uk": "Посилання без тексту",
        "it": "Link senza testo",
        "en": "Link with no text",
    },
    "a11y_seo_empty_link_found": {
        "uk": "Посилання на {href} не містить ані тексту, ані зображення, ані aria-label.",
        "it": "Il link a {href} non contiene né testo, né immagine, né aria-label.",
        "en": "The link to {href} contains no text, no image and no aria-label.",
    },
    "a11y_seo_empty_link_why": {
        "uk": "Текст посилання є єдиним поясненням того, куди воно веде - і для людини, і для пошукової системи, яка з нього розуміє, про що цільова сторінка. Порожнє посилання не передає нічого нікуди, а для того, хто йде по сторінці клавіатурою, воно ще й стає зупинкою без назви: фокус десь є, а що це - невідомо.",
        "it": "Il testo del link è l'unica spiegazione di dove porta, sia per la persona sia per il motore di ricerca, che da lì capisce di cosa parla la pagina di destinazione. Un link vuoto non trasmette nulla a nessuno, e per chi naviga da tastiera diventa una fermata senza nome: il focus è da qualche parte, ma su che cosa non si sa.",
        "en": "Link text is the only account of where the link goes - both for a person and for a search engine, which reads it to understand what the target page is about. An empty link conveys nothing to anyone, and for someone moving through the page by keyboard it becomes a stop with no name: the focus is somewhere, but on what is anybody's guess.",
    },
    "a11y_seo_empty_link_fix": {
        "uk": "Дайте посиланню видимий текст, що описує ціль. Якщо за задумом це іконка без підпису, додайте aria-label=\"…\" з тією ж назвою, яку сказали б уголос: aria-label=\"Ми у Facebook\", а не \"посилання\".",
        "it": "Dai al link un testo visibile che descriva la destinazione. Se per scelta è un'icona senza etichetta, aggiungi aria-label=\"…\" con lo stesso nome che diresti a voce: aria-label=\"Siamo su Facebook\", non \"link\".",
        "en": "Give the link visible text that describes the destination. If it is deliberately an unlabelled icon, add aria-label=\"…\" with the same name you would say out loud: aria-label=\"We are on Facebook\", not \"link\".",
    },
    # -------------------------------------------------------- Performance
    "a11y_perf_render_blocking_title": {
        "uk": "Забагато ресурсів блокують перший показ сторінки",
        "it": "Troppe risorse bloccano la prima visualizzazione",
        "en": "Too many resources block the first paint",
    },
    "a11y_perf_render_blocking_found": {
        "uk": "У <head> знайдено {count} {files_noun} при розумній межі {budget}.",
        "it": "Nel <head> ci sono {count} {files_noun}, il limite ragionevole è {budget}.",
        "en": "Found {count} {files_noun} in <head> against a sensible budget of {budget}.",
    },
    "a11y_perf_render_blocking_why": {
        "uk": "Скрипт без async чи defer і звичайний файл стилів зупиняють розбір документа: браузер не малює жодного пікселя, доки не завантажить і не виконає кожен з них. Тобто час до першого слова на екрані дорівнює сумі найповільніших запитів, і на мобільному зв'язку це секунди білого екрана при цілком робочому сайті.",
        "it": "Uno script senza async o defer e un foglio di stile normale fermano l'analisi del documento: il browser non disegna un solo pixel finché non ha scaricato ed eseguito ognuno di essi. Il tempo fino alla prima parola sullo schermo è quindi la somma delle richieste più lente, e su rete mobile sono secondi di schermo bianco con un sito perfettamente funzionante.",
        "en": "A script without async or defer, and an ordinary stylesheet, stop the parser: the browser paints no pixel until it has fetched and run every one of them. Time to the first word on screen is therefore the sum of the slowest requests, and on a mobile connection that is seconds of white screen in front of a perfectly working site.",
    },
    "a11y_perf_render_blocking_fix": {
        "uk": "Скриптам у <head> додайте defer, а тим, що не потрібні для першого екрана - async. Стилі розділіть: критичні для першого екрана вставте інлайново, решту підключіть з media=\"print\" і перемкніть на all після завантаження. Мета - лишити в <head> не більше {budget} блокувальних запитів.",
        "it": "Aggiungi defer agli script nel <head> e async a quelli non necessari alla prima schermata. Dividi gli stili: quelli critici per la prima schermata inseriscili inline, il resto caricalo con media=\"print\" e passa ad all dopo il caricamento. L'obiettivo è lasciare nel <head> non più di {budget} richieste bloccanti.",
        "en": "Give scripts in <head> a defer, and async to those not needed for the first screen. Split the styles: inline what the first screen needs and load the rest with media=\"print\", switching it to all once it has arrived. The target is no more than {budget} blocking requests in <head>.",
    },
    "a11y_perf_third_party_sync_title": {
        "uk": "Сторонній скрипт завантажується синхронно",
        "it": "Script di terze parti caricato in modo sincrono",
        "en": "Third-party script loaded synchronously",
    },
    "a11y_perf_third_party_sync_found": {
        "uk": "Скрипт з чужого домену {host} підключений без async і без defer: {src}.",
        "it": "Uno script dal dominio esterno {host} è incluso senza async e senza defer: {src}.",
        "en": "A script from the external host {host} is included with neither async nor defer: {src}.",
    },
    "a11y_perf_third_party_sync_why": {
        "uk": "Такий тег віддає чужому серверу право зупинити показ вашої сторінки. Якщо аналітика, чат підтримки чи рекламна мережа відповідатиме повільно або не відповість зовсім, відвідувач дивитиметься на порожнє вікно, і жодна оптимізація власного коду цього не змінить. Це єдина точка відмови, яка не належить команді сайту.",
        "it": "Un tag così concede a un server esterno il diritto di fermare la visualizzazione della tua pagina. Se l'analytics, la chat di supporto o il network pubblicitario risponde lentamente o non risponde affatto, il visitatore guarda una finestra vuota, e nessuna ottimizzazione del proprio codice lo cambia. È un punto di guasto unico che non appartiene al team del sito.",
        "en": "A tag like this hands an outside server the power to stop your page from rendering. If the analytics, the support chat or the ad network answers slowly - or not at all - the visitor stares at an empty window, and no amount of optimising your own code changes that. It is a single point of failure that does not belong to the site's team.",
    },
    "a11y_perf_third_party_sync_fix": {
        "uk": "Додайте defer, якщо порядок виконання важливий, або async, якщо ні. Скрипти, потрібні лише після взаємодії (чат, віджет відгуків), підключайте за подією, а не одразу при завантаженні.",
        "it": "Aggiungi defer se l'ordine di esecuzione conta, oppure async se non conta. Gli script necessari solo dopo un'interazione (chat, widget di recensioni) caricali su evento, non subito al caricamento.",
        "en": "Add defer if execution order matters, async if it does not. Scripts only needed after an interaction (a chat widget, a review embed) should be loaded on that event rather than at page load.",
    },
    "a11y_perf_large_inline_title": {
        "uk": "Завеликий інлайновий блок коду або стилів",
        "it": "Blocco inline di codice o stili troppo grande",
        "en": "Oversized inline code or style block",
    },
    "a11y_perf_large_inline_found": {
        "uk": "Блок <{element}> містить {bytes} байтів при межі {budget}.",
        "it": "Il blocco <{element}> contiene {bytes} byte, il limite è {budget}.",
        "en": "The <{element}> block holds {bytes} bytes against a budget of {budget}.",
    },
    "a11y_perf_large_inline_why": {
        "uk": "Інлайновий блок економить один запит, і саме тому в нього поступово переїжджає все. Але він приходить у кожній відповіді сервера, ніколи не кешується між сторінками і розбирається в головному потоці до першого показу. Після певного розміру економія на запиті стає меншою за втрату на розборі, а на повторних відвідинах цей код завантажується знову і знову.",
        "it": "Un blocco inline risparmia una richiesta, ed è proprio per questo che ci finisce dentro tutto, poco a poco. Ma arriva in ogni risposta del server, non viene mai messo in cache tra le pagine e viene analizzato nel thread principale prima della prima visualizzazione. Oltre una certa dimensione il risparmio sulla richiesta diventa minore della perdita nell'analisi, e a ogni nuova visita quel codice si scarica di nuovo.",
        "en": "An inline block saves one request, which is exactly why everything gradually migrates into it. But it ships in every server response, is never cached across pages, and is parsed on the main thread before the first paint. Past a certain size the saved request costs less than the parsing, and on every repeat visit that code is downloaded all over again.",
    },
    "a11y_perf_large_inline_fix": {
        "uk": "Винесіть блок в окремий файл і підключіть його посиланням - тоді він кешується і не приходить з кожною сторінкою. Інлайновим лишайте тільки те, що справді потрібне для першого екрана, у межах {budget} байтів.",
        "it": "Sposta il blocco in un file separato e collegalo: così viene messo in cache e non arriva con ogni pagina. Lascia inline solo ciò che serve davvero alla prima schermata, entro {budget} byte.",
        "en": "Move the block into its own file and link to it - then it is cached and does not travel with every page. Keep inline only what the first screen genuinely needs, within {budget} bytes.",
    },
    "a11y_perf_image_loading_title": {
        "uk": "Зображення нижче першого екрана без відкладеного завантаження",
        "it": "Immagine sotto la prima schermata senza caricamento differito",
        "en": "Below-the-fold image without lazy loading",
    },
    "a11y_perf_image_loading_found": {
        "uk": "У <img src=\"{src}\"> немає loading=\"lazy\", хоча зображення стоїть далеко від початку сторінки.",
        "it": "In <img src=\"{src}\"> manca loading=\"lazy\", pur trovandosi lontano dall'inizio della pagina.",
        "en": "The <img src=\"{src}\"> has no loading=\"lazy\", although it sits well below the start of the page.",
    },
    "a11y_perf_image_loading_why": {
        "uk": "За замовчуванням браузер тягне всі зображення одразу, разом із тими, до яких відвідувач ніколи не догортає. Вони змагаються за канал із тим, що видно зараз, тому головна картинка на екрані з'являється пізніше. На мобільному тарифі це ще й прямі витрати людини за трафік, який вона не побачила.",
        "it": "Per impostazione predefinita il browser scarica subito tutte le immagini, comprese quelle fino a cui il visitatore non arriverà mai. Competono per la banda con ciò che è visibile adesso, quindi l'immagine principale compare più tardi. Su una tariffa mobile è anche un costo diretto per traffico che la persona non ha visto.",
        "en": "By default the browser fetches every image at once, including the ones the visitor never scrolls to. They compete for bandwidth with what is on screen now, so the main image appears later. On a metered mobile plan it is also money spent on data the person never saw.",
    },
    "a11y_perf_image_loading_fix": {
        "uk": "Додайте loading=\"lazy\" до зображень нижче першого екрана. Першим 2-3 картинкам його не ставте: там відкладення лише сповільнює найбільший видимий елемент, тобто робить гірше саме там, де вимірюється швидкість.",
        "it": "Aggiungi loading=\"lazy\" alle immagini sotto la prima schermata. Non metterlo alle prime 2-3: lì il differimento rallenta soltanto l'elemento visibile più grande, cioè peggiora proprio dove la velocità viene misurata.",
        "en": "Add loading=\"lazy\" to images below the first screen. Do not put it on the first two or three: there, deferring only slows the largest visible element - it makes things worse exactly where speed is measured.",
    },
    "a11y_perf_font_display_title": {
        "uk": "Шрифт без стратегії показу тексту",
        "it": "Font senza strategia di visualizzazione del testo",
        "en": "Font with no text-display strategy",
    },
    "a11y_perf_font_display_found": {
        "uk": "Шрифт підключено без font-display і без параметра display: {href}.",
        "it": "Font caricato senza font-display e senza il parametro display: {href}.",
        "en": "The font is loaded with no font-display and no display parameter: {href}.",
    },
    "a11y_perf_font_display_why": {
        "uk": "Без вказаної стратегії браузер до трьох секунд ховає текст, доки чекає на шрифт. Сторінка в цей час технічно завантажена, але слів на ній немає - людина дивиться на порожні блоки і часто йде, вирішивши, що сайт зламаний. Ховати вміст заради накреслення шрифту майже ніколи не є правильним обміном.",
        "it": "Senza una strategia dichiarata il browser nasconde il testo fino a tre secondi mentre aspetta il font. In quel momento la pagina è tecnicamente caricata, ma non ci sono parole: la persona guarda blocchi vuoti e spesso se ne va convinta che il sito sia rotto. Nascondere il contenuto per il disegno del carattere non è quasi mai uno scambio corretto.",
        "en": "With no strategy declared the browser hides the text for up to three seconds while it waits for the font. The page is technically loaded, but has no words on it - the visitor looks at empty blocks and often leaves, concluding the site is broken. Hiding content for the sake of a typeface is almost never the right trade.",
    },
    "a11y_perf_font_display_fix": {
        "uk": "Додайте font-display: swap у @font-face, а до посилання на Google Fonts - параметр &display=swap. Текст одразу покажеться запасним шрифтом і перемалюється, коли прийде основний. Для дуже помітної різниці накреслень підійде optional: тоді шрифт застосується лише з наступного візиту.",
        "it": "Aggiungi font-display: swap in @font-face e il parametro &display=swap al link di Google Fonts. Il testo compare subito con il font di riserva e viene ridisegnato quando arriva quello principale. Se la differenza tra i caratteri è molto marcata, usa optional: il font si applicherà dalla visita successiva.",
        "en": "Add font-display: swap to @font-face, and &display=swap to the Google Fonts URL. The text shows immediately in the fallback face and is repainted when the real one arrives. Where the two faces differ sharply, optional works better: the font then applies from the next visit onwards.",
    },
    "a11y_perf_preconnect_title": {
        "uk": "Немає підказок на з'єднання зі сторонніми доменами",
        "it": "Mancano suggerimenti di connessione ai domini esterni",
        "en": "No connection hints for third-party hosts",
    },
    "a11y_perf_preconnect_found": {
        "uk": "Сторінка звертається до {count} {domains_noun} без preconnect чи dns-prefetch: {hosts}.",
        "it": "La pagina contatta {count} {domains_noun} senza preconnect o dns-prefetch: {hosts}.",
        "en": "The page reaches {count} {domains_noun} with no preconnect or dns-prefetch: {hosts}.",
    },
    "a11y_perf_preconnect_why": {
        "uk": "Перш ніж завантажити перший байт з чужого домену, браузер має знайти адресу в DNS, встановити з'єднання і домовитись про шифрування. Це три послідовні подорожі мережею, і на мобільному зв'язку разом вони дають кількасот мілісекунд ще до початку завантаження - і так для кожного домену окремо.",
        "it": "Prima di scaricare il primo byte da un dominio esterno, il browser deve risolvere l'indirizzo via DNS, stabilire la connessione e negoziare la cifratura. Sono tre viaggi di rete consecutivi e, su rete mobile, insieme costano centinaia di millisecondi prima ancora che inizi il download, e questo per ogni dominio separatamente.",
        "en": "Before the first byte arrives from an external host, the browser has to resolve the address over DNS, open a connection and negotiate encryption. That is three consecutive round trips, and on a mobile connection they add up to several hundred milliseconds before the download even starts - separately for every host.",
    },
    "a11y_perf_preconnect_fix": {
        "uk": "Додайте у <head> <link rel=\"preconnect\" href=\"https://домен\"> для двох-трьох найважливіших чужих доменів (шрифти, головний CDN). Робити це для всіх підряд не варто: кожне зайве з'єднання теж займає ресурси, тому решті достатньо dns-prefetch.",
        "it": "Aggiungi nel <head> <link rel=\"preconnect\" href=\"https://dominio\"> per i due o tre domini esterni più importanti (font, CDN principale). Non farlo per tutti: ogni connessione superflua consuma risorse, per gli altri basta dns-prefetch.",
        "en": "Add <link rel=\"preconnect\" href=\"https://host\"> to <head> for the two or three most important external hosts (fonts, the main CDN). Do not do it for all of them: every extra connection costs resources too, so dns-prefetch is enough for the rest.",
    },
    "a11y_perf_layout_shift_title": {
        "uk": "Елемент без зарезервованого місця зсуває макет",
        "it": "Elemento senza spazio riservato che sposta il layout",
        "en": "Element with no reserved space shifts the layout",
    },
    "a11y_perf_layout_shift_found": {
        "uk": "Елемент <{element}> не має ані розмірів, ані aspect-ratio, тому місце під нього не резервується.",
        "it": "L'elemento <{element}> non ha dimensioni né aspect-ratio, quindi non viene riservato spazio.",
        "en": "The <{element}> has neither dimensions nor an aspect-ratio, so no space is reserved for it.",
    },
    "a11y_perf_layout_shift_why": {
        "uk": "Елемент, розмір якого стає відомим лише після завантаження, з'являється у вже прочитаному місці і зсуває все нижче. Найдорожчий наслідок - не естетичний: людина натискає кнопку в момент, коли та поїхала вниз, і потрапляє в іншу. Для реклами й вбудованих плеєрів це трапляється найчастіше, бо їхня висота приходить ззовні.",
        "it": "Un elemento la cui dimensione si conosce solo dopo il caricamento compare in un punto già letto e sposta tutto ciò che sta sotto. La conseguenza più costosa non è estetica: la persona preme un pulsante nell'istante in cui questo scende e ne colpisce un altro. Con la pubblicità e i player incorporati succede più spesso, perché la loro altezza arriva dall'esterno.",
        "en": "An element whose size is only known after it loads appears in a place already being read and pushes everything below it down. The costly consequence is not aesthetic: someone taps a button at the moment it moves and hits a different one. Ads and embedded players cause this most often, because their height comes from outside.",
    },
    "a11y_perf_layout_shift_fix": {
        "uk": "Задайте width і height, або зарезервуйте місце через aspect-ratio у CSS чи контейнер фіксованої висоти. Для вбудованих плеєрів і банерів найнадійніше - обгортка з відомим співвідношенням сторін, бо самі вони своїх розмірів наперед не повідомляють.",
        "it": "Imposta width e height, oppure riserva lo spazio con aspect-ratio nel CSS o con un contenitore di altezza fissa. Per player incorporati e banner la soluzione più solida è un wrapper con rapporto d'aspetto noto, dato che da soli non dichiarano le proprie dimensioni.",
        "en": "Set width and height, or reserve the space with an aspect-ratio in CSS or a container of fixed height. For embedded players and banners the most reliable answer is a wrapper with a known aspect ratio, since they do not announce their own size in advance.",
    },
    "a11y_perf_largest_contentful_paint_title": {
        "uk": "Найбільший видимий елемент з'являється повільно",
        "it": "L'elemento visibile più grande appare lentamente",
        "en": "The largest visible element appears slowly",
    },
    "a11y_perf_largest_contentful_paint_found": {
        "uk": "Браузер виміряв LCP {value} мс при цілі не більше {budget} мс.",
        "it": "Il browser ha misurato LCP {value} ms, con obiettivo non oltre {budget} ms.",
        "en": "The browser measured LCP at {value} ms, against a target of at most {budget} ms.",
    },
    "a11y_perf_largest_contentful_paint_why": {
        "uk": "LCP показує, коли для людини з'явився головний вміст першого екрана. Повільне значення означає, що сторінка може вже реагувати технічно, але ключовий текст або зображення ще не видно.",
        "it": "LCP indica quando compare per la persona il contenuto principale della prima schermata. Un valore lento significa che la pagina può già reagire tecnicamente, ma il testo o l'immagine principali non sono ancora visibili.",
        "en": "LCP shows when the main above-the-fold content became visible to a person. A slow value means the page may technically respond while its key text or image is still missing.",
    },
    "a11y_perf_largest_contentful_paint_fix": {
        "uk": "Визначте елемент LCP у профілюванні браузера, оптимізуйте його ресурс і шлях до нього: відповідь сервера, зображення, шрифт, CSS або блокувальний JavaScript. Перевірте повторно на реальному маршруті.",
        "it": "Individua l'elemento LCP nel profiling del browser e ottimizza la sua risorsa e il percorso: risposta del server, immagine, font, CSS o JavaScript bloccante. Verifica di nuovo sul percorso reale.",
        "en": "Identify the LCP element in browser profiling and optimise its resource and path: server response, image, font, CSS or blocking JavaScript. Verify again on the real route.",
    },
    "a11y_perf_first_paint_title": {
        "uk": "Перше відображення вмісту затримується",
        "it": "Il primo contenuto appare tardi",
        "en": "The first content appears late",
    },
    "a11y_perf_first_paint_found": {
        "uk": "Браузер виміряв FCP {value} мс при цілі не більше {budget} мс.",
        "it": "Il browser ha misurato FCP a {value} ms, con obiettivo massimo di {budget} ms.",
        "en": "The browser measured FCP at {value} ms against a target of {budget} ms.",
    },
    "a11y_perf_first_paint_why": {
        "uk": "FCP показує, коли браузер уперше намалював текст, зображення чи інший вміст. Пізній перший кадр залишає сторінку порожньою довше, ніж потрібно.",
        "it": "FCP indica quando il browser ha mostrato per la prima volta testo, immagini o altro contenuto. Un primo fotogramma tardivo lascia la pagina vuota più a lungo del necessario.",
        "en": "FCP records when the browser first painted text, an image or other content. A late first paint leaves the page blank longer than it needs to be.",
    },
    "a11y_perf_first_paint_fix": {
        "uk": "Скоротіть час відповіді сервера, приберіть ресурси, що блокують перше відображення, і залиште критичні стилі невеликими. Перевірте мережевий профіль після змін.",
        "it": "Riduci il tempo di risposta del server, rimuovi le risorse che bloccano il primo rendering e mantieni piccoli gli stili critici. Ricontrolla il profilo di rete dopo le modifiche.",
        "en": "Reduce server response time, remove resources that block the first paint and keep critical styles small. Check the network profile again after the change.",
    },
    "a11y_perf_load_time_title": {
        "uk": "Сторінка завантажується повільно",
        "it": "La pagina si carica lentamente",
        "en": "The page takes too long to load",
    },
    "a11y_perf_load_time_found": {
        "uk": "Браузер завершив завантаження за {value} мс при бюджеті {budget} мс.",
        "it": "Il browser ha completato il caricamento in {value} ms, con budget di {budget} ms.",
        "en": "The browser finished loading in {value} ms against a budget of {budget} ms.",
    },
    "a11y_perf_load_time_why": {
        "uk": "Це час до завершення завантаження сторінки та її ресурсів у браузері. Довге очікування затримує доступ до вмісту й часто вказує на важкі ресурси або зайві мережеві запити.",
        "it": "È il tempo necessario al browser per completare il caricamento della pagina e delle sue risorse. Un'attesa lunga ritarda l'accesso ai contenuti e spesso segnala risorse pesanti o troppe richieste di rete.",
        "en": "This is how long the browser took to finish loading the page and its resources. A long wait delays access to the content and often points to heavy resources or too many network requests.",
    },
    "a11y_perf_load_time_fix": {
        "uk": "Перегляньте мережевий профіль: зменште зображення й скрипти, приберіть непотрібні запити та налаштуйте кешування. Порівнюйте той самий маршрут у тих самих умовах.",
        "it": "Esamina il profilo di rete: riduci immagini e script, rimuovi richieste inutili e configura la cache. Confronta lo stesso percorso nelle stesse condizioni.",
        "en": "Inspect the network profile: reduce images and scripts, remove unnecessary requests and configure caching. Compare the same route under the same conditions.",
    },
    "a11y_perf_page_weight_title": {
        "uk": "Сторінка передає забагато даних",
        "it": "La pagina trasferisce troppi dati",
        "en": "The page transfers too much data",
    },
    "a11y_perf_page_weight_found": {
        "uk": "Передано {value} байтів при бюджеті {budget} байтів.",
        "it": "Sono stati trasferiti {value} byte, con budget di {budget} byte.",
        "en": "The page transferred {value} bytes against a budget of {budget} bytes.",
    },
    "a11y_perf_page_weight_why": {
        "uk": "Великий обсяг даних довше завантажується в повільній або лімітованій мережі. Часто основну вагу створюють зображення, відео, шрифти й сторонні скрипти.",
        "it": "Una quantità elevata di dati richiede più tempo su reti lente o a consumo. Spesso il peso maggiore viene da immagini, video, font e script di terze parti.",
        "en": "A large transfer takes longer on slow or metered connections. Images, video, fonts and third-party scripts often account for most of the weight.",
    },
    "a11y_perf_page_weight_fix": {
        "uk": "Стисніть і задайте потрібні розміри зображень, відкладайте завантаження вмісту поза першим екраном і видаліть непотрібні бібліотеки. Перевірте фактичні байти у мережевому профілі.",
        "it": "Comprimi le immagini e specifica le dimensioni necessarie, rimanda il contenuto fuori dal primo schermo e rimuovi le librerie inutili. Verifica i byte effettivi nel profilo di rete.",
        "en": "Compress images and give them the needed dimensions, defer content below the first screen and remove unused libraries. Check the actual bytes in the network profile.",
    },
    "a11y_perf_request_count_title": {
        "uk": "Сторінка робить забагато мережевих запитів",
        "it": "La pagina effettua troppe richieste di rete",
        "en": "The page makes too many network requests",
    },
    "a11y_perf_request_count_found": {
        "uk": "Браузер виконав {value} запитів при бюджеті {budget}.",
        "it": "Il browser ha eseguito {value} richieste, con budget di {budget}.",
        "en": "The browser made {value} requests against a budget of {budget}.",
    },
    "a11y_perf_request_count_why": {
        "uk": "Кожен запит додає очікування та витрати на з'єднання, особливо на мобільній мережі. Велика кількість дрібних файлів може затримати готовність сторінки навіть за невеликого загального обсягу.",
        "it": "Ogni richiesta aggiunge attesa e costi di connessione, soprattutto sulle reti mobili. Molti file piccoli possono ritardare la pagina anche quando il volume totale è contenuto.",
        "en": "Each request adds waiting and connection overhead, especially on mobile networks. Many small files can delay the page even when the total transfer is modest.",
    },
    "a11y_perf_request_count_fix": {
        "uk": "Об'єднайте або приберіть зайві ресурси, відкладіть некритичні скрипти й перевірте, чи не завантажуються дублікати. Не об'єднуйте файли ціною кешування без вимірювання.",
        "it": "Unisci o rimuovi le risorse superflue, rimanda gli script non critici e controlla che non vengano caricati duplicati. Non unire file a scapito della cache senza misurare il risultato.",
        "en": "Combine or remove unnecessary resources, defer non-critical scripts and check for duplicate downloads. Do not sacrifice caching by combining files without measuring the result.",
    },
    "a11y_perf_dom_size_title": {
        "uk": "У сторінці забагато елементів DOM",
        "it": "La pagina contiene troppi elementi DOM",
        "en": "The page has too many DOM elements",
    },
    "a11y_perf_dom_size_found": {
        "uk": "У DOM знайдено {value} вузлів при бюджеті {budget}.",
        "it": "Nel DOM sono stati rilevati {value} nodi, con budget di {budget}.",
        "en": "The DOM contains {value} nodes against a budget of {budget}.",
    },
    "a11y_perf_dom_size_why": {
        "uk": "Велике дерево сторінки потребує більше пам'яті та роботи під час стилізації, розкладки й оновлення. Це може сповільнити малювання та взаємодію на слабших пристроях.",
        "it": "Un albero della pagina troppo grande richiede più memoria e lavoro per stili, layout e aggiornamenti. Può rallentare il rendering e l'interazione sui dispositivi meno potenti.",
        "en": "A large page tree needs more memory and work for styling, layout and updates. It can slow rendering and interaction on less powerful devices.",
    },
    "a11y_perf_dom_size_fix": {
        "uk": "Зменште кількість повторюваних обгорток і не створюйте невидимі елементи наперед. Для довгих списків використайте віртуалізацію та відображайте лише видиму частину.",
        "it": "Riduci i contenitori ripetuti ed evita di creare in anticipo elementi invisibili. Per gli elenchi lunghi usa la virtualizzazione e mostra solo la parte visibile.",
        "en": "Reduce repeated wrappers and avoid creating invisible elements in advance. Virtualise long lists so only the visible portion is rendered.",
    },
    "a11y_perf_layout_shift_browser_title": {
        "uk": "Браузер зафіксував нестабільність макета",
        "it": "Il browser ha rilevato instabilità del layout",
        "en": "The browser recorded layout instability",
    },
    "a11y_perf_layout_shift_browser_found": {
        "uk": "Браузер виміряв CLS {value} при цілі не більше {budget}.",
        "it": "Il browser ha misurato CLS {value}, con obiettivo non oltre {budget}.",
        "en": "The browser measured CLS at {value}, against a target of at most {budget}.",
    },
    "a11y_perf_layout_shift_browser_why": {
        "uk": "CLS фіксує зсуви, які сталися під час завантаження, тому це сильніший сигнал за перевірку окремого HTML-елемента. Зсув може змусити людину натиснути не на ту дію або втратити місце читання.",
        "it": "CLS registra gli spostamenti avvenuti durante il caricamento, quindi è un segnale più forte dell'ispezione di un singolo elemento HTML. Uno spostamento può far premere l'azione sbagliata o far perdere il punto di lettura.",
        "en": "CLS records shifts that happened while the page loaded, so it is stronger evidence than inspecting a single HTML element. A shift can make someone activate the wrong control or lose their reading position.",
    },
    "a11y_perf_layout_shift_browser_fix": {
        "uk": "За профілем завантаження знайдіть ресурс або блок, що зміщується, і зарезервуйте для нього місце. Найчастіше це зображення, реклама, вбудований віджет або шрифт, що міняє розмір тексту після появи.",
        "it": "Nel profilo di caricamento trova la risorsa o il blocco che si sposta e riservagli spazio. Di solito è un'immagine, pubblicità, un widget incorporato o un font che cambia la dimensione del testo quando arriva.",
        "en": "Use the loading profile to find the resource or block that shifts and reserve its space. It is often an image, ad, embedded widget or font that changes text size after it arrives.",
    },
    "a11y_perf_interaction_to_next_paint_title": {
        "uk": "Сторінка повільно відповідає на введення",
        "it": "La pagina risponde lentamente all'input",
        "en": "The page responds slowly to input",
    },
    "a11y_perf_interaction_to_next_paint_found": {
        "uk": "У цьому лабораторному сценарії INP становить {value} мс при цілі не більше {budget} мс.",
        "it": "In questo scenario di laboratorio INP è {value} ms, con obiettivo non oltre {budget} ms.",
        "en": "INP in this lab scenario was {value} ms, against a target of at most {budget} ms.",
    },
    "a11y_perf_interaction_to_next_paint_why": {
        "uk": "INP вимірює затримку між введенням і наступним відображенням. Цей обмежений сценарій не описує всі взаємодії реальних користувачів.",
        "it": "INP misura il ritardo tra l'input e il rendering successivo. Questo scenario limitato non descrive tutte le interazioni degli utenti reali.",
        "en": "INP measures the delay from input to the next paint. This bounded scenario does not describe all real-user interactions.",
    },
    "a11y_perf_interaction_to_next_paint_fix": {
        "uk": "За атрибуцією знайдіть повільну взаємодію, скоротіть синхронну роботу обробника та перевірте повторно з тим самим сценарієм.",
        "it": "Usa l'attribuzione per trovare l'interazione lenta, riduci il lavoro sincrono del gestore e ripeti lo stesso scenario.",
        "en": "Use the attribution to find the slow interaction, reduce synchronous handler work and repeat the same scenario.",
    },
    "a11y_perf_long_tasks_title": {
        "uk": "Головний потік надто довго зайнятий JavaScript",
        "it": "Il thread principale resta occupato troppo a lungo dal JavaScript",
        "en": "JavaScript keeps the main thread busy for too long",
    },
    "a11y_perf_long_tasks_found": {
        "uk": "Браузер зафіксував {value} мс довгих задач при бюджеті {budget} мс.",
        "it": "Il browser ha registrato {value} ms di task lunghi, con budget di {budget} ms.",
        "en": "The browser recorded {value} ms of long tasks, against a {budget} ms budget.",
    },
    "a11y_perf_long_tasks_why": {
        "uk": "Поки головний потік зайнятий, браузер не може вчасно малювати сторінку або відповідати на введення. Це вимірювання блокування під час цього запуску, не підмінник Interaction to Next Paint.",
        "it": "Finché il thread principale è occupato, il browser non può disegnare la pagina o rispondere all'input in tempo. È una misura del blocco in questa esecuzione, non un sostituto di Interaction to Next Paint.",
        "en": "While the main thread is busy, the browser cannot paint promptly or respond to input. This measures blocking in this run, not a substitute for Interaction to Next Paint.",
    },
    "a11y_perf_long_tasks_fix": {
        "uk": "Відкрийте профіль продуктивності, знайдіть найдовші завдання і розбийте або відкладіть їх. Особливо перевірте великі бандли, сторонні віджети та синхронну обробку даних на старті.",
        "it": "Apri il profilo prestazioni, trova i task più lunghi e suddividili o rimandali. Controlla soprattutto bundle grandi, widget esterni ed elaborazione sincrona dei dati all'avvio.",
        "en": "Open a performance profile, find the longest tasks and split or defer them. Check large bundles, third-party widgets and synchronous data processing at startup first.",
    },
    # ------------------------------------------------------ Best practices
    "a11y_sec_password_in_get_form_title": {
        "uk": 'Пароль піде в адресний рядок',
        "it": 'La password finirà nella barra degli indirizzi',
        "en": 'The password will go into the address bar',
    },
    "a11y_sec_password_in_get_form_found": {
        "uk": 'Форма з полем пароля надсилається методом {method}.',
        "it": 'Il form con un campo password invia con il metodo {method}.',
        "en": 'The form with a password field submits by {method}.',
    },
    "a11y_sec_password_in_get_form_why": {
        "uk": 'Усе з форми потрапляє в рядок запиту: адресний рядок, історію браузера, referrer до наступного сайту, журнал доступу сервера і кожен проксі між ними. HTTPS тут не рятує: адреса зашифрована в дорозі й записана відкрито на обох кінцях.',
        "it": "Tutto il form finisce nella query string: barra degli indirizzi, cronologia, referrer verso il sito successivo, log di accesso del server e ogni proxy nel mezzo. HTTPS non aiuta: l'URL è cifrato in transito e scritto in chiaro a entrambi i capi.",
        "en": "Everything in the form goes into the query string: the address bar, the browser history, the referrer sent to the next site, the server's access log and every proxy in between. HTTPS does not help - the URL is encrypted in transit and written in the clear at both ends.",
    },
    "a11y_sec_password_in_get_form_fix": {
        "uk": 'Поставте method="post". Відсутній method означає GET, тож його треба вказати явно.',
        "it": 'Imposta method="post". Un method assente significa GET, quindi va dichiarato esplicitamente.',
        "en": 'Set method="post". An absent method means GET, so it has to be stated.',
    },
    "a11y_sec_formaction_insecure_title": {
        "uk": 'Кнопка перекриває дію форми на http',
        "it": "Il pulsante sovrascrive l'azione del form con http",
        "en": "A button overrides the form's action with http",
    },
    "a11y_sec_formaction_insecure_found": {
        "uk": 'formaction="{formaction}" надсилає через http.',
        "it": 'formaction="{formaction}" invia via http.',
        "en": 'formaction="{formaction}" posts over http.',
    },
    "a11y_sec_formaction_insecure_why": {
        "uk": 'formaction на кнопці перемагає власний action форми, тож форма, яка виглядає безпечною, все одно надсилає у відкритому вигляді через одну зі своїх кнопок. Читання самої форми цього не бачить.',
        "it": "formaction sul pulsante prevale sull'action del form, quindi un form che sembra sicuro invia comunque in chiaro attraverso uno dei suoi pulsanti. Leggere solo il form non lo mostra.",
        "en": "formaction on a button wins over the form's own action, so a form that looks safe can still post in the clear through one of its buttons. Reading the form alone misses it.",
    },
    "a11y_sec_formaction_insecure_fix": {
        "uk": 'Змініть formaction на https або приберіть його, щоб кнопка користувалась action форми.',
        "it": "Cambia formaction in https oppure rimuovilo, così il pulsante usa l'action del form.",
        "en": "Change formaction to https, or remove it so the button uses the form's action.",
    },
    "a11y_sec_credentials_in_url_title": {
        "uk": 'Логін і пароль записані в адресу',
        "it": "Credenziali scritte nell'URL",
        "en": 'A credential written into a URL',
    },
    "a11y_sec_credentials_in_url_found": {
        "uk": 'Атрибут {attribute} містить логін і пароль для {host}.',
        "it": "L'attributo {attribute} contiene credenziali per {host}.",
        "en": 'The {attribute} attribute carries a credential for {host}.',
    },
    "a11y_sec_credentials_in_url_why": {
        "uk": 'Форма https://user:pass@host/ кладе облікові дані в розмітку, в історію браузера і в referrer. Браузери роками зрізають цю форму, тож зазвичай це витік, який до того ж уже не працює.',
        "it": 'La forma https://user:pass@host/ mette le credenziali nel markup, nella cronologia e nel referrer. I browser rimuovono questa forma da anni, quindi di solito è una fuga che per giunta non funziona più.',
        "en": "The https://user:pass@host/ form puts the credential in the markup, in the browser's history and in the referrer. Browsers have been stripping this form for years, so it is usually a leak that no longer even works.",
    },
    "a11y_sec_credentials_in_url_fix": {
        "uk": 'Приберіть облікові дані з адреси й відкличте їх: усе, що потрапило в розмітку, вважайте опублікованим.',
        "it": "Togli le credenziali dall'URL e revocale: tutto ciò che è finito nel markup va considerato pubblicato.",
        "en": 'Take the credential out of the URL and revoke it: anything that reached the markup should be treated as published.',
    },
    "a11y_sec_srcdoc_sandbox_title": {
        "uk": 'Вбудований документ без пісочниці',
        "it": 'Documento inline nel frame senza sandbox',
        "en": 'An inline framed document with no sandbox',
    },
    "a11y_sec_srcdoc_sandbox_found": {
        "uk": '<iframe srcdoc="..."> не має атрибута sandbox.',
        "it": 'L\'<iframe srcdoc="..."> non ha l\'attributo sandbox.',
        "en": 'The <iframe srcdoc="..."> carries no sandbox attribute.',
    },
    "a11y_sec_srcdoc_sandbox_why": {
        "uk": "Розмітка в srcdoc виконується у походженні сторінки, яка її вбудовує, якщо sandbox не скаже інакше. Тож усе, що туди підставляється - коментар, прев'ю, відрендерений фрагмент - виконується як власний скрипт першої сторони. Це той самий ризик, що й чужий кадр, тільки без походження, яке його видавало б.",
        "it": "Il markup in srcdoc viene eseguito nell'origine della pagina che lo incorpora, a meno che un sandbox non dica diversamente. Tutto ciò che vi viene interpolato - un commento, un'anteprima, un frammento renderizzato - gira come script di prima parte. È lo stesso rischio di un frame di terze parti, senza l'origine che lo renderebbe evidente.",
        "en": "srcdoc markup runs in the embedding page's origin unless a sandbox says otherwise, so anything interpolated into it - a comment, a preview, a rendered snippet - runs as first-party script. It is the same risk as a cross-origin frame with the origin removed, which makes it easier to miss.",
    },
    "a11y_sec_srcdoc_sandbox_fix": {
        "uk": 'Додайте sandbox і перелічіть лише потрібне. Для показу чужого вмісту порожній sandbox зазвичай і є правильною відповіддю.',
        "it": 'Aggiungi sandbox elencando solo il necessario. Per mostrare contenuto altrui, un sandbox vuoto è di solito la risposta giusta.',
        "en": "Add sandbox and list only what is needed. For showing someone else's content, an empty sandbox is usually the right answer.",
    },
    "a11y_sec_frame_sandbox_title": {
        "uk": 'Чужий кадр без пісочниці',
        "it": 'Frame di terzi senza sandbox',
        "en": 'Third-party frame with no sandbox',
    },
    "a11y_sec_frame_sandbox_found": {
        "uk": '<iframe> вказує на {src} і не має атрибута sandbox.',
        "it": "L'<iframe> punta a {src} e non ha l'attributo sandbox.",
        "en": 'The <iframe> points at {src} and carries no sandbox attribute.',
    },
    "a11y_sec_frame_sandbox_why": {
        "uk": 'Документ у кадрі з іншого походження не читає вашу сторінку, а браузер не дає йому без кліку людини перемкнути верхнє вікно чи відкрити спливне. Але після кліку в кадрі він може зробити й те, й інше, а також надсилати форми. sandbox звужує це до потрібного, тож це загартування, а не відкрита діра.',
        "it": 'Un documento in un frame di un\'altra origine non legge la tua pagina, e il browser gli impedisce di cambiare la finestra principale o aprire popup senza un clic della persona. Dopo un clic nel frame può però fare entrambe le cose e inviare form. sandbox lo limita a ciò che serve: è un rafforzamento, non una falla aperta.',
        "en": 'A framed document from another origin cannot read your page, and the browser stops it from navigating the top window or opening a popup without the person\'s click. After a click inside the frame it can do both, and submit forms. sandbox narrows that to what the embed needs: hardening, not an open hole.',
    },
    "a11y_sec_frame_sandbox_fix": {
        "uk": 'Додайте sandbox і перелічіть лише те, що кадру справді потрібно: sandbox="allow-scripts". Порожній sandbox забирає все.',
        "it": 'Aggiungi sandbox elencando solo ciò che serve davvero: sandbox="allow-scripts". Un sandbox vuoto toglie tutto.',
        "en": 'Add sandbox and list only what the frame genuinely needs: sandbox="allow-scripts". An empty sandbox removes everything.',
    },
    "a11y_sec_frame_permissions_title": {
        "uk": 'Кадру віддано чутливий дозвіл',
        "it": 'Permesso sensibile concesso a un frame',
        "en": 'A sensitive permission handed to a frame',
    },
    "a11y_sec_frame_permissions_found": {
        "uk": '<iframe> на {src} отримує через allow: {granted}.',
        "it": "L'<iframe> su {src} riceve tramite allow: {granted}.",
        "en": 'The <iframe> at {src} is granted, via allow: {granted}.',
    },
    "a11y_sec_frame_permissions_why": {
        "uk": 'Дозвіл, делегований у розмітці, надається без того, щоб чуже походження перепитало людину в сторінці. Камера, мікрофон, геолокація і платежі це ті чотири, які варто перечитати двічі.',
        "it": "Un permesso delegato nel markup viene concesso senza che l'origine di terzi richieda di nuovo il consenso. Camera, microfono, geolocalizzazione e pagamenti sono i quattro da rileggere due volte.",
        "en": 'A permission delegated in markup is granted without the framed origin asking the person in the page again. Camera, microphone, geolocation and payment are the four worth reading twice.',
    },
    "a11y_sec_frame_permissions_fix": {
        "uk": 'Приберіть із allow усе, чого кадр не використовує. Якщо потрібно все перелічене, звузьте походження в самому src.',
        "it": "Rimuovi da allow tutto ciò che il frame non usa. Se serve davvero tutto, restringi l'origine nello stesso src.",
        "en": 'Drop from allow everything the frame does not use. If it genuinely needs all of it, narrow the origin in src itself.',
    },
    "a11y_sec_form_insecure_action_title": {
        "uk": 'Форма надсилає дані через http',
        "it": 'Il form invia i dati via http',
        "en": 'The form posts over http',
    },
    "a11y_sec_form_insecure_action_found": {
        "uk": '<form action="{action}"> надсилає через http.',
        "it": '<form action="{action}"> invia via http.',
        "en": '<form action="{action}"> posts over http.',
    },
    "a11y_sec_form_insecure_action_why": {
        "uk": 'Усе набране в цій формі перетинає мережу відкритим текстом. Те, що сама сторінка на https, робить це легким для пропуску: замок стосується сторінки, а не того, куди йде форма.',
        "it": 'Tutto ciò che viene digitato attraversa la rete in chiaro. Il fatto che la pagina sia in https rende la cosa facile da mancare: il lucchetto riguarda la pagina, non la destinazione del form.',
        "en": 'Everything typed into it crosses the network in the clear. The page itself being HTTPS is what makes this easy to miss: the padlock is about the page, not about where the form goes.',
    },
    "a11y_sec_form_insecure_action_fix": {
        "uk": 'Змініть action на https, або на відносний шлях, щоб він успадкував схему сторінки.',
        "it": 'Cambia action in https, oppure in un percorso relativo così eredita lo schema della pagina.',
        "en": "Change action to https, or to a relative path so it inherits the page's scheme.",
    },
    "a11y_sec_script_integrity_title": {
        "uk": 'Чужий скрипт без перевірки цілісності',
        "it": 'Script di terzi senza controllo di integrità',
        "en": 'Third-party script with no integrity check',
    },
    "a11y_sec_script_integrity_found": {
        "uk": '<script src="{src}"> завантажується з {host} без integrity.',
        "it": '<script src="{src}"> viene caricato da {host} senza integrity.',
        "en": '<script src="{src}"> is loaded from {host} with no integrity.',
    },
    "a11y_sec_script_integrity_why": {
        "uk": 'Що б це походження не віддало, воно виконається з повними правами цієї сторінки. Хеш integrity змушує браузер відмовитись від усього іншого, і це різниця між довірою до CDN сьогодні та довірою щодня.',
        "it": "Qualunque cosa quell'origine serva viene eseguita con tutti i diritti di questa pagina. Un hash integrity fa sì che il browser rifiuti qualsiasi altra cosa: è la differenza tra fidarsi di una CDN oggi e fidarsene ogni giorno.",
        "en": 'Whatever that origin serves runs with the full rights of this page. An integrity hash makes the browser refuse anything else, which is the difference between trusting a CDN today and trusting it every day.',
    },
    "a11y_sec_script_integrity_fix": {
        "uk": 'Додайте integrity="sha384-..." разом із crossorigin="anonymous", або покладіть файл поруч зі сторінкою.',
        "it": 'Aggiungi integrity="sha384-..." insieme a crossorigin="anonymous", oppure ospita il file accanto alla pagina.',
        "en": 'Add integrity="sha384-..." alongside crossorigin="anonymous", or host the file beside the page.',
    },
    "a11y_sec_secret_in_markup_title": {
        "uk": 'Ключ записаний у розмітці',
        "it": 'Una chiave scritta nel markup',
        "en": 'A key written into the markup',
    },
    "a11y_sec_secret_in_markup_found": {
        "uk": 'Атрибут {attribute} несе значення довжиною {length} символів.',
        "it": "L'attributo {attribute} contiene un valore di {length} caratteri.",
        "en": 'The {attribute} attribute carries a value {length} characters long.',
    },
    "a11y_sec_secret_in_markup_why": {
        "uk": 'Розмітка публічна: її віддають кожному, хто відкриє сторінку, і вона лежить у репозиторії. Ключ тут це ключ опублікований, хай як називається атрибут.',
        "it": "Il markup è pubblico: viene servito a chiunque apra la pagina ed è nel repository. Una chiave qui è una chiave pubblicata, comunque si chiami l'attributo.",
        "en": 'Markup is public: it is served to everyone who opens the page and it is in the repository. A key here is a key published, whatever the attribute is called.',
    },
    "a11y_sec_secret_in_markup_fix": {
        "uk": 'Заберіть значення з розмітки. Якщо клієнту потрібен доступ, віддайте його з сервера за сеансом, і відкличте те, що вже опубліковано.',
        "it": "Togli il valore dal markup. Se il client ha bisogno dell'accesso, forniscilo dal server per sessione, e revoca ciò che è già stato pubblicato.",
        "en": 'Take the value out of the markup. If the client needs access, hand it out from the server per session, and revoke whatever has already been published.',
    },
    "a11y_sec_autocomplete_secret_title": {
        "uk": 'Браузеру сказано запамʼятати пароль',
        "it": 'Al browser è stato detto di ricordare la password',
        "en": 'The browser is told to remember the password',
    },
    "a11y_sec_autocomplete_secret_found": {
        "uk": 'Поле пароля має autocomplete="{autocomplete}".',
        "it": 'Il campo password ha autocomplete="{autocomplete}".',
        "en": 'The password field has autocomplete="{autocomplete}".',
    },
    "a11y_sec_autocomplete_secret_why": {
        "uk": 'autocomplete="on" на полі пароля просить браузер зберегти те, що не має пережити запит.',
        "it": 'autocomplete="on" su un campo password chiede al browser di conservare qualcosa che non dovrebbe sopravvivere alla richiesta.',
        "en": 'autocomplete="on" on a password field asks the browser to store something that should not outlive the request.',
    },
    "a11y_sec_autocomplete_secret_fix": {
        "uk": 'Використайте autocomplete="current-password" для входу або "new-password" для реєстрації: обидва кажуть менеджеру паролів правду й не просять зайвого.',
        "it": 'Usa autocomplete="current-password" per l\'accesso o "new-password" per la registrazione: entrambi dicono la verità al gestore di password senza chiedere altro.',
        "en": 'Use autocomplete="current-password" for sign-in or "new-password" for registration: both tell the password manager the truth without asking for more.',
    },
    "a11y_bp_mixed_content_title": {
        "uk": "Незахищений ресурс на захищеній сторінці",
        "it": "Risorsa non sicura in una pagina sicura",
        "en": "Insecure resource on a secure page",
    },
    "a11y_bp_mixed_content_found": {
        "uk": "Елемент <{element}> завантажується через http на сторінці https: {url}.",
        "it": "L'elemento <{element}> viene caricato via http in una pagina https: {url}.",
        "en": "The <{element}> is loaded over http on an https page: {url}.",
    },
    "a11y_bp_mixed_content_why": {
        "uk": "Один незахищений файл знімає гарантію з усієї сторінки: його вміст можна підмінити в дорозі, і для скрипта це означає чужий код у вашому домені. Браузери вже блокують такі скрипти повністю і поступово беруться за зображення. Сторінка працює сьогодні і перестане після оновлення браузера, яке ніхто з команди не контролює.",
        "it": "Un solo file non sicuro toglie la garanzia all'intera pagina: il suo contenuto può essere sostituito lungo il percorso e, per uno script, questo significa codice altrui nel tuo dominio. I browser bloccano già del tutto questi script e si stanno occupando gradualmente delle immagini. La pagina funziona oggi e smetterà dopo un aggiornamento del browser che nessuno nel team controlla.",
        "en": "A single insecure file removes the guarantee from the whole page: its contents can be swapped in transit, and for a script that means someone else's code running on your domain. Browsers already block such scripts outright and are steadily tightening on images. The page works today and stops working after a browser update nobody on the team controls.",
    },
    "a11y_bp_mixed_content_fix": {
        "uk": "Змініть адресу на https. Якщо чужий сервер не підтримує https - перенесіть файл до себе або замініть постачальника; лишати як є означає чекати на день, коли ресурс просто зникне зі сторінки.",
        "it": "Cambia l'indirizzo in https. Se il server esterno non supporta https, ospita il file da te o cambia fornitore: lasciarlo com'è significa aspettare il giorno in cui la risorsa sparirà dalla pagina.",
        "en": "Change the address to https. If the external server does not support https, host the file yourself or change supplier; leaving it is waiting for the day the resource simply vanishes from the page.",
    },
    "a11y_bp_target_blank_title": {
        "uk": "Посилання у нову вкладку без rel=\"noopener\"",
        "it": "Link a nuova scheda senza rel=\"noopener\"",
        "en": "New-tab link without rel=\"noopener\"",
    },
    "a11y_bp_target_blank_found": {
        "uk": "Посилання на {href} має target=\"_blank\", але не має rel=\"noopener\" чи \"noreferrer\".",
        "it": "Il link a {href} ha target=\"_blank\" ma non rel=\"noopener\" o \"noreferrer\".",
        "en": "The link to {href} has target=\"_blank\" but no rel=\"noopener\" or \"noreferrer\".",
    },
    "a11y_bp_target_blank_why": {
        "uk": "Відкрита сторінка отримує посилання назад на вашу вкладку через window.opener і може перевести її на іншу адресу, поки людина читає нову. Це класичний сценарій підміни сторінки входу. Сучасні браузери підставляють noopener самі, але старі версії і вбудовані вікна всередині застосунків - ні, і саме там така підміна найнепомітніша.",
        "it": "La pagina aperta riceve un riferimento alla tua scheda tramite window.opener e può portarla a un altro indirizzo mentre la persona legge quella nuova. È lo scenario classico di sostituzione della pagina di accesso. I browser moderni aggiungono noopener da soli, ma le versioni vecchie e le finestre incorporate nelle app no, ed è proprio lì che la sostituzione passa più inosservata.",
        "en": "The opened page gets a handle on your tab through window.opener and can navigate it elsewhere while the person is reading the new one. That is the classic login-page swap. Modern browsers imply noopener themselves, but older versions and in-app webviews do not - and those are exactly where such a swap goes unnoticed.",
    },
    "a11y_bp_target_blank_fix": {
        "uk": "Додайте rel=\"noopener noreferrer\" до кожного посилання з target=\"_blank\". Заразом подумайте, чи потрібна нова вкладка взагалі: рішення відкривати її замість людини забирає в неї кнопку «назад».",
        "it": "Aggiungi rel=\"noopener noreferrer\" a ogni link con target=\"_blank\". Già che ci sei, valuta se la nuova scheda serva davvero: deciderla al posto della persona le toglie il pulsante «indietro».",
        "en": "Add rel=\"noopener noreferrer\" to every link with target=\"_blank\". While you are there, consider whether the new tab is needed at all: deciding it on someone's behalf takes their back button away.",
    },
    # Shown when a finding is about the document rather than about an element
    # in it: nothing on screen can be outlined, and saying so beats a click
    # that appears to do nothing.
    # Width names, and the two sentences that report them. Words rather than
    # pixel counts: "1440" is a number the reader has to interpret, "desktop"
    # is the thing they were already thinking about.
    "breakpoint_tooltip": {
        "uk": "Показати прев'ю на ширині {name} ({width} px) - тій самій, на "
              "якій браузерний прохід шукав знахідки",
        "it": "Mostra l'anteprima alla larghezza {name} ({width} px), la "
              "stessa a cui il passaggio nel browser ha cercato",
        "en": "Show the preview at the {name} width ({width} px) - the same "
              "one the browser pass looked at",
    },
    "status_browser_pass_widths": {
        "uk": "Браузерний прохід на {n} ширинах: {url}",
        "it": "Passaggio nel browser a {n} larghezze: {url}",
        "en": "Browser pass at {n} widths: {url}",
    },
    # Said whenever a repository walk stopped at its cap. The one thing a
    # partial result must never do is look like a complete one.
    "finding_copies": {
        "uk": "ще у {n} файлах", "it": "in altri {n} file",
        "en": "in {n} more file(s)",
    },
    "scan_truncated": {
        "uk": "Прочитано лише {files} файлів: спрацювало обмеження в {limit}. "
              "Усе за цією межею не переглядалось, тож це не висновок про "
              "весь репозиторій.",
        "it": "Letti solo {files} file: è scattato il limite di {limit}. "
              "Tutto ciò che sta oltre non è stato esaminato, quindi questa "
              "non è una conclusione sull'intero repository.",
        "en": "Only {files} files were read: the {limit}-file limit stopped "
              "the walk. Nothing past it was examined, so this is not a "
              "statement about the whole repository.",
    },
    "status_dropped": {
        "uk": "Ціль узято з перетягнутого: {path}",
        "it": "Obiettivo preso dal file trascinato: {path}",
        "en": "Target taken from the drop: {path}",
    },
    "setup_drop_title": {
        "uk": "Перетягніть сторінку сюди",
        "it": "Trascina qui la pagina",
        "en": "Drop a page here",
    },
    "setup_drop_note": {
        "uk": "Сторінка, збережена в один файл - .html або .htm. Її можна і "
              "відрендерити, і прочитати як код. Теку теж можна перетягнути.",
        "it": "Una pagina salvata in un solo file - .html o .htm. Si può sia "
              "renderizzare sia leggere come codice. Anche una cartella si "
              "può trascinare.",
        "en": "A page saved as one file - .html or .htm. It can be rendered "
              "and read as code. A folder can be dropped too.",
    },
    "setup_drop_choose": {
        "uk": "Обрати файл…", "it": "Scegli un file…", "en": "Choose a file…",
    },
    "setup_drop_chosen": {
        "uk": "{name} · {size}", "it": "{name} · {size}", "en": "{name} · {size}",
    },
    "audit_only_at": {
        "uk": "лише @{width}", "it": "solo @{width}", "en": "only @{width}",
    },
    "audit_only_at_note": {
        "uk": "Знайдено лише на ширині «{name}». На інших ширинах правило не "
              "спрацьовує: елемент там або має назву, або його немає в DOM.",
        "it": "Rilevato solo alla larghezza «{name}». Alle altre la regola non "
              "scatta: lì l'elemento ha un nome oppure non è nel DOM.",
        "en": "Found only at the {name} width. At the others the rule does not "
              "fire: there the element either has a name or is not in the DOM "
              "at all.",
    },
    "breakpoint_default": {"uk": "типово", "it": "predefinito", "en": "default"},
    "breakpoint_all": {"uk": "усі ширини", "it": "tutte le larghezze", "en": "all widths"},
    "breakpoint_desktop": {"uk": "десктоп", "it": "desktop", "en": "desktop"},
    "breakpoint_desktop_mobile": {
        "uk": "десктоп і мобільний",
        "it": "desktop e mobile",
        "en": "desktop and mobile",
    },
    "breakpoint_tablet": {"uk": "планшет", "it": "tablet", "en": "tablet"},
    "breakpoint_mobile": {"uk": "мобільний", "it": "mobile", "en": "mobile"},
    "breakpoint_reflow": {"uk": "перекомпонування 320 px", "it": "reflow 320 px", "en": "320 px reflow"},
    "a11y_breakpoint_only": {
        "uk": "Знайдено лише на одній ширині: {breakpoints}.",
        "it": "Trovato a una sola larghezza: {breakpoints}.",
        "en": "Found at one width only: {breakpoints}.",
    },
    "a11y_breakpoint_seen": {
        "uk": "Знайдено на ширинах: {breakpoints}.",
        "it": "Trovato alle larghezze: {breakpoints}.",
        "en": "Found at these widths: {breakpoints}.",
    },
    "audit_document_level": {
        "uk": "Ця знахідка стосується документа загалом, окремого елемента для підсвітки немає.",
        "it": "Questa segnalazione riguarda il documento nel suo insieme: non c'è un elemento da evidenziare.",
        "en": "This finding is about the document as a whole - there is no single element to highlight.",
    },
    "a11y_axe_target_size_title": {
        "uk": "Ціль для натискання менша за 24×24 px і стоїть надто близько до іншої",
        "it": "Bersaglio più piccolo di 24×24 px e troppo vicino a un altro",
        "en": "Target smaller than 24×24 px and too close to another",
    },
    "a11y_axe_target_size_found": {
        "uk": "axe-core виміряв ціль у браузері, і вона не відповідає мінімуму 2.5.8.",
        "it": "axe-core ha misurato il bersaglio nel browser e non rispetta il minimo 2.5.8.",
        "en": "axe-core measured the target in the browser and it does not meet the 2.5.8 minimum.",
    },
    "a11y_axe_target_size_found_size": {
        "uk": "Виміряний розмір {width}×{height} px, мінімум {min_size}×{min_size} px.",
        "it": "Dimensione misurata {width}×{height} px, minimo {min_size}×{min_size} px.",
        "en": "Measured size {width}×{height} px, minimum {min_size}×{min_size} px.",
    },
    "a11y_axe_target_size_found_offset": {
        "uk": "Вільне коло навколо цілі має діаметр {closest_offset} px замість щонайменше {min_offset} px.",
        "it": "Lo spazio libero attorno al bersaglio ha un diametro di {closest_offset} px invece di almeno {min_offset} px.",
        "en": "The free space around the target is {closest_offset} px across instead of at least {min_offset} px.",
    },
    "a11y_axe_target_size_found_offset_to": {
        "uk": "Вільне коло навколо цілі має діаметр {closest_offset} px замість щонайменше {min_offset} px; найближча ціль: {neighbour}.",
        "it": "Lo spazio libero attorno al bersaglio ha un diametro di {closest_offset} px invece di almeno {min_offset} px; bersaglio più vicino: {neighbour}.",
        "en": "The free space around the target is {closest_offset} px across instead of at least {min_offset} px; nearest target: {neighbour}.",
    },
    "a11y_axe_target_size_why": {
        "uk": "Людина з тремором, на телефоні чи з товстим пальцем натискає не туди: замала ціль поруч з іншою означає випадкову дію. WCAG 2.2 (2.5.8, рівень AA) вимагає 24×24 CSS px або такого відступу, щоб коло діаметром 24 px навколо цілі не перетинало сусідніх. За EN 301 549 V4.1.1 це вимога Європейського акту про доступність.",
        "it": "Chi ha un tremore, usa il telefono o ha dita grandi tocca il punto sbagliato: un bersaglio piccolo accanto a un altro significa un'azione per errore. WCAG 2.2 (2.5.8, livello AA) chiede 24×24 px CSS o uno spazio tale che un cerchio di 24 px attorno al bersaglio non tocchi quelli vicini. Con EN 301 549 V4.1.1 è un requisito dell'European Accessibility Act.",
        "en": "Someone with a tremor, on a phone or with large fingers hits the wrong thing: a small target next to another means an action by mistake. WCAG 2.2 (2.5.8, level AA) asks for 24×24 CSS px, or spacing such that a 24 px circle around the target does not touch its neighbours'. Under EN 301 549 V4.1.1 it is a European Accessibility Act requirement.",
    },
    "a11y_axe_target_size_fix": {
        "uk": "Дайте елементу min-width і min-height 24px (або padding, що збільшує область натискання, а не лише картинку), або розсуньте сусідні цілі так, щоб між їхніми центрами було щонайменше 24 px.",
        "it": "Dai all'elemento min-width e min-height di 24px (o un padding che allarghi l'area cliccabile, non solo l'immagine), oppure distanzia i bersagli vicini in modo che tra i centri ci siano almeno 24 px.",
        "en": "Give the element min-width and min-height of 24px (or padding that enlarges the clickable area, not only the image), or move neighbouring targets apart so their centres are at least 24 px apart.",
    },
    "preview_load_failed": {
        "uk": "Не вдалося показати сторінку в попередньому перегляді.",
        "it": "Impossibile mostrare la pagina nell'anteprima.",
        "en": "The page could not be shown in the preview.",
    },
    # Media provenance (`audit/media.py`). Every one of these is worded as
    # "the file says", never as "this is AI": what was read is a statement
    # the file makes about itself, and the absence of one means nothing at
    # all - a screenshot or a re-save strips every field involved.
    # What the repository reveals about itself (`audit/repo_facts.py`).
    # Two of these are provenance and two are security, and the wording
    # keeps them apart: writing code with an assistant is not a defect, and
    # a credential in the working tree is not a style preference.
    # `git blame` on a finding's line (`audit/repo_facts.py`). The caveat
    # travels with the fact every time it is shown: an unqualified
    # name-and-date beside a finding reads as an accusation, and blame does
    # not support one.
    "audit_arrived": {
        "uk": "Рядок востаннє змінено", "it": "Riga modificata l'ultima volta",
        "en": "Line last changed",
    },
    "audit_arrived_assistant": {
        "uk": "Цей коміт називає асистента співавтором.",
        "it": "Questo commit indica un assistente come coautore.",
        "en": "That commit names an assistant as a co-author.",
    },
    "audit_arrived_caveat": {
        "uk": "Це коміт, який востаннє торкнувся рядка, а не обовʼязково той, "
              "що створив проблему: переформатування, перейменування чи "
              "переміщений блок так само забирають рядок на себе.",
        "it": "E il commit che ha toccato la riga per ultimo, non "
              "necessariamente quello che ha creato il problema: una "
              "riformattazione, una rinomina o un blocco spostato prendono la "
              "riga su di se allo stesso modo.",
        "en": "This is the commit that last touched the line, not necessarily "
              "the one that created the problem: a reformat, a rename or a "
              "moved block take the line over just the same.",
    },
    "a11y_bp_assistant_touched_title": {
        "uk": "Частина знахідок у рядках з асистентських комітів",
        "it": "Alcuni riscontri su righe di commit con assistente",
        "en": "Some findings sit on lines from assistant commits",
    },
    "a11y_bp_assistant_touched_found": {
        "uk": "{count} із {read} знахідок, які вдалось привʼязати до рядка, "
              "стоять у рядках, востаннє змінених комітами, що називають "
              "асистента співавтором.",
        "it": "{count} dei {read} riscontri collegabili a una riga si trovano "
              "su righe toccate per ultime da commit che indicano un assistente "
              "come coautore.",
        "en": "{count} of the {read} findings that could be placed on a line "
              "sit on lines last touched by commits naming an assistant as a "
              "co-author.",
    },
    "a11y_bp_assistant_touched_why": {
        "uk": "Це не звинувачення і не оцінка: `git blame` називає коміт, який "
              "востаннє торкнувся рядка, а не той, що створив проблему. "
              "Показано тому, що це єдина точна відповідь на питання про "
              "походження, яку взагалі можна отримати, і тому, що вона своя для "
              "кожного проєкту: у одному це нічого не означає, у іншому це "
              "привід подивитись, як приймається така робота.",
        "it": "Non e un'accusa ne una valutazione: `git blame` nomina il commit "
              "che ha toccato la riga per ultimo, non quello che ha creato il "
              "problema. Viene mostrato perche e l'unica risposta esatta sulla "
              "provenienza che si possa ottenere, e perche significa cose "
              "diverse in progetti diversi.",
        "en": "Not an accusation and not a judgement: `git blame` names the "
              "commit that last touched a line, not the one that created the "
              "problem. It is shown because it is the only exact answer about "
              "provenance available at all, and because it means different "
              "things in different projects - nothing in one, and a reason to "
              "look at how that work is reviewed in another.",
    },
    "a11y_bp_assistant_touched_fix": {
        "uk": "Дії не потрібно. Якщо число здається великим, дивіться не на "
              "інструмент, а на те, як така робота переглядається перед злиттям.",
        "it": "Non serve alcuna azione. Se il numero sembra alto, guardate non "
              "lo strumento ma come quel lavoro viene rivisto prima del merge.",
        "en": "No action needed. If the number looks high, the thing to look at "
              "is not the tool but how that work gets reviewed before it lands.",
    },
    "a11y_sec_env_tracked_title": {
        "uk": "Файл із секретами вже в історії git",
        "it": "Un file con segreti e gia nella storia di git",
        "en": "A secrets file is already in git history",
    },
    "a11y_sec_env_tracked_found": {
        "uk": "{path} відстежується git, тобто він є в кожній копії репозиторія.",
        "it": "{path} e tracciato da git, quindi si trova in ogni copia del "
              "repository.",
        "en": "{path} is tracked by git, so it is in every copy of the "
              "repository.",
    },
    "a11y_sec_env_tracked_why": {
        "uk": "Це вже опубліковано. Видалення файлу цього не скасує: він "
              "лишається в кожному клоні й у кожному записі історії, і будь-хто, "
              "хто мав доступ, має ці значення.",
        "it": "E gia pubblicato. Cancellare il file non lo annulla: resta in "
              "ogni clone e in ogni voce della storia, e chiunque abbia avuto "
              "accesso possiede quei valori.",
        "en": "This is already published. Deleting the file does not undo it: "
              "it stays in every clone and every history entry, and anyone who "
              "had access has those values.",
    },
    "a11y_sec_env_tracked_fix": {
        "uk": "Змініть ці облікові дані. Прибирання файлу з історії має сенс "
              "лише після того, і саме в такому порядку.",
        "it": "Cambiate quelle credenziali. Rimuovere il file dalla storia ha "
              "senso solo dopo, e in quest'ordine.",
        "en": "Rotate those credentials. Removing the file from history is "
              "worth doing only afterwards, and in that order.",
    },
    "a11y_sec_env_not_ignored_title": {
        "uk": "Файл із секретами не в ігнорі",
        "it": "Un file con segreti non e ignorato",
        "en": "A secrets file is not ignored",
    },
    "a11y_sec_env_not_ignored_found": {
        "uk": "{path} лежить у робочій теці, і жодне правило ігнорування його "
              "не покриває.",
        "it": "{path} si trova nella cartella di lavoro e nessuna regola di "
              "ignore lo copre.",
        "en": "{path} is in the working tree and no ignore rule covers it.",
    },
    "a11y_sec_env_not_ignored_why": {
        "uk": "Ще не опубліковано, і саме тому це варто читати зараз: "
              "наступний `git add .` забере його з собою, і тоді буде пізно.",
        "it": "Non e ancora pubblicato, ed e proprio per questo che vale la "
              "pena leggerlo adesso: il prossimo `git add .` se lo porta via.",
        "en": "Not published yet, which is exactly why this is worth reading "
              "now: the next `git add .` takes it along, and then it is too "
              "late.",
    },
    "a11y_sec_env_not_ignored_fix": {
        "uk": "Додайте його до `.gitignore`.",
        "it": "Aggiungetelo a `.gitignore`.",
        "en": "Add it to `.gitignore`.",
    },
    "a11y_bp_assistant_commits_title": {
        "uk": "В історії є коміти, написані з асистентом",
        "it": "La storia contiene commit scritti con un assistente",
        "en": "The history contains commits written with an assistant",
    },
    "a11y_bp_assistant_commits_found": {
        "uk": "{count} із {read} прочитаних комітів називають асистента "
              "співавтором.",
        "it": "{count} dei {read} commit letti indicano un assistente come "
              "coautore.",
        "en": "{count} of the {read} commits read name an assistant as a "
              "co-author.",
    },
    "a11y_bp_assistant_commits_why": {
        "uk": "Це запис, а не здогад: так написано в самих комітах. І це не "
              "дефект. Писати код з асистентом нормально, а інструмент, який "
              "каже інакше, вказує людям, як їм працювати. Показано тому, що "
              "походження коду буває питанням, і відповідь на нього тут точна, "
              "на відміну від будь-якого класифікатора.",
        "it": "E un dato registrato, non una supposizione: lo dicono i commit "
              "stessi. E non e un difetto. Scrivere codice con un assistente va "
              "bene, e uno strumento che dice il contrario sta dicendo alle "
              "persone come lavorare. Viene mostrato perche la provenienza del "
              "codice a volte e una domanda, e qui la risposta e esatta.",
        "en": "This is a record, not a guess: the commits say so themselves. "
              "And it is not a defect. Writing code with an assistant is fine, "
              "and a tool that says otherwise is telling people how to work. "
              "It is shown because the provenance of code is sometimes a "
              "question, and here the answer is exact - unlike any "
              "classifier's.",
    },
    "a11y_bp_assistant_commits_fix": {
        "uk": "Дії не потрібно. Якщо ваш проєкт вимагає позначати такий внесок, "
              "це місце, де видно, що вже позначено.",
        "it": "Non serve alcuna azione. Se il vostro progetto richiede di "
              "dichiarare questo contributo, qui si vede cosa e gia dichiarato.",
        "en": "No action needed. If your project requires declaring this kind "
              "of contribution, this is where you can see what already is.",
    },
    "a11y_bp_assistant_artifacts_title": {
        "uk": "У репозиторії є конфігурація AI-інструментів",
        "it": "Il repository contiene configurazioni di strumenti AI",
        "en": "The repository carries AI tool configuration",
    },
    "a11y_bp_assistant_artifacts_found": {
        "uk": "Знайдено {count}: {names}.",
        "it": "Trovati {count}: {names}.",
        "en": "Found {count}: {names}.",
    },
    "a11y_bp_assistant_artifacts_why": {
        "uk": "Самі по собі вони нешкідливі й часто корисні. Варто подивитись "
              "з іншої причини: такі файли зазвичай містять контекст проєкту, "
              "який писали для інструмента, а не для читача, і разом із ним "
              "інколи внутрішні шляхи, імена систем і робочі домовленості.",
        "it": "Di per se sono innocui e spesso utili. Vale la pena guardarli "
              "per un altro motivo: contengono di solito contesto di progetto "
              "scritto per uno strumento e non per un lettore, e insieme a "
              "quello a volte percorsi interni, nomi di sistemi e accordi di "
              "lavoro.",
        "en": "They are harmless in themselves and often useful. They are worth "
              "a look for a different reason: such files usually hold project "
              "context written for a tool rather than for a reader, and with it "
              "sometimes internal paths, system names and working arrangements.",
    },
    "a11y_bp_assistant_artifacts_fix": {
        "uk": "Прочитайте їх як опубліковані. Якщо там є те, чого ви не "
              "публікували б, приберіть це звідти або файл з індексу.",
        "it": "Leggeteli come se fossero pubblicati. Se contengono qualcosa che "
              "non pubblichereste, toglietelo o togliete il file dall'indice.",
        "en": "Read them as published. If they hold anything you would not "
              "publish, take it out - or take the file out of the index.",
    },
    "a11y_bp_ai_media_declared_title": {
        "uk": "Файл каже, що його згенеровано",
        "it": "Il file dichiara di essere generato",
        "en": "The file states it was generated",
    },
    "a11y_bp_ai_media_declared_found": {
        "uk": "У полі {marker} записано, що зображення зробила модель.",
        "it": "Il campo {marker} dichiara che l'immagine e stata prodotta da "
              "un modello.",
        "en": "The {marker} field records that a model produced this image.",
    },
    "a11y_bp_ai_media_declared_why": {
        "uk": "Це заява самого файлу, а не висновок перевірки: так його "
              "підписав генератор. Зворотне не діє. Відсутність такого поля "
              "не означає, що зображення зняла людина: скріншот, "
              "пересохранення або завантаження через більшість соцмереж "
              "стирають усі ці поля.",
        "it": "E una dichiarazione del file stesso, non una conclusione "
              "dell'analisi: cosi l'ha firmato il generatore. Il contrario "
              "non vale. L'assenza di questo campo non significa che la foto "
              "sia di una persona: uno screenshot, un nuovo salvataggio o il "
              "caricamento su molte piattaforme cancellano tutti questi campi.",
        "en": "This is the file's own statement, not a conclusion the check "
              "drew: the generator signed it that way. The reverse does not "
              "hold. The absence of such a field does not mean a person took "
              "the picture - a screenshot, a re-save, or an upload through "
              "most platforms strips every one of these fields.",
    },
    "a11y_bp_ai_media_declared_fix": {
        "uk": "Дія залежить від контексту, а не від інструмента: якщо "
              "зображення має бути позначене як згенероване, позначте його; "
              "якщо ні, лишіть. Прибирати саме поле не варто, бо воно і є "
              "тим, що робить походження перевірним.",
        "it": "Cosa fare dipende dal contesto, non dallo strumento: se "
              "l'immagine va dichiarata come generata, dichiaratela; "
              "altrimenti lasciatela. Non conviene rimuovere il campo: e "
              "proprio cio che rende verificabile la provenienza.",
        "en": "What to do depends on the context, not on the tool: if the "
              "image should be labelled as generated, label it; if not, leave "
              "it. Removing the field itself is rarely right - it is the "
              "thing that makes the provenance checkable at all.",
    },
    "a11y_bp_ai_media_tool_title": {
        "uk": "У файлі є назва генератора",
        "it": "Il file contiene il nome di un generatore",
        "en": "The file names a generator",
    },
    "a11y_bp_ai_media_tool_found": {
        "uk": "Поле {marker} називає {tool}.",
        "it": "Il campo {marker} nomina {tool}.",
        "en": "The {marker} field names {tool}.",
    },
    "a11y_bp_ai_media_tool_why": {
        "uk": "Слабший факт, ніж попередній: поле каже, яка програма "
              "торкалась файлу, а не звідки взялись пікселі. Зображення, "
              "відредаговане в застосунку генератора, несе той самий рядок.",
        "it": "Un fatto piu debole del precedente: il campo dice quale "
              "programma ha toccato il file, non da dove vengono i pixel. "
              "Un'immagine modificata nell'app di un generatore porta la "
              "stessa stringa.",
        "en": "A weaker fact than the one above: the field says which program "
              "touched the file, not where the pixels came from. An image "
              "edited in a generator's own app carries the same string.",
    },
    "a11y_bp_ai_media_tool_fix": {
        "uk": "Перевірте, чи це те, чим ви вважали цей файл. Правки в коді "
              "тут немає.",
        "it": "Verificate che sia cio che pensavate fosse questo file. Non "
              "c'e una correzione nel codice.",
        "en": "Check whether this is what you took the file to be. There is "
              "no code change here.",
    },
    "a11y_bp_ai_media_signed_title": {
        "uk": "Є підписані Content Credentials, не прочитані",
        "it": "Content Credentials presenti, non lette",
        "en": "Content Credentials present, unread",
    },
    "a11y_bp_ai_media_signed_found": {
        "uk": "Файл несе маніфест C2PA. Не прочитано: {value}.",
        "it": "Il file contiene un manifesto C2PA. Non letto: {value}.",
        "en": "The file carries a C2PA manifest. Not read: {value}.",
    },
    "a11y_bp_ai_media_signed_why": {
        "uk": "Підписаний маніфест є найсильнішим доказом походження, який "
              "взагалі буває, і мовчазно його пропустити означало б показати "
              "файл, що сам себе документує, як файл без документів. Прочитати "
              "підпис ця збірка не може, тож вона каже, що він є, і не вдає, "
              "що знає його зміст.",
        "it": "Un manifesto firmato e la prova di provenienza piu forte che "
              "esista, e ignorarlo in silenzio farebbe sembrare un file che si "
              "documenta da solo un file senza documenti. Questa build non sa "
              "leggere la firma, quindi dice che c'e e non finge di conoscerne "
              "il contenuto.",
        "en": "A signed manifest is the strongest provenance there is, and "
              "passing over it silently would show a file that documents "
              "itself as a file that does not. This build cannot read the "
              "signature, so it says one is there and does not pretend to "
              "know what it says.",
    },
    "a11y_bp_ai_media_signed_fix": {
        "uk": "Відкрийте файл переглядачем Content Credentials, щоб побачити "
              "підписаний ланцюг.",
        "it": "Aprite il file con un lettore di Content Credentials per vedere "
              "la catena firmata.",
        "en": "Open the file in a Content Credentials viewer to see the signed "
              "chain.",
    },
    "a11y_bp_ai_markup_artifact_title": {
        "uk": "Слід генератора в розмітці",
        "it": "Traccia del generatore nel markup",
        "en": "Generator trace left in the markup",
    },
    # The artifacts are listed as the markup tokens themselves rather than
    # described in words: a developer reading `class="claude-..."` already
    # knows what it is, and a translated noun for it would add nothing.
    "a11y_bp_ai_markup_artifact_found": {
        "uk": "Елемент <{element}> має {names} з назвою постачальника ({vendor}).",
        "it": "L'elemento <{element}> ha {names} con il nome del fornitore ({vendor}).",
        "en": "The <{element}> element carries {names}, named after a vendor ({vendor}).",
    },
    "a11y_bp_ai_markup_artifact_why": {
        "uk": "Такі імена класів і data-атрибути пишуть інтерфейси чатів, а не ваш шаблон: вони потрапляють у сторінку разом із вставленою відповіддю. Це факт про походження розмітки, а не про авторство тексту - і це не водяний знак: офіційний знак Anthropic живе у виборі слів і перевіряється лише ключем, якого немає ні в кого поза Anthropic. Клас із таким словом може належати й вашому власному коду, тому це слабкий за наслідками, але точний за фактом сигнал.",
        "it": "Questi nomi di classe e attributi data li scrivono le interfacce di chat, non il tuo template: finiscono nella pagina insieme alla risposta incollata. È un fatto sull'origine del markup, non sull'autore del testo - e non è una filigrana: il marchio ufficiale di Anthropic vive nella scelta delle parole e si verifica solo con una chiave che nessuno ha fuori da Anthropic. Una classe con quella parola può appartenere anche al tuo codice, quindi il segnale è debole per conseguenze ma esatto come fatto.",
        "en": "Class names and data attributes like these are written by chat interfaces, not by your template: they arrive in the page along with a pasted answer. It is a fact about where the markup came from, not about who wrote the words - and it is not a watermark: Anthropic's official mark lives in word choice and can only be verified with a key nobody outside Anthropic holds. A class with that word in it can equally belong to your own code, which is why this is weak in consequence and exact in fact.",
    },
    "a11y_bp_ai_markup_artifact_fix": {
        "uk": "Приберіть саме цей клас або атрибут, а не елемент: вміст лишається, зникає тільки слід. Якщо назва належить вашому власному коду, додайте її у винятки, щоб не бачити цю знахідку щоразу.",
        "it": "Rimuovi proprio quella classe o quell'attributo, non l'elemento: il contenuto resta, sparisce solo la traccia. Se il nome appartiene al tuo codice, aggiungilo alle eccezioni per non rivedere questa segnalazione ogni volta.",
        "en": "Remove that class token or attribute, not the element: the content stays, only the trace goes. If the name belongs to your own code, add it to the exceptions so the finding stops coming back.",
    },
    "a11y_bp_charset_title": {
        "uk": "Кодування сторінки не оголошено",
        "it": "Codifica della pagina non dichiarata",
        "en": "Page encoding not declared",
    },
    "a11y_bp_charset_found": {
        "uk": "У <head> немає ані <meta charset>, ані http-equiv=\"content-type\".",
        "it": "Nel <head> non c'è né <meta charset> né http-equiv=\"content-type\".",
        "en": "The <head> has neither a <meta charset> nor an http-equiv=\"content-type\".",
    },
    "a11y_bp_charset_why": {
        "uk": "Без оголошеного кодування браузер вгадує його за першими байтами і помиляється саме на тому тексті, заради якого цей інструмент існує: українські й італійські літери перетворюються на нечитабельний набір символів. Пошукова система бачить те саме сміття, тому сторінка ще й індексується зіпсованою.",
        "it": "Senza una codifica dichiarata il browser la indovina dai primi byte e sbaglia proprio sul testo per cui questo strumento esiste: le lettere ucraine e italiane diventano una sequenza illeggibile. Il motore di ricerca vede la stessa spazzatura, quindi la pagina viene anche indicizzata rovinata.",
        "en": "With no declared encoding the browser guesses from the first bytes, and it guesses wrong on exactly the text this tool exists for: Ukrainian and Italian letters turn into an unreadable run of symbols. The search engine sees the same garbage, so the page is indexed broken as well.",
    },
    "a11y_bp_charset_fix": {
        "uk": "Поставте <meta charset=\"utf-8\"> найпершим рядком у <head>, у межах перших 1024 байтів документа: далі браузер уже прийме рішення сам.",
        "it": "Metti <meta charset=\"utf-8\"> come prima riga nel <head>, entro i primi 1024 byte del documento: oltre, il browser avrà già deciso da solo.",
        "en": "Put <meta charset=\"utf-8\"> as the very first line in <head>, within the first 1024 bytes of the document: past that the browser has already decided on its own.",
    },
    "a11y_bp_doctype_title": {
        "uk": "Немає оголошення типу документа",
        "it": "Manca la dichiarazione del tipo di documento",
        "en": "No document type declaration",
    },
    "a11y_bp_doctype_found": {
        "uk": "Перед <html> немає рядка <!DOCTYPE html>.",
        "it": "Prima di <html> manca la riga <!DOCTYPE html>.",
        "en": "There is no <!DOCTYPE html> line before <html>.",
    },
    "a11y_bp_doctype_why": {
        "uk": "Без doctype браузер переходить у режим сумісності зі старими сайтами, де розміри рахуються за правилами двадцятирічної давнини. Сучасний CSS у ньому поводиться інакше, і найгірше те, що поводиться по-різному в різних браузерах - тобто помилка виглядає як випадкове розсипання макета в когось одного.",
        "it": "Senza doctype il browser passa in modalità di compatibilità con i vecchi siti, dove le dimensioni si calcolano con regole di vent'anni fa. Il CSS moderno vi si comporta diversamente e, cosa peggiore, in modo diverso da browser a browser: l'errore appare quindi come un layout che si sfalda a caso solo per qualcuno.",
        "en": "Without a doctype the browser drops into quirks mode, where sizes follow twenty-year-old rules. Modern CSS behaves differently there and, worse, differently between browsers - so the bug shows up as a layout that falls apart at random for one person only.",
    },
    "a11y_bp_doctype_fix": {
        "uk": "Додайте <!DOCTYPE html> найпершим рядком файлу, до будь-яких коментарів і порожніх рядків. Інших значень цього рядка сьогодні не потрібно.",
        "it": "Aggiungi <!DOCTYPE html> come primissima riga del file, prima di qualsiasi commento o riga vuota. Oggi non servono altri valori.",
        "en": "Add <!DOCTYPE html> as the very first line of the file, before any comments or blank lines. No other value of this line is needed today.",
    },
    "a11y_bp_inline_handlers_title": {
        "uk": "Обробник події прописаний прямо в розмітці",
        "it": "Gestore di evento scritto direttamente nel markup",
        "en": "Event handler written inline in the markup",
    },
    "a11y_bp_inline_handlers_found": {
        "uk": "Елемент <{element}> має атрибут {handler} з кодом усередині.",
        "it": "L'elemento <{element}> ha l'attributo {handler} con del codice al suo interno.",
        "en": "The <{element}> carries a {handler} attribute with code inside it.",
    },
    "a11y_bp_inline_handlers_why": {
        "uk": "Такі атрибути змушують політику безпеки вмісту дозволяти 'unsafe-inline', а це саме та зміна, після якої CSP перестає бути захистом і стає формальністю: браузер більше не може відрізнити ваш код від впровадженого. Плюс код у розмітці не проходить складання, не мінімізується і не бачиться інструментами перевірки.",
        "it": "Questi attributi costringono la Content Security Policy a consentire 'unsafe-inline', ed è proprio la modifica dopo cui la CSP smette di essere una difesa e diventa una formalità: il browser non può più distinguere il tuo codice da quello iniettato. Inoltre il codice nel markup non passa dalla build, non viene minificato e sfugge agli strumenti di analisi.",
        "en": "Such attributes force a Content Security Policy to allow 'unsafe-inline', which is the single change that turns a CSP from a defence into a formality: the browser can no longer tell your code from injected code. On top of that, code in markup skips the build, is never minified, and is invisible to your linters.",
    },
    "a11y_bp_inline_handlers_fix": {
        "uk": "Перенесіть код у скрипт і привʼяжіть його через addEventListener за селектором. Якщо інлайновий обробник лишається свідомо, дайте йому nonce або хеш у CSP, а не загальний дозвіл на весь інлайн.",
        "it": "Sposta il codice in uno script e collegalo con addEventListener tramite un selettore. Se un gestore inline resta per scelta, dagli un nonce o un hash nella CSP, non un permesso generico per tutto l'inline.",
        "en": "Move the code into a script file and attach it with addEventListener by selector. If an inline handler stays on purpose, give it a nonce or a hash in the CSP rather than a blanket allowance for all inline code.",
    },
    "a11y_bp_password_field_title": {
        "uk": "Поле пароля, яке не бачить менеджер паролів",
        "it": "Campo password che il gestore di password non riconosce",
        "en": "Password field a password manager cannot see",
    },
    "a11y_bp_password_field_found": {
        "uk": "Поле type=\"password\" має проблеми: {problems}.",
        "it": "Il campo type=\"password\" presenta i problemi: {problems}.",
        "en": "The type=\"password\" field has these problems: {problems}.",
    },
    "a11y_bp_password_field_why": {
        "uk": "Поза формою і без підказки autocomplete менеджер паролів не розпізнає поле, тому не пропонує ані зберегти, ані підставити пароль. Наслідок не технічний, а людський: люди вигадують пароль, який зможуть запам'ятати, тобто слабший, і повторюють його на інших сайтах. Заповнення вручну ще й ламає роботу з клавіатури і на мобільному.",
        "it": "Fuori da un form e senza il suggerimento autocomplete, il gestore di password non riconosce il campo e quindi non propone né di salvare né di inserire la password. La conseguenza non è tecnica ma umana: le persone inventano una password che riescono a ricordare, cioè più debole, e la riusano su altri siti. La compilazione manuale rompe anche l'uso da tastiera e da mobile.",
        "en": "Outside a form and with no autocomplete hint, a password manager does not recognise the field, so it offers neither to save nor to fill. The consequence is human rather than technical: people invent a password they can remember, which is a weaker one, and reuse it elsewhere. Typing by hand also breaks keyboard and mobile use.",
    },
    "a11y_bp_password_field_fix": {
        "uk": "Загорніть поле у <form> - навіть якщо відправка йде через JavaScript - і додайте autocomplete=\"current-password\" для входу або \"new-password\" для реєстрації і зміни пароля. Поле логіна поруч має отримати autocomplete=\"username\".",
        "it": "Racchiudi il campo in un <form>, anche se l'invio avviene via JavaScript, e aggiungi autocomplete=\"current-password\" per l'accesso o \"new-password\" per la registrazione e il cambio password. Il campo dell'utente accanto deve avere autocomplete=\"username\".",
        "en": "Wrap the field in a <form> - even when submission happens through JavaScript - and add autocomplete=\"current-password\" for sign-in or \"new-password\" for registration and password changes. The username field beside it should get autocomplete=\"username\".",
    },
    "a11y_bp_deprecated_html_title": {
        "uk": "Застарілий елемент розмітки",
        "it": "Elemento di markup obsoleto",
        "en": "Obsolete markup element",
    },
    "a11y_bp_deprecated_html_found": {
        "uk": "Знайдено <{element}>. Сучасна заміна: {replacement}.",
        "it": "Trovato <{element}>. Sostituzione moderna: {replacement}.",
        "en": "Found <{element}>. The modern replacement: {replacement}.",
    },
    "a11y_bp_deprecated_html_why": {
        "uk": "Ці теги прибрані зі стандарту, і браузери підтримують їх лише зі співчуття до старих сайтів. Підтримка не гарантована, поведінка різна, а частина з них не має жодного зрозумілого значення для програм читання з екрана. Крім того, вони змішують оформлення з вмістом, тому змінити вигляд без правки розмітки стає неможливо.",
        "it": "Questi tag sono stati rimossi dallo standard e i browser li supportano solo per compassione verso i vecchi siti. Il supporto non è garantito, il comportamento varia e alcuni non hanno alcun significato comprensibile per gli screen reader. Inoltre mescolano presentazione e contenuto, quindi cambiare l'aspetto senza toccare il markup diventa impossibile.",
        "en": "These tags were removed from the standard and browsers keep them only out of sympathy for old sites. Support is not guaranteed, behaviour varies, and several of them carry no meaning a screen reader can convey. They also mix presentation into the content, so changing the look becomes impossible without editing the markup.",
    },
    "a11y_bp_deprecated_html_fix": {
        "uk": "Замініть на {replacement}. Якщо тег лише оформлював текст, приберіть його і перенесіть вигляд у CSS; якщо він щось означав, візьміть семантичний елемент з тим самим значенням.",
        "it": "Sostituisci con {replacement}. Se il tag serviva solo a impaginare il testo, rimuovilo e sposta l'aspetto nel CSS; se aveva un significato, usa l'elemento semantico che lo esprime.",
        "en": "Replace it with {replacement}. If the tag was only styling text, drop it and move the look into CSS; if it meant something, use the semantic element that carries that meaning.",
    },
    # --- пояснення для двигунів, чий текст не наш -------------------------
    "a11y_engine_found": {
        "uk": "Знайшов {engine}, правило {rule}. Текст нижче - його власний, "
              "англійською.",
        "it": "Trovato da {engine}, regola {rule}. Il testo qui sotto è suo, "
              "in inglese.",
        "en": "Found by {engine}, rule {rule}.",
    },
    "a11y_engine_error_title": {
        "uk": "Перевірка у браузері не завершилась",
        "it": "Il controllo nel browser non è stato completato",
        "en": "The browser check did not finish",
    },
    "a11y_engine_generic_name": {
        "uk": "двигун браузера",
        "it": "motore del browser",
        "en": "browser engine",
    },
    "a11y_engine_error_found": {
        "uk": "Двигун {engine} не зміг виконати перевірку доступності.",
        "it": "Il motore {engine} non ha potuto eseguire il controllo di accessibilità.",
        "en": "The {engine} engine could not complete the accessibility check.",
    },
    "a11y_engine_error_detail": {
        "uk": "Технічна причина: {error}",
        "it": "Dettaglio tecnico: {error}",
        "en": "Technical detail: {error}",
    },
    "a11y_engine_error_fix": {
        "uk": "Перевірте, що браузер доступний, і запустіть перевірку ще раз.",
        "it": "Verifica che il browser sia disponibile e ripeti il controllo.",
        "en": "Make sure the browser is available, then run the check again.",
    },
    "a11y_engine_incomplete": {
        "uk": "{engine} не зміг вирішити сам і позначив це як таке, що "
              "потребує ручної перевірки. Це не обовʼязково помилка.",
        "it": "{engine} non ha potuto decidere e lo ha segnato come da "
              "verificare a mano. Non è necessariamente un errore.",
        "en": "{engine} could not decide and marked this as needing a manual "
              "check. It is not necessarily a defect.",
    },

    # --- становий прохід: наші правила, наші пояснення ---------------------
    "a11y_state:keyboard_trap_title": {
        "uk": "Клавіатурна пастка", "it": "Trappola per la tastiera",
        "en": "Keyboard trap",
    },
    "a11y_state:keyboard_trap_found": {
        "uk": "Елемент перехоплює Tab і не пропускає фокус далі.",
        "it": "L'elemento intercetta Tab e non lascia proseguire il focus.",
        "en": "The element swallows Tab and does not let focus move on.",
    },
    "a11y_state:keyboard_trap_why": {
        "uk": "Людина, яка користується лише клавіатурою, застрягає тут "
              "назавжди: вийти можна хіба що закривши вкладку. Це найважча з "
              "можливих перешкод, бо вона зупиняє не одну дію, а весь сеанс.",
        "it": "Chi usa solo la tastiera resta bloccato qui per sempre: si esce "
              "solo chiudendo la scheda. È l'ostacolo più grave possibile, "
              "perché non blocca una singola azione ma l'intera sessione.",
        "en": "Someone using only a keyboard is stuck here for good; the way "
              "out is closing the tab. This is the worst obstacle there is, "
              "because it stops not one action but the whole session.",
    },
    "a11y_state:keyboard_trap_fix": {
        "uk": "Не скасовуйте подію Tab. Якщо фокус тримається навмисно (модальне "
              "вікно), додайте вихід по Escape і повертайте фокус туди, звідки "
              "вікно відкрили.",
        "it": "Non annullare l'evento Tab. Se il focus è trattenuto di "
              "proposito (una finestra modale), aggiungi l'uscita con Escape e "
              "riporta il focus da dove la finestra è stata aperta.",
        "en": "Do not cancel the Tab event. If focus is held on purpose (a "
              "modal), add an Escape exit and return focus to whatever opened "
              "it.",
    },
    "a11y_state:modal_focus_not_contained_title": {
        "uk": "Фокус лишився поза відкритим модальним вікном",
        "it": "Il focus è rimasto fuori dalla finestra modale aperta",
        "en": "Focus remains outside the open modal dialog",
    },
    "a11y_state:modal_focus_not_contained_found": {
        "uk": "Видиме модальне вікно позначене aria-modal=\"true\", але активний фокус не належить йому.",
        "it": "Una finestra modale visibile è contrassegnata aria-modal=\"true\", ma il focus attivo non le appartiene.",
        "en": "A visible dialog is marked aria-modal=\"true\", but the active focus is not inside it.",
    },
    "a11y_state:modal_focus_not_contained_why": {
        "uk": "Людина з клавіатурою або програмою читання може взаємодіяти з вмістом, який модальне вікно візуально перекрило. Це змішує два стани інтерфейсу і робить діалог непередбачуваним.",
        "it": "Chi usa tastiera o screen reader può interagire con contenuto che la finestra modale ha coperto visivamente. Questo mescola due stati dell'interfaccia e rende il dialogo imprevedibile.",
        "en": "A keyboard or screen-reader user can interact with content the modal visually covers. That mixes two interface states and makes the dialog unpredictable.",
    },
    "a11y_state:modal_focus_not_contained_fix": {
        "uk": "Коли відкриваєте модальне вікно, переведіть фокус на його заголовок, перший елемент керування або сам діалог. Поки воно відкрите, не залишайте фокус на сторінці позаду.",
        "it": "Quando apri la finestra modale, sposta il focus sul titolo, sul primo controllo o sul dialogo stesso. Finché resta aperta, non lasciare il focus sulla pagina sottostante.",
        "en": "When opening the modal, move focus to its heading, first control or the dialog itself. While it remains open, do not leave focus on the page behind it.",
    },
    "a11y_state:focus_not_visible_title": {
        "uk": "Фокус не видно", "it": "Il focus non si vede",
        "en": "The focus ring is invisible",
    },
    "a11y_state:focus_not_visible_found": {
        "uk": "Елемент отримав фокус, але жодна його властивість не змінилась: "
              "ані обведення, ані тінь, ані колір рамки.",
        "it": "L'elemento ha ricevuto il focus ma nessuna sua proprietà è "
              "cambiata: né contorno, né ombra, né colore del bordo.",
        "en": "The element took focus but nothing about it changed: no "
              "outline, no shadow, no border colour.",
    },
    "a11y_state:focus_not_visible_why": {
        "uk": "Людина, яка ходить сторінкою з клавіатури, не бачить, де вона "
              "зараз. Сторінка формально працює, але користуватися нею "
              "доводиться навпомацки. Це найчастіша клавіатурна проблема, і "
              "статична перевірка її не бачить: `outline: none` майже завжди "
              "живе в таблиці стилів, а не в розмітці.",
        "it": "Chi naviga da tastiera non vede dove si trova. La pagina "
              "funziona formalmente, ma la si usa a tentoni. È il problema di "
              "tastiera più comune e un controllo statico non lo vede: "
              "`outline: none` sta quasi sempre nel foglio di stile, non nel "
              "markup.",
        "en": "Someone moving through the page by keyboard cannot see where "
              "they are. The page technically works, but has to be used by "
              "feel. This is the most common keyboard problem, and a static "
              "check cannot see it: `outline: none` almost always lives in a "
              "stylesheet, not in the markup.",
    },
    "a11y_state:focus_not_visible_fix": {
        "uk": "Приберіть `outline: none` або дайте заміну: `:focus-visible` з "
              "видимим обведенням чи тінню, контрастною до тла.",
        "it": "Rimuovi `outline: none` oppure dai un sostituto: "
              "`:focus-visible` con un contorno o un'ombra visibile, in "
              "contrasto con lo sfondo.",
        "en": "Remove `outline: none` or replace it: a `:focus-visible` rule "
              "with a visible outline or shadow that contrasts with the "
              "background.",
    },
    "a11y_state:focus_indicator_low_contrast_title": {
        "uk": "Індикатор фокуса майже зливається з тлом",
        "it": "L'indicatore del focus si distingue appena dallo sfondo",
        "en": "The focus indicator barely stands out from the background",
    },
    "a11y_state:focus_indicator_low_contrast_found": {
        "uk": "Індикатор фокуса ({indicator}, {color}) на тлі {background} дає "
              "контраст {ratio}:1, а потрібно щонайменше {required}:1.",
        "it": "L'indicatore del focus ({indicator}, {color}) su sfondo "
              "{background} ha un contrasto di {ratio}:1, ne servono almeno "
              "{required}:1.",
        "en": "The focus indicator ({indicator}, {color}) on a {background} "
              "background has a contrast of {ratio}:1; at least {required}:1 "
              "is needed.",
    },
    "a11y_state:focus_indicator_low_contrast_why": {
        "uk": "Обведення є, тож перевірка «чи змінилось щось» мовчить, але "
              "бачити його майже неможливо: білий контур на білій шапці. "
              "Людина, яка ходить сторінкою з клавіатури, і далі не знає, де "
              "вона. Це та сама проблема, що й відсутній фокус, тільки "
              "захована.",
        "it": "Il contorno c'è, quindi il controllo «è cambiato qualcosa?» "
              "tace, ma è quasi impossibile vederlo: un contorno bianco su "
              "un'intestazione bianca. Chi naviga da tastiera continua a non "
              "sapere dove si trova. È lo stesso problema del focus assente, "
              "solo nascosto.",
        "en": "There is an outline, so the \"did anything change\" check stays "
              "quiet, but it is almost impossible to see: a white outline on a "
              "white header. Someone moving through the page by keyboard "
              "still cannot tell where they are. It is the same problem as a "
              "missing focus ring, only hidden.",
    },
    "a11y_state:focus_indicator_low_contrast_fix": {
        "uk": "Зробіть контур контрастним до сусіднього тла (щонайменше 3:1) "
              "або додайте другий контур протилежного кольору, як два кільця "
              "біле плюс темне. Перевіряйте і у sticky-стані, де тло інше.",
        "it": "Rendi il contorno contrastato rispetto allo sfondo adiacente "
              "(almeno 3:1) oppure aggiungi un secondo anello di colore "
              "opposto, bianco più scuro. Controlla anche nello stato sticky, "
              "dove lo sfondo è diverso.",
        "en": "Give the outline at least 3:1 against the background next to "
              "it, or add a second ring of the opposite colour, a white one "
              "plus a dark one. Check the sticky state too, where the "
              "background is different.",
    },
    "a11y_state:focus_obscured_title": {
        "uk": "Елемент у фокусі повністю закритий фіксованим блоком",
        "it": "L'elemento con il focus è coperto del tutto da un blocco fisso",
        "en": "The focused element is entirely covered by a fixed block",
    },
    "a11y_state:focus_obscured_found": {
        "uk": "Коли браузер прокручує елемент до {edge} краю вікна, його "
              "повністю перекриває {coveredBy} (висота {coverHeight} px). "
              "Таких елементів на сторінці: {count}. Рамки (x, y, ширина, "
              "висота) у вікні {viewport}: елемент {elementBox}, перекриття "
              "{coverBox}.",
        "it": "Quando il browser porta l'elemento al bordo {edge} della "
              "finestra, lo copre del tutto {coveredBy} (altezza "
              "{coverHeight} px). Elementi interessati nella pagina: {count}. "
              "Riquadri (x, y, larghezza, altezza) nella finestra {viewport}: "
              "elemento {elementBox}, copertura {coverBox}.",
        "en": "When the browser scrolls the element to the {edge} edge of the "
              "window, {coveredBy} ({coverHeight} px tall) covers it "
              "completely. Elements affected on this page: {count}. Boxes "
              "(x, y, width, height) in a {viewport} window: element "
              "{elementBox}, cover {coverBox}.",
    },
    "a11y_state:focus_obscured_why": {
        "uk": "Людина, яка йде сторінкою з клавіатури, бачить, як фокус "
              "зникає під липкою шапкою: елемент сфокусований, але його не "
              "видно. Shift+Tab угору веде просто під шапку, тому страждають "
              "саме посилання хлібних крихт і початок сторінки.",
        "it": "Chi naviga da tastiera vede il focus sparire sotto "
              "l'intestazione fissa: l'elemento è a fuoco ma non si vede. "
              "Shift+Tab verso l'alto porta proprio sotto l'intestazione, "
              "quindi a soffrirne sono i link del breadcrumb e l'inizio della "
              "pagina.",
        "en": "Someone moving through the page by keyboard watches focus "
              "disappear under the sticky header: the element is focused but "
              "cannot be seen. Shift+Tab upwards lands right under the "
              "header, so the breadcrumb links and the top of the page suffer "
              "most.",
    },
    "a11y_state:focus_not_measured_title": {
        "uk": "Фокус на цій сторінці не вдалося виміряти",
        "it": "Il focus di questa pagina non è stato misurabile",
        "en": "Focus could not be measured on this page",
    },
    "a11y_state:focus_not_measured_found": {
        "uk": "Сторінка не мала фокуса вікна, тому стилі :focus не застосовувались до {count} перевірених елементів.",
        "it": "La pagina non aveva il focus della finestra, quindi gli stili :focus non si sono applicati ai {count} elementi controllati.",
        "en": "The page did not have window focus, so :focus styles did not apply to the {count} elements checked.",
    },
    "a11y_state:focus_not_measured_why": {
        "uk": "Відсутність знахідок про фокус у цьому звіті нічого не доводить: перевірки видимості фокуса, його контрасту і перекриття не мали з чого читати. Це не дефект сторінки, а межа самого прогону.",
        "it": "L'assenza di segnalazioni sul focus in questo rapporto non prova nulla: i controlli su visibilità, contrasto e copertura del focus non avevano nulla da leggere. Non è un difetto della pagina ma un limite di questa esecuzione.",
        "en": "The absence of focus findings in this report proves nothing: the checks for focus visibility, contrast and obstruction had nothing to read. This is not a defect of the page but a limit of this run.",
    },
    "a11y_state:focus_not_measured_fix": {
        "uk": "Запустіть аудит у режимі CLI (`audit --browser`), де прихованому переглядачу надається фокус, або перевірте фокус вручну клавішею Tab.",
        "it": "Esegui l'audit da riga di comando (`audit --browser`), dove alla vista nascosta viene dato il focus, oppure controlla il focus a mano con il tasto Tab.",
        "en": "Run the audit from the command line (`audit --browser`), where the hidden view is given focus, or check focus by hand with the Tab key.",
    },
    "a11y_state:focus_obscured_fix": {
        "uk": "Одне правило на весь сайт: `scroll-margin-top` (або "
              "`scroll-padding-top` на контейнері прокрутки) дорівнює висоті "
              "липкої шапки, краще через CSS-змінну. Для нижньої панелі "
              "так само `scroll-margin-bottom`.",
        "it": "Una sola regola per tutto il sito: `scroll-margin-top` (o "
              "`scroll-padding-top` sul contenitore di scorrimento) uguale "
              "all'altezza dell'intestazione fissa, meglio con una variabile "
              "CSS. Per una barra in basso vale `scroll-margin-bottom`.",
        "en": "One rule for the whole site: `scroll-margin-top` (or "
              "`scroll-padding-top` on the scroll container) equal to the "
              "sticky header's height, ideally through a CSS variable. For a "
              "bar at the bottom, `scroll-margin-bottom` does the same.",
    },
    "a11y_state:focus_order_mismatch_title": {
        "uk": "Порядок фокуса не збігається з порядком читання",
        "it": "L'ordine del focus non segue l'ordine di lettura",
        "en": "Focus order does not follow reading order",
    },
    "a11y_state:focus_order_mismatch_found": {
        "uk": "Фокус кілька разів стрибає вгору сторінкою замість того, щоб "
              "рухатись донизу.",
        "it": "Il focus salta più volte verso l'alto invece di scendere.",
        "en": "Focus jumps back up the page several times instead of moving "
              "down it.",
    },
    "a11y_state:focus_order_mismatch_why": {
        "uk": "Той, хто не бачить сторінки цілком, будує її мапу з порядку "
              "обходу. Коли порядок стрибає, мапа виходить неправильною, і "
              "людина губиться там, де зряча людина просто дивиться нижче.",
        "it": "Chi non vede l'intera pagina se ne costruisce la mappa "
              "dall'ordine di attraversamento. Se l'ordine salta, la mappa "
              "esce sbagliata e la persona si perde dove una vedente "
              "guarderebbe semplicemente più in basso.",
        "en": "Someone who cannot see the whole page builds their map of it "
              "from the order they move through it. When the order jumps, the "
              "map comes out wrong, and they get lost where a sighted person "
              "would simply look further down.",
    },
    "a11y_state:focus_order_mismatch_fix": {
        "uk": "Приведіть порядок у розмітці до порядку на екрані. Не "
              "виправляйте це через `tabindex` із додатними значеннями: так "
              "проблема лише переміщується.",
        "it": "Allinea l'ordine nel markup a quello sullo schermo. Non "
              "correggerlo con `tabindex` positivi: così il problema si "
              "sposta soltanto.",
        "en": "Bring the order in the markup in line with the order on "
              "screen. Do not patch it with positive `tabindex` values: that "
              "only moves the problem.",
    },
    "a11y_state:hover_only_content_title": {
        "uk": "Вміст зʼявляється лише під мишею",
        "it": "Contenuto visibile solo al passaggio del mouse",
        "en": "Content that only appears on hover",
    },
    "a11y_state:hover_only_content_found": {
        "uk": "Прихований блок відкривається наведенням, але не має "
              "рівноцінного відкриття з клавіатури.",
        "it": "Un blocco nascosto si apre al passaggio del mouse ma non ha "
              "un equivalente da tastiera.",
        "en": "A hidden block opens on hover but has no keyboard equivalent.",
    },
    "a11y_state:hover_only_content_why": {
        "uk": "Без миші цього вмісту не існує зовсім. Якщо там пункти меню, "
              "частина сайту стає недосяжною - і не лише для клавіатури, а й "
              "для сенсорного екрана, де наведення немає.",
        "it": "Senza mouse quel contenuto non esiste affatto. Se contiene voci "
              "di menu, una parte del sito diventa irraggiungibile: non solo "
              "da tastiera, ma anche su touch, dove il passaggio del mouse non "
              "esiste.",
        "en": "Without a mouse that content does not exist at all. If it holds "
              "menu items, part of the site becomes unreachable - not only "
              "from a keyboard but on touch, where there is no hover.",
    },
    "a11y_state:hover_only_content_fix": {
        "uk": "Відкривайте те саме на `:focus-within` або кнопкою з "
              "`aria-expanded`, яку можна натиснути з клавіатури.",
        "it": "Apri lo stesso contenuto con `:focus-within` o con un pulsante "
              "con `aria-expanded` azionabile da tastiera.",
        "en": "Open the same content on `:focus-within`, or from a button "
              "with `aria-expanded` that a keyboard can operate.",
    },
    "a11y_state:no_skip_link_title": {
        "uk": "Немає посилання «перейти до вмісту»",
        "it": "Manca il link «vai al contenuto»",
        "en": "No skip link",
    },
    "a11y_state:no_skip_link_found": {
        "uk": "У шапці й навігації {navLinks} посилань, а способу оминути їх "
              "немає.",
        "it": "Nell'intestazione e nella navigazione ci sono {navLinks} link e "
              "non c'è modo di saltarli.",
        "en": "The header and navigation hold {navLinks} links, and there is "
              "no way past them.",
    },
    "a11y_state:no_skip_link_why": {
        "uk": "Кожен візит із клавіатури починається з проходу через усе меню "
              "наново. На кожній сторінці. Це не помилка, а щоденний податок "
              "на користування сайтом.",
        "it": "Ogni visita da tastiera comincia riattraversando tutto il menu. "
              "Su ogni pagina. Non è un errore, è una tassa quotidiana "
              "sull'uso del sito.",
        "en": "Every keyboard visit starts by tabbing through the whole menu "
              "again. On every page. It is not an error so much as a daily tax "
              "on using the site.",
    },
    "a11y_state:no_skip_link_fix": {
        "uk": "Додайте першим у `<body>` посилання на якір основного вмісту. "
              "Воно може бути прихованим, поки не отримає фокус.",
        "it": "Aggiungi come primo elemento di `<body>` un link all'ancora del "
              "contenuto principale. Può restare nascosto finché non riceve il "
              "focus.",
        "en": "Add a link to the main content anchor as the first thing in "
              "`<body>`. It can stay hidden until it takes focus.",
    },
    "a11y_state:focus_outside_viewport_title": {
        "uk": "Фокус іде за межі видимої області",
        "it": "Il focus finisce fuori dall'area visibile",
        "en": "Focus lands outside the visible area",
    },
    "a11y_state:focus_outside_viewport_found": {
        "uk": "Елемент отримує фокус, перебуваючи поза екраном.",
        "it": "L'elemento riceve il focus mentre si trova fuori schermo.",
        "en": "The element takes focus while it is off screen.",
    },
    "a11y_state:focus_outside_viewport_why": {
        "uk": "Фокус зникає з очей: людина натискає Tab і не бачить нічого "
              "нового, хоча наступне натискання вже стосується елемента, якого "
              "вона не бачила. Так зазвичай поводяться закриті меню, які "
              "прибрали зсувом, а не з дерева фокуса.",
        "it": "Il focus sparisce dalla vista: si preme Tab e non cambia nulla "
              "di visibile, mentre la pressione successiva agisce già su un "
              "elemento mai visto. È il comportamento tipico dei menu chiusi "
              "spostati fuori schermo invece che tolti dall'ordine di focus.",
        "en": "Focus disappears from sight: the user presses Tab, sees nothing "
              "change, and their next keystroke already acts on an element "
              "they never saw. This is what closed menus do when they are "
              "moved off screen instead of taken out of the focus order.",
    },
    "a11y_state:focus_outside_viewport_fix": {
        "uk": "Прибирайте приховане з порядку фокуса: `display: none`, "
              "`visibility: hidden` або `inert` замість зсуву за край екрана.",
        "it": "Togli ciò che è nascosto dall'ordine di focus: `display: none`, "
              "`visibility: hidden` o `inert` invece di spostarlo oltre il "
              "bordo.",
        "en": "Take hidden things out of the focus order: `display: none`, "
              "`visibility: hidden` or `inert` rather than moving them past "
              "the edge.",
    },
    "a11y_state:state_pass_title": {
        "uk": "Перевірка станів не завершилась",
        "it": "Il controllo degli stati non è terminato",
        "en": "The state pass did not finish",
    },
    "a11y_state:state_pass_found": {
        "uk": "Прохід по станах сторінки впав: {engine_error}",
        "it": "Il passaggio sugli stati della pagina è fallito: {engine_error}",
        "en": "The pass over the page's states failed: {engine_error}",
    },
    "a11y_state:state_pass_why": {
        "uk": "Перевірки фокуса, клавіатурних пасток і вмісту під мишею для "
              "цієї сторінки не виконано, тож їхня відсутність у списку нічого "
              "не означає.",
        "it": "I controlli su focus, trappole per la tastiera e contenuto al "
              "passaggio del mouse non sono stati eseguiti per questa pagina: "
              "la loro assenza dall'elenco non significa nulla.",
        "en": "The focus, keyboard-trap and hover checks did not run for this "
              "page, so their absence from the list means nothing.",
    },
    "a11y_state:state_pass_fix": {
        "uk": "Спробуйте ще раз; якщо повторюється - сторінка, ймовірно, "
              "перевизначає щось, на що спирається перевірка.",
        "it": "Riprova; se si ripete, la pagina probabilmente ridefinisce "
              "qualcosa su cui il controllo si appoggia.",
        "en": "Try again; if it repeats, the page is probably overriding "
              "something the check relies on.",
    },
    # --- нові правила accessibility (2026-08-20) ---
    "a11y_landmark_regions_title": {
        "uk": "Сторінка без основної області (landmark)",
        "it": "Pagina senza area principale (landmark)",
        "en": "Page without main landmark region",
    },
    "a11y_landmark_regions_found": {
        "uk": "На сторінці немає <main> або ARIA-ролі main. Знайдені області: {found}.",
        "it": "La pagina non ha <main> né un ruolo ARIA main. Aree trovate: {found}.",
        "en": "The page has no <main> or ARIA role main. Found regions: {found}.",
    },
    "a11y_landmark_regions_why": {
        "uk": "Програма читання з екрана не має способу перейти до основного вмісту: користувач змушений табулювати через всю навігацію на кожній сторінці. Landmark-області - це те, як незряча людина «бачить» структуру сторінки.",
        "it": "Lo screen reader non ha un modo per saltare al contenuto principale: l'utente deve tabulare attraverso tutta la navigazione su ogni pagina. Le aree landmark sono il modo in cui una persona non vedente «vede» la struttura della pagina.",
        "en": "A screen reader has no way to jump to the main content: the user must tab through the entire navigation on every page. Landmark regions are how a blind person «sees» the page structure.",
    },
    "a11y_landmark_regions_fix": {
        "uk": "Обгорніть основний вміст сторінки у <main>. Навігацію обгорніть у <nav>, шапку у <header>, підвал у <footer>. Це не змінює вигляд, але дає програмі читання карту сторінки.",
        "it": "Racchiudi il contenuto principale in <main>. Avvolgi la navigazione in <nav>, l'intestazione in <header>, il piè di pagina in <footer>. Non cambia l'aspetto ma dà allo screen reader una mappa della pagina.",
        "en": "Wrap the main content in <main>. Wrap navigation in <nav>, the header in <header>, the footer in <footer>. This does not change the look but gives the screen reader a map of the page.",
    },
    "a11y_skip_link_title": {
        "uk": "Немає посилання «перейти до вмісту»",
        "it": "Manca il link «vai al contenuto»",
        "en": "No «skip to content» link",
    },
    "a11y_skip_link_found": {
        "uk": "Перші 10 посилань на сторінці не ведуть до якоря на основному вмісті.",
        "it": "I primi 10 link sulla pagina non portano a un'ancora sul contenuto principale.",
        "en": "The first 10 links on the page do not point to an anchor on the main content.",
    },
    "a11y_skip_link_why": {
        "uk": "Клавіатурний користувач на кожній сторінці змушений проходити через всю навігацію, перш ніж дістатися до вмісту. Це 10-20 натискань Tab на кожному переході, і для людини з обмеженою моторикою це реальна перешкода.",
        "it": "Un utente da tastiera è costretto a passare attraverso tutta la navigazione prima di raggiungere il contenuto su ogni pagina. Sono 10-20 pressioni di Tab a ogni transizione, e per chi ha limitazioni motorie è un ostacolo reale.",
        "en": "A keyboard user must tab through the entire navigation before reaching the content on every page. That is 10-20 Tab presses per transition, and for someone with limited motor ability it is a real barrier.",
    },
    "a11y_skip_link_fix": {
        "uk": "Додайте першим елементом у <body> посилання <a href=\"#main\" class=\"skip-link\">Перейти до вмісту</a>, яке веде до id основного блоку. Воно може бути прихованим і з'являтися лише при фокусі (Tab).",
        "it": "Aggiungi come primo elemento in <body> un link <a href=\"#main\" class=\"skip-link\">Vai al contenuto</a> che punta all'id del blocco principale. Può essere nascosto e comparire solo al focus (Tab).",
        "en": "Add as the first element in <body> a link <a href=\"#main\" class=\"skip-link\">Skip to content</a> pointing to the main block's id. It can be hidden and appear only on focus (Tab).",
    },
    "a11y_form_error_message_title": {
        "uk": "Поле з помилкою без опису помилки",
        "it": "Campo con errore senza descrizione dell'errore",
        "en": "Field with error but no error description",
    },
    "a11y_form_error_message_found": {
        "uk": "Поле <{element}> має aria-invalid=\"true\", але не має aria-describedby або aria-errormessage.",
        "it": "Il campo <{element}> ha aria-invalid=\"true\" ma non ha aria-describedby né aria-errormessage.",
        "en": "The <{element}> field has aria-invalid=\"true\" but no aria-describedby or aria-errormessage.",
    },
    "a11y_form_error_message_why": {
        "uk": "Програма читання з екрана оголосить «неправильне поле», але не скаже що саме не так. Користувач знає що помилився, але не знає як виправити, і змушений вгадувати або просити допомоги зрячої людини.",
        "it": "Lo screen reader annuncerà «campo non valido» ma non dirà cosa c'è di sbagliato. L'utente sa di aver sbagliato ma non come correggere, e deve indovinare o chiedere aiuto a una persona vedente.",
        "en": "A screen reader will announce «invalid field» but will not say what is wrong. The user knows they made a mistake but not how to fix it, and must either guess or ask a sighted person for help.",
    },
    "a11y_form_error_message_fix": {
        "uk": "Додайте до поля aria-describedby=\"error-id\", де error-id - id елемента з текстом помилки. Або використовуйте aria-errormessage=\"error-id\" для явного зв'язку.",
        "it": "Aggiungi al campo aria-describedby=\"error-id\", dove error-id è l'id dell'elemento con il testo dell'errore. Oppure usa aria-errormessage=\"error-id\" per un collegamento esplicito.",
        "en": "Add to the field aria-describedby=\"error-id\" where error-id is the id of the element with the error text. Or use aria-errormessage=\"error-id\" for an explicit link.",
    },
    "a11y_table_scope_title": {
        "uk": "Заголовки таблиці без атрибута scope",
        "it": "Intestazioni di tabella senza attributo scope",
        "en": "Table headers without scope attribute",
    },
    "a11y_table_scope_found": {
        "uk": "Таблиця має {th_count} заголовків <th>, але жоден не має scope. {rows} рядків.",
        "it": "La tabella ha {th_count} intestazioni <th> ma nessuna ha scope. {rows} righe.",
        "en": "The table has {th_count} <th> headers but none has scope. {rows} rows.",
    },
    "a11y_table_scope_why": {
        "uk": "Без scope програма читання з екрана не знає чи заголовок стовпця, чи рядка. У складній таблиці це означає, що користувач чує значення «42» без розуміння до якого стовпця воно належить.",
        "it": "Senza scope lo screen reader non sa se l'intestazione è di colonna o di riga. In una tabella complessa significa che l'utente sente il valore «42» senza sapere a quale colonna appartiene.",
        "en": "Without scope a screen reader does not know if the header is for a column or a row. In a complex table this means the user hears the value «42» without knowing which column it belongs to.",
    },
    "a11y_table_scope_fix": {
        "uk": "Додайте до заголовків стовпців scope=\"col\", до заголовків рядків - scope=\"row\". Це одна мить і миттєво робить таблицю зрозумілою для програми читання.",
        "it": "Aggiungi alle intestazioni di colonna scope=\"col\" e alle intestazioni di riga scope=\"row\". È un attimo e rende la tabella immediatamente comprensibile allo screen reader.",
        "en": "Add scope=\"col\" to column headers and scope=\"row\" to row headers. It takes a moment and instantly makes the table understandable to a screen reader.",
    },
    "a11y_hreflang_links_title": {
        "uk": "Мультимовний сайт без hreflang",
        "it": "Sito multilingua senza hreflang",
        "en": "Multilingual site without hreflang",
    },
    "a11y_hreflang_links_found": {
        "uk": "Сторінка має мову {lang} і посилання на іншомовні версії, але немає hreflang-тегів у <head>.",
        "it": "La pagina ha la lingua {lang} e link a versioni in altre lingue, ma non ci sono tag hreflang nel <head>.",
        "en": "The page has language {lang} and links to other-language versions, but no hreflang tags in <head>.",
    },
    "a11y_hreflang_links_why": {
        "uk": "Пошуковик не знає яка версія сторінки для якої мови, тому може показати українську сторінку італійському користувачу або навпаки. Це псує досвід і знижує рейтинг у локальному пошуку.",
        "it": "Il motore di ricerca non sa quale versione della pagina è per quale lingua, quindi può mostrare la pagina ucraina a un utente italiano o viceversa. Questo rovina l'esperienza e abbassa il ranking nella ricerca locale.",
        "en": "The search engine does not know which version of the page is for which language, so it may show the Ukrainian page to an Italian user or vice versa. This ruins the experience and lowers local search ranking.",
    },
    "a11y_hreflang_links_fix": {
        "uk": "Додайте у <head> посилання <link rel=\"alternate\" hreflang=\"uk\" href=\"...\" /> для кожної мовної версії. Також додайте hreflang=\"x-default\" для версії за замовчуванням.",
        "it": "Aggiungi nel <head> i link <link rel=\"alternate\" hreflang=\"uk\" href=\"...\" /> per ogni versione linguistica. Aggiungi anche hreflang=\"x-default\" per la versione predefinita.",
        "en": "Add to <head> links <link rel=\"alternate\" hreflang=\"uk\" href=\"...\" /> for each language version. Also add hreflang=\"x-default\" for the default version.",
    },
    "a11y_breadcrumb_markup_title": {
        "uk": "Хлібні крихти поза семантикою",
        "it": "Breadcrumb fuori dalla semantica",
        "en": "Breadcrumb outside semantic markup",
    },
    "a11y_breadcrumb_markup_found": {
        "uk": "Елемент з класом «breadcrumb» або «breadcrumbs» не обгорнутий у <nav>.",
        "it": "L'elemento con classe «breadcrumb» o «breadcrumbs» non è racchiuso in <nav>.",
        "en": "An element with class «breadcrumb» or «breadcrumbs» is not wrapped in <nav>.",
    },
    "a11y_breadcrumb_markup_why": {
        "uk": "Програма читання з екрана не розпізнає цей блок як навігацію, тому не пропонує його як landmark і не оголошує його призначення. Користувач бачить список посилань, але не знає що це шлях по сайту.",
        "it": "Lo screen reader non riconosce questo blocco come navigazione, quindi non lo offre come landmark e non ne annuncia lo scopo. L'utente vede un elenco di link ma non sa che è un percorso nel sito.",
        "en": "A screen reader does not recognise this block as navigation, so it does not offer it as a landmark and does not announce its purpose. The user sees a list of links but does not know it is a path through the site.",
    },
    "a11y_breadcrumb_markup_fix": {
        "uk": "Обгорніть хлібні крихти у <nav aria-label=\"breadcrumb\"> зі списком <ol>. Це не змінює вигляд, але дає програмі читання розуміння що це таке.",
        "it": "Racchiudi il breadcrumb in <nav aria-label=\"breadcrumb\"> con una lista <ol>. Non cambia l'aspetto ma dà allo screen reader la comprensione di cosa sia.",
        "en": "Wrap the breadcrumb in <nav aria-label=\"breadcrumb\"> with an <ol> list. This does not change the look but gives the screen reader understanding of what it is.",
    },
    "a11y_language_change_title": {
        "uk": "Іншомовний текст без атрибута мови",
        "it": "Testo in altra lingua senza attributo lingua",
        "en": "Foreign-language text without language attribute",
    },
    "a11y_language_change_found": {
        "uk": "Текст іншою мовою ({detected_script}) всередині сторінки мовою {page_lang} не має атрибута lang.",
        "it": "Testo in un'altra lingua ({detected_script}) dentro una pagina in {page_lang} non ha l'attributo lang.",
        "en": "Text in another language ({detected_script}) inside a {page_lang} page has no lang attribute.",
    },
    "a11y_language_change_why": {
        "uk": "Програма читання з екрана вимовляє іншомовний текст з вимовою мови сторінки. Українське слово «привіт» в англійській сторінці буде прочитане як набір англійських літер, і навпаки. Це робить текст незрозумілим.",
        "it": "Lo screen reader pronuncia il testo straniero con la pronuncia della lingua della pagina. La parola ucraina «привіт» in una pagina inglese verrà letta come un insieme di lettere inglesi, e viceversa. Questo rende il testo incomprensibile.",
        "en": "A screen reader pronounces foreign text with the page language's pronunciation. The Ukrainian word «привіт» in an English page will be read as a sequence of English letters, and vice versa. This makes the text unintelligible.",
    },
    "a11y_language_change_fix": {
        "uk": "Додайте до елемента з іншомовним текстом атрибут lang=\"{suggested_lang}\". Наприклад: <span lang=\"uk\">Привіт</span>.",
        "it": "Aggiungi all'elemento con il testo straniero l'attributo lang=\"{suggested_lang}\". Ad esempio: <span lang=\"uk\">Привіт</span>.",
        "en": "Add to the element with foreign text the attribute lang=\"{suggested_lang}\". For example: <span lang=\"uk\">Привіт</span>.",
    },
    "a11y_abbreviation_expansion_title": {
        "uk": "Абревіатура без розшифровки",
        "it": "Abbreviazione senza espansione",
        "en": "Abbreviation without expansion",
    },
    "a11y_abbreviation_expansion_found": {
        "uk": "Абревіатура «{abbreviation}» не обгорнута у <abbr> з атрибутом title.",
        "it": "L'abbreviazione «{abbreviation}» non è racchiusa in <abbr> con attributo title.",
        "en": "The abbreviation «{abbreviation}» is not wrapped in <abbr> with a title attribute.",
    },
    "a11y_abbreviation_expansion_why": {
        "uk": "Програма читання з екрана не може правильно вимовити абревіатуру без розшифровки. «WCAG» буде прочитане як «вкаг» або «дабл-ю-сі-е-джі», і жоден варіант не дає зрозуміти що це за стандарт.",
        "it": "Lo screen reader non può pronunciare correttamente un'abbreviazione senza espansione. «WCAG» verrà letto come «вкаг» o «doppio-vu-ci-a-gi», e nessuna delle due opzioni fa capire che standard sia.",
        "en": "A screen reader cannot pronounce an abbreviation correctly without expansion. «WCAG» will be read as «вкаг» or «double-u-see-ay-gee», and neither option makes clear what standard it is.",
    },
    "a11y_abbreviation_expansion_fix": {
        "uk": "Обгорніть абревіатуру у <abbr title=\"Повна назва\">{abbreviation}</abbr>. При першому використанні на сторінці краще написати повну назву з абревіатурою в дужках.",
        "it": "Racchiudi l'abbreviazione in <abbr title=\"Nome completo\">{abbreviation}</abbr>. Al primo uso nella pagina è meglio scrivere il nome completo con l'abbreviazione tra parentesi.",
        "en": "Wrap the abbreviation in <abbr title=\"Full name\">{abbreviation}</abbr>. On first use on the page it is better to write the full name with the abbreviation in parentheses.",
    },
    # --- нові правила performance (2026-08-20) ---
    "a11y_image_modern_format_title": {
        "uk": "Зображення у застарілому форматі",
        "it": "Immagine in formato obsoleto",
        "en": "Image in legacy format",
    },
    "a11y_image_modern_format_found": {
        "uk": "Зображення <img src=\"{src}\"> у форматі PNG/JPG без srcset.",
        "it": "L'immagine <img src=\"{src}\"> è in formato PNG/JPG senza srcset.",
        "en": "The image <img src=\"{src}\"> is in PNG/JPG format without srcset.",
    },
    "a11y_image_modern_format_why": {
        "uk": "WebP і AVIF стискають зображення на 25-50% краще за PNG/JPG при тій самій якості. Без srcset браузер не може обрати оптимальний розмір для пристрою, тому мобільний телефон завантажує зображення для десктопу.",
        "it": "WebP e AVIF comprimono le immagini del 25-50% meglio di PNG/JPG alla stessa qualità. Senza srcset il browser non può scegliere la dimensione ottimale per il dispositivo, quindi un telefono scarica l'immagine per desktop.",
        "en": "WebP and AVIF compress images 25-50% better than PNG/JPG at the same quality. Without srcset the browser cannot choose the optimal size for the device, so a phone downloads the desktop image.",
    },
    "a11y_image_modern_format_fix": {
        "uk": "Конвертуйте зображення у WebP або AVIF і додайте srcset з кількома розмірами. Сучасні інструменти збірки роблять це автоматично.",
        "it": "Converti le immagini in WebP o AVIF e aggiungi srcset con più dimensioni. Gli strumenti di build moderni lo fanno automaticamente.",
        "en": "Convert images to WebP or AVIF and add srcset with multiple sizes. Modern build tools do this automatically.",
    },
    "a11y_advisory": {
        "uk": "Дорадча ознака: жоден інструмент не вирішить це за вас. Чи це дефект, чи свідомий вибір, вирішує людина.",
        "it": "Segnale consultivo: nessuno strumento può deciderlo al posto tuo. Se sia un difetto o una scelta voluta lo decide una persona.",
        "en": "Advisory signal: no tool can settle this for you. Whether it is a defect or a deliberate choice is a person's call.",
    },
    "a11y_needs_browser": {
        "uk": "Часткова перевірка: без запуску браузера видно лише те, що є в самій розмітці. Решту треба звірити на живій сторінці.",
        "it": "Verifica parziale: senza eseguire un browser si vede solo ciò che è nel markup. Il resto va controllato sulla pagina reale.",
        "en": "Partial check: without running a browser only what is in the markup is visible. The rest needs checking on the live page.",
    },
    "a11y_rule_error": {
        "uk": "Правило {rule} впало на цьому документі",
        "it": "La regola {rule} è fallita su questo documento",
        "en": "Rule {rule} failed on this document",
    },
    "a11y_rule_error_title": {
        "uk": "Правило {rule} впало",
        "it": "La regola {rule} è fallita",
        "en": "Rule {rule} failed",
    },
    "a11y_summary": {
        "uk": "Критичних {critical}, серйозних {serious}, помірних {moderate}, дрібних {minor} на {documents} {documents_noun}",
        "it": "Critici {critical}, seri {serious}, moderati {moderate}, minori {minor} su {documents} {documents_noun}",
        "en": "{critical} critical, {serious} serious, {moderate} moderate, {minor} minor across {documents} {documents_noun}",
    },
    # The same sentence once something repeats: the headline is the number of
    # distinct problems, and the occurrences follow, so a header that sits on
    # every page is one job and not three hundred.
    "a11y_summary_distinct": {
        "uk": "Унікальних проблем {distinct}: критичних {critical}, серйозних {serious}, помірних {moderate}, дрібних {minor}. Усього знайдено {occurrences} разів на {documents} {documents_noun}",
        "it": "Problemi unici {distinct}: critici {critical}, seri {serious}, moderati {moderate}, minori {minor}. Trovati {occurrences} volte in tutto su {documents} {documents_noun}",
        "en": "{distinct} unique problems: {critical} critical, {serious} serious, {moderate} moderate, {minor} minor. Found {occurrences} times across {documents} {documents_noun}",
    },
    # Ownership. The count is said out loud rather than folded into the
    # summary: a person deciding what to do next needs to know that some of
    # what they are looking at is not theirs to change.
    "settings_view_logs": {"uk": "Переглянути логи", "it": "Vedi i log",
                           "en": "View logs"},
    "settings_clean_logs": {"uk": "Прибрати старі логи", "it": "Pulisci i log",
                            "en": "Clean up logs"},
    "settings_logs_note": {
        "uk": "Логи: {n} файл(ів), {mb} МБ, зберігаються {days} днів - {path}",
        "it": "Log: {n} file, {mb} MB, conservati {days} giorni - {path}",
        "en": "Logs: {n} file(s), {mb} MB, kept {days} days - {path}",
    },
    # The log screen (TUI) and the log panel (window). The CLI prints the
    # same records through `applog.format_line`.
    "tui_menu_logs": {"uk": "Логи", "it": "Log", "en": "Logs"},
    "tui_logs_title": {"uk": "Логи застосунку", "it": "Log dell'applicazione",
                       "en": "Application log"},
    "tui_logs_summary": {
        "uk": "{files} файл(ів), {mb} МБ, рівень {level}, зберігається {days} днів",
        "it": "{files} file, {mb} MB, livello {level}, conservati {days} giorni",
        "en": "{files} file(s), {mb} MB, level {level}, kept {days} days",
    },
    "tui_logs_errors": {"uk": "Лише помилки", "it": "Solo errori", "en": "Errors only"},
    "tui_logs_all": {"uk": "Усі", "it": "Tutti", "en": "All"},
    "tui_logs_hint": {
        "uk": "Тут видно, що прогін справді зробив: які сторінки прочитано, який рушій не запустився, яке правило впало.",
        "it": "Qui si vede cosa ha fatto davvero l'esecuzione: quali pagine sono state lette, quale motore non è partito, quale regola è fallita.",
        "en": "What the run actually did: which pages were read, which engine refused to start, which rule raised.",
    },
    "tui_logs_empty": {
        "uk": "Ще нічого не записано. Запустіть скан, або поставте XANALYZE_LOG_LEVEL=debug.",
        "it": "Non c'è ancora nulla. Avvia una scansione, o imposta XANALYZE_LOG_LEVEL=debug.",
        "en": "Nothing logged yet. Run a scan, or set XANALYZE_LOG_LEVEL=debug.",
    },
    "tui_col_level": {"uk": "Рівень", "it": "Livello", "en": "Level"},
    "tui_col_event": {"uk": "Подія", "it": "Evento", "en": "Event"},
    "tui_col_detail": {"uk": "Деталі", "it": "Dettagli", "en": "Detail"},
    "a11y_perf_image_oversized_title": {
        "uk": "Зображення більше, ніж потрібно будь-якому екрану",
        "it": "Immagine più grande di quanto serva a qualsiasi schermo",
        "en": "Image larger than any screen needs",
    },
    "a11y_perf_image_oversized_found": {
        "uk": "Файл має {width}x{height} пікселів, тоді як межа корисного розміру - {limit} у ширину.",
        "it": "Il file è {width}x{height} pixel, mentre il limite utile è {limit} di larghezza.",
        "en": "The file is {width}x{height} pixels, where the useful ceiling is {limit} wide.",
    },
    "a11y_perf_image_oversized_why": {
        "uk": "Браузер завантажує всі пікселі, а потім зменшує їх до розміру верстки. Відвідувач платить трафіком і часом за те, чого не побачить, і найбільше платить той, у кого зʼєднання найгірше.",
        "it": "Il browser scarica tutti i pixel e poi li rimpicciolisce alla dimensione del layout. Il visitatore paga in traffico e tempo per ciò che non vedrà, e paga di più chi ha la connessione peggiore.",
        "en": "The browser downloads every pixel and then shrinks them to the layout size. The visitor pays in bandwidth and time for what they will never see, and the one on the worst connection pays most.",
    },
    "a11y_perf_image_oversized_fix": {
        "uk": "Збережіть версію під реальну ширину показу і віддавайте кілька розмірів через srcset. Один файл на всі екрани означає, що телефон вантажить картинку для монітора.",
        "it": "Salva una versione alla larghezza reale di visualizzazione e servi più misure con srcset. Un solo file per tutti gli schermi significa che il telefono scarica l'immagine del monitor.",
        "en": "Save a version at the width it is actually displayed at, and serve several sizes through srcset. One file for every screen means the phone downloads the desktop picture.",
    },
    # Cross-page rules (`audit.crosspage`): what one document cannot show.
    "a11y_seo_duplicate_title_title": {
        "uk": "Однаковий <title> на кількох сторінках",
        "it": "Stesso <title> su più pagine",
        "en": "The same <title> on several pages",
    },
    "a11y_seo_duplicate_title_found": {
        "uk": '{count} сторінок мають однаковий заголовок "{value}".',
        "it": '{count} pagine hanno lo stesso titolo "{value}".',
        "en": '{count} pages carry the same title "{value}".',
    },
    "a11y_seo_duplicate_title_why": {
        "uk": "Заголовок є головним рядком у видачі й у вкладці браузера. Коли він однаковий, ані пошук, ані людина з десятьма вкладками не можуть відрізнити сторінки одну від одної.",
        "it": "Il titolo è la riga principale nei risultati di ricerca e nella scheda del browser. Se è identico, né il motore né una persona con dieci schede aperte distingue una pagina dall'altra.",
        "en": "The title is the headline in search results and in the browser tab. When it repeats, neither the engine nor a person with ten tabs open can tell the pages apart.",
    },
    "a11y_seo_duplicate_title_fix": {
        "uk": "Дайте кожній сторінці заголовок, що описує саме її, і лишіть назву сайту як суфікс.",
        "it": "Dai a ogni pagina un titolo che descriva quella pagina, tenendo il nome del sito come suffisso.",
        "en": "Give each page a title that describes that page, and keep the site name as a suffix.",
    },
    "a11y_seo_duplicate_description_title": {
        "uk": "Однаковий опис на кількох сторінках",
        "it": "Stessa description su più pagine",
        "en": "The same description on several pages",
    },
    "a11y_seo_duplicate_description_found": {
        "uk": '{count} сторінок мають однакову meta description "{value}".',
        "it": '{count} pagine hanno la stessa meta description "{value}".',
        "en": '{count} pages carry the same meta description "{value}".',
    },
    "a11y_seo_duplicate_description_why": {
        "uk": "Опис є текстом під заголовком у видачі. Один опис на весь сайт означає, що жодна сторінка не пояснює, чим вона відрізняється.",
        "it": "La description è il testo sotto il titolo nei risultati. Una sola description per tutto il sito significa che nessuna pagina spiega in cosa è diversa.",
        "en": "The description is the text under the headline in search results. One description across the site means no page explains what makes it different.",
    },
    "a11y_seo_duplicate_description_fix": {
        "uk": "Напишіть опис для кожної сторінки окремо, або приберіть шаблонний: відсутній опис пошук складе сам зі змісту сторінки.",
        "it": "Scrivi una description per ogni pagina, oppure togli quella generica: se manca, il motore la costruisce dal contenuto.",
        "en": "Write a description per page, or drop the boilerplate one: with none, the engine builds it from the page itself.",
    },
    "a11y_seo_duplicate_canonical_title": {
        "uk": "Кілька сторінок вказують на один canonical",
        "it": "Più pagine puntano allo stesso canonical",
        "en": "Several pages name the same canonical",
    },
    "a11y_seo_duplicate_canonical_found": {
        "uk": '{count} сторінок оголошують canonical "{value}".',
        "it": '{count} pagine dichiarano canonical "{value}".',
        "en": '{count} pages declare canonical "{value}".',
    },
    "a11y_seo_duplicate_canonical_why": {
        "uk": "Canonical каже пошуку: справжня адреса цієї сторінки інша. Коли його ставлять на кількох різних сторінках, кожна з них просить не індексувати себе - це не втрачена можливість, а прохання зникнути.",
        "it": "Il canonical dice al motore: l'indirizzo vero di questa pagina è un altro. Quando lo stesso valore è su pagine diverse, ognuna chiede di non essere indicizzata: non è un'occasione persa, è una richiesta di sparire.",
        "en": "A canonical tells the engine that the page's real address is elsewhere. When several different pages name the same one, each is asking not to be indexed - not a missed opportunity, a request to be dropped.",
    },
    "a11y_seo_duplicate_canonical_fix": {
        "uk": "Кожна сторінка має вказувати canonical на власну адресу. Один спільний canonical правильний лише для справжніх дублів - фільтрів, сортувань, UTM-міток.",
        "it": "Ogni pagina deve indicare come canonical il proprio indirizzo. Un canonical condiviso è corretto solo per duplicati veri: filtri, ordinamenti, parametri UTM.",
        "en": "Each page should name its own address as canonical. A shared canonical is right only for genuine duplicates - filters, sort orders, UTM parameters.",
    },
    "a11y_html_lang_contradicts_address_title": {
        "uk": "Оголошена мова суперечить самому сайту",
        "it": "La lingua dichiarata contraddice il sito stesso",
        "en": "The declared language contradicts the site itself",
    },
    "a11y_html_lang_contradicts_address_found": {
        "uk": 'Сторінка оголошує lang="{declared}", а сайт називає її мовою "{expected}" у {count} {places_noun}: {signals}.',
        "it": 'La pagina dichiara lang="{declared}", ma il sito la indica come "{expected}" in {count} {places_noun}: {signals}.',
        "en": 'The page declares lang="{declared}" while the site names it "{expected}" in {count} {places_noun}: {signals}.',
    },
    "a11y_html_lang_contradicts_address_why": {
        "uk": "Це не здогад про мову тексту, а розбіжність між тим, що сайт знає про сторінку, і тим, що вона декларує. Зазвичай означає атрибут, забутий в одному місці шаблону: адреса й og:locale уже правильні, а <html lang> лишився мовою за замовчуванням. Читач екрана довіряє атрибуту повністю, тому читає текст чужою фонетикою, а пошук отримує суперечливі сигнали про мовні версії.",
        "it": "Non è un'ipotesi sulla lingua del testo, ma una contraddizione fra ciò che il sito sa della pagina e ciò che la pagina dichiara. Di solito significa un attributo dimenticato in un punto solo del template: indirizzo e og:locale sono già corretti, mentre <html lang> è rimasto sulla lingua predefinita. Lo screen reader si fida completamente dell'attributo e legge il testo con la fonetica sbagliata, e i motori ricevono segnali contraddittori sulle versioni linguistiche.",
        "en": "This is not a guess about the language of the text but a contradiction between what the site knows about the page and what the page declares. It usually means an attribute forgotten in one place in the template: the address and og:locale are already right while <html lang> stayed on the default language. A screen reader trusts the attribute completely and reads the text with the wrong phonetics, and search engines get contradictory signals about the language versions.",
    },
    "a11y_html_lang_contradicts_address_fix": {
        "uk": 'Зробіть так, щоб <html lang> ішов за мовою запиту, а не був сталим: lang="{expected}" на цій сторінці. Якщо сайт багатомовний, атрибут має братись із того самого джерела, що й адреса та og:locale, тобто з поточної мови, а не бути записаним у шаблоні.',
        "it": 'Fai in modo che <html lang> segua la lingua della richiesta invece di restare fisso: lang="{expected}" su questa pagina. Se il sito è multilingue, l\'attributo deve venire dalla stessa fonte di indirizzo e og:locale, cioè dalla lingua corrente, e non essere scritto nel template.',
        "en": 'Make <html lang> follow the language of the request instead of staying fixed: lang="{expected}" on this page. On a multilingual site the attribute should come from the same source as the address and og:locale - the current language - rather than being written into the template.',
    },
    "a11y_html_lang_mismatch_title": {
        "uk": "Оголошена мова не збігається з текстом",
        "it": "La lingua dichiarata non è quella del testo",
        "en": "The declared language is not the one on the page",
    },
    "a11y_html_lang_mismatch_found": {
        "uk": 'Сторінка оголошує lang="{declared}", а текст написаний мовою "{detected}".',
        "it": 'La pagina dichiara lang="{declared}", ma il testo è in "{detected}".',
        "en": 'The page declares lang="{declared}" while the text is written in "{detected}".',
    },
    "a11y_html_lang_mismatch_why": {
        "uk": "Читач екрана довіряє атрибуту повністю: він перемикає голос і правила вимови за ним. Хибне оголошення читає текст чужою фонетикою і гірше за відсутній атрибут, бо без нього читач бере мову з налаштувань користувача.",
        "it": "Lo screen reader si fida completamente dell'attributo: cambia voce e regole di pronuncia in base a esso. Una dichiarazione sbagliata legge il testo con la fonetica di un'altra lingua ed è peggio di un attributo assente, perché senza di esso il lettore usa le impostazioni dell'utente.",
        "en": "A screen reader trusts the attribute completely: it switches voice and pronunciation rules on it. A wrong declaration reads the text with another language's phonetics, and that is worse than no attribute at all - with none, the reader falls back to the user's own setting.",
    },
    "a11y_html_lang_mismatch_fix": {
        "uk": 'Виправте атрибут на lang="{detected}", або, якщо сторінка справді змішана, лишіть основну мову в <html> і позначте вставки атрибутом lang на їхніх елементах.',
        "it": 'Correggi l\'attributo in lang="{detected}", oppure, se la pagina è davvero mista, lascia la lingua principale su <html> e marca gli inserti con lang sui loro elementi.',
        "en": 'Correct the attribute to lang="{detected}", or, if the page really is mixed, keep the main language on <html> and mark the passages with lang on their own elements.',
    },
    # Served-response rules (`audit.headers`). The bytes already arrived;
    # everything but Content-Type was being discarded.

    "a11y_sec_no_csp_title": {
        "uk": 'Немає Content-Security-Policy',
        "it": 'Nessuna Content-Security-Policy',
        "en": 'No Content-Security-Policy',
    },
    "a11y_sec_no_csp_found": {
        "uk": 'Відповідь не несе заголовка {header}, і в розмітці політики теж немає.',
        "it": "La risposta non porta l'header {header}, e nemmeno il markup contiene una policy.",
        "en": 'The response carries no {header} header, and the markup holds no policy either.',
    },
    "a11y_sec_no_csp_why": {
        "uk": 'CSP визначає, звідки сторінці дозволено вантажити скрипти й стилі. Без неї будь-який впроваджений скрипт - через коментар, віджет, скомпрометовану залежність - виконується з повними правами сторінки.',
        "it": 'La CSP dice da dove la pagina può caricare script e stili. Senza, qualsiasi script iniettato - da un commento, da un widget, da una dipendenza compromessa - gira con tutti i permessi della pagina.',
        "en": "A CSP says where the page may load scripts and styles from. Without one, any injected script - through a comment, a widget, a compromised dependency - runs with the page's full privileges.",
    },
    "a11y_sec_no_csp_fix": {
        "uk": 'Почніть з режиму звіту: Content-Security-Policy-Report-Only, зберіть порушення, потім вмикайте. Політика, зібрана на око, ламає сторінку.',
        "it": 'Parti in modalità report: Content-Security-Policy-Report-Only, raccogli le violazioni, poi attiva. Una policy scritta a occhio rompe la pagina.',
        "en": 'Start in report mode: Content-Security-Policy-Report-Only, collect the violations, then enforce. A policy written by guesswork breaks the page.',
    },
    "a11y_sec_no_hsts_title": {
        "uk": 'Немає Strict-Transport-Security',
        "it": 'Nessuna Strict-Transport-Security',
        "en": 'No Strict-Transport-Security',
    },
    "a11y_sec_no_hsts_found": {
        "uk": 'Сторінка віддається через HTTPS, але відповідь не несе {header}.',
        "it": 'La pagina è servita in HTTPS, ma la risposta non porta {header}.',
        "en": 'The page is served over HTTPS, but the response carries no {header}.',
    },
    "a11y_sec_no_hsts_why": {
        "uk": 'Без HSTS перший візит іде звичайним HTTP і його можна перехопити до редиректу. Заголовок каже браузеру більше ніколи не пробувати HTTP для цього домену.',
        "it": "Senza HSTS la prima visita passa da HTTP normale e può essere intercettata prima del redirect. L'header dice al browser di non provare mai più HTTP per questo dominio.",
        "en": 'Without HSTS the first visit goes over plain HTTP and can be intercepted before the redirect. The header tells the browser never to try HTTP for this domain again.',
    },
    "a11y_sec_no_hsts_fix": {
        "uk": 'Strict-Transport-Security: max-age=31536000; includeSubDomains. Спершу переконайтесь, що кожен піддомен уже на HTTPS.',
        "it": 'Strict-Transport-Security: max-age=31536000; includeSubDomains. Prima assicurati che ogni sottodominio sia già in HTTPS.',
        "en": 'Strict-Transport-Security: max-age=31536000; includeSubDomains. Make sure every subdomain is already on HTTPS first.',
    },
    "a11y_sec_no_nosniff_title": {
        "uk": 'Немає X-Content-Type-Options',
        "it": 'Nessun X-Content-Type-Options',
        "en": 'No X-Content-Type-Options',
    },
    "a11y_sec_no_nosniff_found": {
        "uk": 'Відповідь не несе заголовка {header}.',
        "it": "La risposta non porta l'header {header}.",
        "en": 'The response carries no {header} header.',
    },
    "a11y_sec_no_nosniff_why": {
        "uk": 'Без nosniff браузер може вгадати тип вмісту всупереч оголошеному. Завантажений користувачем файл, відданий як текст, тоді виконується як скрипт.',
        "it": "Senza nosniff il browser può indovinare il tipo di contenuto contro quello dichiarato. Un file caricato dall'utente e servito come testo finisce eseguito come script.",
        "en": 'Without nosniff a browser may guess the content type against the declared one. A user-uploaded file served as text then runs as a script.',
    },
    "a11y_sec_no_nosniff_fix": {
        "uk": 'X-Content-Type-Options: nosniff. Побічних ефектів у нього немає.',
        "it": 'X-Content-Type-Options: nosniff. Non ha effetti collaterali.',
        "en": 'X-Content-Type-Options: nosniff. It has no side effects.',
    },
    "a11y_sec_no_referrer_policy_title": {
        "uk": 'Немає Referrer-Policy',
        "it": 'Nessuna Referrer-Policy',
        "en": 'No Referrer-Policy',
    },
    "a11y_sec_no_referrer_policy_found": {
        "uk": 'Відповідь не несе заголовка {header}.',
        "it": "La risposta non porta l'header {header}.",
        "en": 'The response carries no {header} header.',
    },
    "a11y_sec_no_referrer_policy_why": {
        "uk": 'За замовчуванням браузер відправляє повну адресу сторінки кожному, на кого веде посилання. Адреса з токеном у запиті або зі шляхом внутрішньої сторінки їде разом із нею.',
        "it": "Per impostazione predefinita il browser invia l'indirizzo completo della pagina a chiunque venga linkato. Un URL con un token nella query o con il percorso di una pagina interna parte insieme.",
        "en": 'By default the browser sends the full page address to everything it links to. A URL with a token in the query, or the path of an internal page, travels with it.',
    },
    "a11y_sec_no_referrer_policy_fix": {
        "uk": 'Referrer-Policy: strict-origin-when-cross-origin. Свій домен бачить повний шлях, чужий - лише походження.',
        "it": "Referrer-Policy: strict-origin-when-cross-origin. Il tuo dominio vede il percorso completo, gli altri solo l'origine.",
        "en": 'Referrer-Policy: strict-origin-when-cross-origin. Your own domain sees the full path, everyone else only the origin.',
    },
    "a11y_sec_no_frame_options_title": {
        "uk": 'Сторінку можна вбудувати в чужий кадр',
        "it": 'La pagina può essere incorniciata da altri',
        "en": 'The page can be framed by anyone',
    },
    "a11y_sec_no_frame_options_found": {
        "uk": 'Немає ні {header}, ні frame-ancestors у CSP.',
        "it": "Non c'è né {header} né frame-ancestors nella CSP.",
        "en": 'There is neither {header} nor frame-ancestors in a CSP.',
    },
    "a11y_sec_no_frame_options_why": {
        "uk": 'Чужий сайт може відкрити цю сторінку в невидимому кадрі поверх власних кнопок, і клік користувача піде вашій сторінці. Це clickjacking.',
        "it": "Un sito terzo può aprire questa pagina in un frame invisibile sopra i propri pulsanti, e il clic dell'utente arriva alla tua pagina. È clickjacking.",
        "en": "Another site can open this page in an invisible frame over its own buttons, and the user's click lands on yours. That is clickjacking.",
    },
    "a11y_sec_no_frame_options_fix": {
        "uk": "X-Frame-Options: SAMEORIGIN, або frame-ancestors 'self' у CSP, якщо вона вже є.",
        "it": "X-Frame-Options: SAMEORIGIN, oppure frame-ancestors 'self' nella CSP se già esiste.",
        "en": "X-Frame-Options: SAMEORIGIN, or frame-ancestors 'self' in the CSP if you already have one.",
    },
    "a11y_perf_no_compression_title": {
        "uk": 'Відповідь без стиснення',
        "it": 'Risposta senza compressione',
        "en": 'Response served uncompressed',
    },
    "a11y_perf_no_compression_found": {
        "uk": 'Відповідь не несе {header}, тобто HTML їде як є.',
        "it": "La risposta non porta {header}: l'HTML viaggia così com'è.",
        "en": 'The response carries no {header}, so the HTML travels as it is.',
    },
    "a11y_perf_no_compression_why": {
        "uk": 'Розмітка стискається у 3-5 разів майже безкоштовно. Це найдешевше прискорення першого показу, яке взагалі існує, і воно вмикається на сервері, а не в коді.',
        "it": "Il markup si comprime di 3-5 volte quasi gratis. È l'accelerazione più economica del primo rendering che esista, e si attiva sul server, non nel codice.",
        "en": 'Markup compresses three to five times over for almost nothing. It is the cheapest first-paint win there is, and it is switched on at the server, not in the code.',
    },
    "a11y_perf_no_compression_fix": {
        "uk": 'Увімкніть gzip або brotli для text/html, text/css і application/javascript.',
        "it": 'Attiva gzip o brotli per text/html, text/css e application/javascript.',
        "en": 'Enable gzip or brotli for text/html, text/css and application/javascript.',
    },
    "a11y_perf_no_cache_header_title": {
        "uk": 'Немає Cache-Control',
        "it": 'Nessun Cache-Control',
        "en": 'No Cache-Control',
    },
    "a11y_perf_no_cache_header_found": {
        "uk": 'Відповідь не несе заголовка {header}.',
        "it": "La risposta non porta l'header {header}.",
        "en": 'The response carries no {header} header.',
    },
    "a11y_perf_no_cache_header_why": {
        "uk": 'Без нього кожен клієнт і кожен проміжний кеш вигадують строк життя самі. Повторний візит або тягне все наново, або показує старе - і ви не обрали, що саме.',
        "it": "Senza, ogni client e ogni cache intermedia inventano da soli la durata. Una seconda visita o riscarica tutto o mostra roba vecchia, e non l'hai deciso tu.",
        "en": 'Without it every client and every intermediate cache invents a lifetime of its own. A second visit either refetches everything or shows something stale, and you did not choose which.',
    },
    "a11y_perf_no_cache_header_fix": {
        "uk": 'Для HTML: Cache-Control: no-cache. Для статики з хешем в імені: max-age=31536000, immutable.',
        "it": "Per l'HTML: Cache-Control: no-cache. Per gli asset con hash nel nome: max-age=31536000, immutable.",
        "en": 'For HTML: Cache-Control: no-cache. For hashed static assets: max-age=31536000, immutable.',
    },
    "a11y_platform_owned": {
        "uk": "З них {count} у розмітці, яку генерує {platform}: власник сайту цього не редагує",
        "it": "Di questi {count} sono nel markup generato da {platform}: non è il proprietario del sito a modificarlo",
        "en": "{count} of these are in markup {platform} generates: not the site owner's to edit",
    },
    "a11y_owned_marker": {
        "uk": "розмітка {platform}",
        "it": "markup di {platform}",
        "en": "{platform} markup",
    },
    # --- що показувати з готового аудиту: категорії, певність, robots.txt ---
    #
    # Це не окремий прогін, а вигляд: правила дешеві й ділять один розбір,
    # тому вибір міняє список, а не запускає аудит наново.
    "setup_step_report": {
        "uk": "5 · Що показувати", "it": "5 · Cosa mostrare",
        "en": "5 · What to show",
    },
    "setup_report_categories": {
        "uk": "Категорії", "it": "Categorie", "en": "Categories",
    },
    "setup_report_categories_hint": {
        "uk": "Нічого не позначено - показуються всі шість.",
        "it": "Se non selezioni nulla, appaiono tutte e sei.",
        "en": "Nothing ticked means all six are shown.",
    },
    "setup_report_certainty": {
        "uk": "Певність", "it": "Certezza", "en": "Certainty",
    },
    "setup_report_certainty_hint": {
        "uk": "Поріг того, наскільки знахідка доведена. Прогін не змінюється - змінюється список.",
        "it": "La soglia di quanto un rilievo è dimostrato. La scansione non cambia: cambia l'elenco.",
        "en": "How settled a finding has to be. The run does not change; the list does.",
    },
    "certainty_any": {
        "uk": "будь-яка", "it": "qualsiasi", "en": "any",
    },
    "certainty_advisory": {
        "uk": "порада і вище", "it": "consultivo e oltre", "en": "advisory and up",
    },
    "certainty_needs-browser": {
        "uk": "потрібен браузер і вище", "it": "serve il browser e oltre",
        "en": "needs a browser and up",
    },
    "certainty_exact": {
        "uk": "лише точне", "it": "solo certo", "en": "settled only",
    },
    "setup_report_site_controls": {
        "uk": "Прочитати robots.txt і sitemap", "it": "Leggere robots.txt e sitemap",
        "en": "Read robots.txt and the sitemap",
    },
    "setup_report_site_controls_hint": {
        "uk": "Два додаткові запити до того самого домену. Тільки для сайту.",
        "it": "Due richieste in più allo stesso dominio. Solo per un sito.",
        "en": "Two extra requests to the same domain. Sites only.",
    },
    "tui_menu_account": {
        "uk": "Акаунт", "it": "Account", "en": "Account",
    },
    "tui_account_title": {
        "uk": "Акаунт xFormat", "it": "Account xFormat", "en": "xFormat account",
    },
    "tui_account_email": {"uk": "Пошта", "it": "Email", "en": "Email"},
    # The same literal in all three, and a key rather than a literal in the
    # screen anyway: it shows the *shape* of the value, an address is written
    # the same way in every language this app speaks, and a placeholder that
    # bypasses this table is a placeholder nobody notices when it should not.
    "tui_account_email_placeholder": {
        "uk": "you@example.com", "it": "you@example.com",
        "en": "you@example.com",
    },
    "tui_account_password": {"uk": "Пароль", "it": "Password", "en": "Password"},
    "tui_account_sign_out": {"uk": "Вийти", "it": "Esci", "en": "Sign out"},
    "tui_account_signed_in": {
        "uk": "Увійшли як {email}", "it": "Connesso come {email}",
        "en": "Signed in as {email}",
    },
    "tui_account_signed_out": {
        "uk": "Сесії немає.", "it": "Nessuna sessione.", "en": "No session.",
    },
    "tui_account_unknown": {
        "uk": "Не вдалося перевірити сесію: {detail}",
        "it": "Impossibile verificare la sessione: {detail}",
        "en": "Could not check the session: {detail}",
    },
    "tui_account_working": {
        "uk": "Входимо…", "it": "Accesso in corso…", "en": "Signing in…",
    },
    "tui_account_welcome": {
        "uk": "Готово.", "it": "Fatto.", "en": "Done.",
    },
    "tui_within_placeholder": {
        "uk": ".my-webpart", "it": ".my-webpart", "en": ".my-webpart",
    },
    "tui_no_session": {
        "uk": "Читати як сторонній (не використовувати збережений вхід)",
        "it": "Leggi come un estraneo (non usare l'accesso salvato)",
        "en": "Read as a stranger (do not use the stored sign-in)",
    },
    "tui_incremental_full": {
        "uk": "Інкрементно - перечитати лише змінені файли",
        "it": "Incrementale: rileggi solo i file modificati",
        "en": "Incremental - re-read only the files that changed",
    },
    "tui_label_medium": {"uk": "документи", "it": "documenti", "en": "documents"},
    "tui_medium_label": {
        "uk": "Тип вмісту",
        "it": "Tipo di contenuto",
        "en": "Content type",
    },
    "tui_medium_auto": {
        "uk": "визначити з файлу", "it": "rileva dal file", "en": "detect from the file",
    },
    "tui_account_use_xformat": {
        "uk": "Платити через xFormat", "it": "Paga tramite xFormat",
        "en": "Pay through xFormat",
    },
    "tui_account_now_xformat": {
        "uk": "Тепер за виклики моделі платить підписка xFormat.",
        "it": "Ora le chiamate al modello le paga l'abbonamento xFormat.",
        "en": "Model calls are now paid for by the xFormat subscription.",
    },
    "tui_account_welcome_switch": {
        "uk": "Вхід виконано. Зараз за виклики моделі платить інший провайдер - натисніть «Платити через xFormat», щоб перемкнути.",
        "it": "Accesso effettuato. Al momento le chiamate al modello le paga un altro provider: premi «Paga tramite xFormat» per cambiare.",
        "en": "Signed in. Model calls are currently paid for by another provider - press \"Pay through xFormat\" to switch.",
    },
    "tui_account_privacy": {
        "uk": "Пароль не зберігається: він обмінюється на токен, який лежить "
              "у keychain системи.",
        "it": "La password non viene salvata: viene scambiata con un token "
              "che risiede nel keychain di sistema.",
        "en": "The password is not stored: it is exchanged for a token that "
              "lives in the OS keychain.",
    },
    "tui_account_not_xformat": {
        "uk": "Обраний провайдер не xFormat - змініть його в Налаштуваннях.",
        "it": "Il provider scelto non è xFormat: cambialo in Impostazioni.",
        "en": "The chosen provider is not xFormat - change it in Settings.",
    },
    "tui_account_elsewhere_anthropic": {
        "uk": "Anthropic бере ключ, а не логін. Введіть його у вікні "
              "(зберігається в keychain) або задайте ANTHROPIC_API_KEY.",
        "it": "Anthropic usa una chiave, non un login. Inseriscila nella "
              "finestra (va nel keychain) o imposta ANTHROPIC_API_KEY.",
        "en": "Anthropic takes a key, not a login. Enter it in the window "
              "(it goes to the keychain) or set ANTHROPIC_API_KEY.",
    },
    "tui_account_elsewhere_claude-code": {
        "uk": "Claude Code керує власним входом: claude auth login",
        "it": "Claude Code gestisce il proprio accesso: claude auth login",
        "en": "Claude Code manages its own sign-in: claude auth login",
    },
    "setup_project_title": {
        "uk": "Профіль проєкту", "it": "Profilo del progetto",
        "en": "Project profile",
    },
    "setup_project_none": {
        "uk": "Стек не розпізнано - діють лише типові виключення.",
        "it": "Stack non riconosciuto: valgono solo le esclusioni predefinite.",
        "en": "No stack recognised - the default exclusions only.",
    },
    "setup_project_detected": {
        "uk": "Розпізнано: {stacks}", "it": "Rilevato: {stacks}",
        "en": "Detected: {stacks}",
    },
    "setup_project_excluded": {
        "uk": "Пропускається {count} шляхів як не ваш код: {patterns}",
        "it": "Saltati {count} percorsi perché non sono codice vostro: {patterns}",
        "en": "Skipping {count} path(s) as not your code: {patterns}",
    },
    # Why a run parameter switched itself on. One sentence each, printed
    # beside the control on both surfaces and on the CLI's own stderr: a
    # default that changes what the run does has to say who asked for it.
    # See `run_profile.RECIPES`.
    "why_web_parts": {
        "uk": "сторінка належить чужому сайту, а ваш - лише веб-парт: аудит "
              "звужується до того, що малюють ці частини",
        "it": "la pagina appartiene a un altro sito e vostra è solo la web "
              "part: l'audit si restringe a ciò che quelle parti disegnano",
        "en": "the page belongs to somebody else's site and only the web "
              "part is yours: the audit narrows to what those parts draw",
    },
    "why_render_sharepoint": {
        "uk": "сучасна сторінка SharePoint збирається в браузері: без "
              "рендеру читається порожнє полотно",
        "it": "una pagina moderna di SharePoint si compone nel browser: "
              "senza rendering si legge una tela vuota",
        "en": "a modern SharePoint page is assembled in the browser: "
              "without rendering the run reads an empty canvas",
    },
    "why_page_tree_sharepoint": {
        "uk": "сайт сам знає свої сторінки - це елементи бібліотеки; за "
              "посиланнями знайдеться лише те, на що послались",
        "it": "il sito conosce le proprie pagine, sono elementi di una "
              "raccolta: seguendo i link si trova solo ciò che è collegato",
        "en": "the site knows its own pages - they are library items; "
              "following links finds only what somebody linked to",
    },
    "why_site_scope_sharepoint": {
        "uk": "один хост обслуговує всі сайти тенанта, а прогін стосується "
              "одного з них",
        "it": "un solo host serve tutti i siti del tenant, e la scansione "
              "riguarda uno di essi",
        "en": "one host serves every site of the tenant, and the run is "
              "about one of them",
    },
    "why_sign_in_sharepoint": {
        "uk": "без збереженого входу SharePoint на кожну адресу відповідає "
              "сторінкою входу Microsoft: спершу увійдіть на сайт",
        "it": "senza un accesso salvato SharePoint risponde a ogni "
              "indirizzo con la pagina di accesso Microsoft: accedete prima "
              "al sito",
        "en": "without a stored sign-in SharePoint answers every address "
              "with Microsoft's sign-in page: sign in to the site first",
    },
    "why_devserver": {
        "uk": "без сервера з диска читаються шаблони, які збірка ще не "
              "виконала: `<App />` не є заголовком",
        "it": "senza server dal disco si leggono template che il bundler non "
              "ha ancora eseguito: `<App />` non è un'intestazione",
        "en": "read off disk this is templates the bundler has not run yet: "
              "`<App />` is not a heading",
    },
    "why_devserver_workspace": {
        "uk": "у корені монорепо є свій dev-скрипт, і в кожного застосунку "
              "під ним теж: запуститься саме кореневий - вкажіть проєкт, "
              "щоб запустити його власний",
        "it": "la radice del monorepo ha il proprio script dev, e ogni "
              "applicazione sotto di essa pure: partirà quello della radice "
              "- indicate un progetto per avviare il suo",
        "en": "the monorepo root has its own dev script and so does every "
              "application under it: the root's is what starts - name a "
              "project to start that project's instead",
    },
    "why_breakpoints_file": {
        "uk": "один документ нікуди не веде, тож лишається єдина вісь - "
              "ширина; переповнення 1.4.10 видно не на типовій",
        "it": "un solo documento non porta altrove: resta un unico asse, la "
              "larghezza, e l'overflow 1.4.10 non si vede su quella di default",
        "en": "one document leads nowhere else, so width is the only axis "
              "left - and 1.4.10 overflow is not visible at the default one",
    },
    "why_spfx_site_url": {
        "uk": "рішення SPFx знає, що віддає веб-парти, і не знає, куди: "
              "вкажіть сайт, на якому вони живуть",
        "it": "una soluzione SPFx sa di consegnare web part ma non dove: "
              "indicate il sito su cui vivono",
        "en": "an SPFx solution knows it ships web parts and cannot know "
              "where: name the site they live on",
    },
    # The sentence that wraps one of the above. `{evidence}` is the marker
    # file `project_profile` proved the stack with, so a wrong guess is
    # arguable rather than mysterious.
    "why_enabled": {
        "uk": "Увімкнено, бо {why}",
        "it": "Attivato perché {why}",
        "en": "Enabled, because {why}",
    },
    "setup_no_session": {
        "uk": "Читати як стороння людина",
        "it": "Leggere come un estraneo",
        "en": "Read it the way a stranger sees it",
    },
    "setup_no_session_hint": {
        "uk": "Ігнорує збережений вхід для цього хоста. Так видно, скільки "
              "сайту насправді за дверима.",
        "it": "Ignora l'accesso memorizzato per questo host. Così si vede "
              "quanta parte del sito è davvero dietro una porta.",
        "en": "Ignores the stored sign-in for this host - which is how you "
              "find out how much of the site is really behind a door.",
    },
    "setup_start_command": {
        "uk": "Команда запуску сервера (необовʼязково)",
        "it": "Comando di avvio del server (facoltativo)",
        "en": "Command that starts the server (optional)",
    },
    "setup_start_command_placeholder": {
        "uk": "npm run dev:site", "it": "npm run dev:site",
        "en": "npm run dev:site",
    },
    "setup_dev_port": {
        "uk": "Порт сервера", "it": "Porta del server", "en": "Server port",
    },
    "setup_dev_port_auto": {
        "uk": "визначити автоматично", "it": "rilevare automaticamente",
        "en": "work it out",
    },
    "setup_project_which": {
        "uk": "Який проєкт із теки аудитувати",
        "it": "Quale progetto della cartella analizzare",
        "en": "Which project in this folder to audit",
    },
    "setup_project_whole": {
        "uk": "уся тека", "it": "tutta la cartella", "en": "the whole folder",
    },
    "setup_web_parts": {
        "uk": "Лише веб-парти, які віддає цей репозиторій",
        "it": "Solo le web part che questo repository consegna",
        "en": "Only the web parts this repository ships",
    },
    "setup_projects_several": {
        "uk": "У теці {count} окремих проєкти ({names}). Зараз вони "
              "аудитуються як один - вкажіть один, щоб перевірити його окремо.",
        "it": "La cartella contiene {count} progetti distinti ({names}). Ora "
              "vengono analizzati come uno solo: indicatene uno per "
              "verificarlo da solo.",
        "en": "{count} separate projects in this folder ({names}). They are "
              "audited as one - name one of them to audit it on its own.",
    },
    "tui_site_url": {
        "uk": "Адреса сайту, куди це ставиться (необовʼязково)",
        "it": "Indirizzo del sito su cui viene pubblicato (facoltativo)",
        "en": "Address of the site this ships to (optional)",
    },
    "tui_site_url_placeholder": {
        "uk": "https://contoso.sharepoint.com/sites/intranet",
        "it": "https://contoso.sharepoint.com/sites/intranet",
        "en": "https://contoso.sharepoint.com/sites/intranet",
    },
    "tui_project_label": {
        "uk": "Який проєкт із теки", "it": "Quale progetto della cartella",
        "en": "Which project in this folder",
    },
    "tui_project_whole": {
        "uk": "уся тека", "it": "tutta la cartella", "en": "the whole folder",
    },
    "tui_projects_several": {
        "uk": "У теці {count} окремих проєкти ({names}). Зараз вони "
              "аудитуються як один - вкажіть один, щоб перевірити його окремо.",
        "it": "La cartella contiene {count} progetti distinti ({names}). "
              "Ora vengono analizzati come uno solo: indicatene uno per "
              "verificarlo da solo.",
        "en": "{count} separate projects in this folder ({names}). They are "
              "audited as one - name one of them to audit it on its own.",
    },
    "why_consider": {
        "uk": "Варто ввімкнути: {why}",
        "it": "Conviene attivare: {why}",
        "en": "Worth switching on: {why}",
    },
    "why_consider_stack": {
        "uk": "Варто ввімкнути: {why} ({stack}, доказ: {evidence})",
        "it": "Conviene attivare: {why} ({stack}, prova: {evidence})",
        "en": "Worth switching on: {why} ({stack}, evidence: {evidence})",
    },
    "why_enabled_stack": {
        "uk": "Увімкнено, бо {why} ({stack}, доказ: {evidence})",
        "it": "Attivato perché {why} ({stack}, prova: {evidence})",
        "en": "Enabled, because {why} ({stack}, evidence: {evidence})",
    },
    "setup_project_lift": {
        "uk": "Сканувати і їх теж",
        "it": "Analizzare anche quelli",
        "en": "Scan those as well",
    },
    "setup_project_lift_hint": {
        "uk": "Профіль - це доказ про власність, а не певність. Увімкніть, "
              "якщо виключений код насправді ваш.",
        "it": "Il profilo è una prova di proprietà, non una certezza. "
              "Attivalo se quel codice è davvero vostro.",
        "en": "A profile is evidence about ownership, not a certainty. Tick "
              "this when the excluded code is in fact yours.",
    },
    "setup_project_medium": {
        "uk": "Документи - це", "it": "Questi documenti sono",
        "en": "These documents are",
    },
    "setup_medium_auto": {
        "uk": "визначати з файлу", "it": "da rilevare dal file",
        "en": "read it off the file",
    },
    "setup_medium_web": {
        "uk": "сторінки для браузера", "it": "pagine per il browser",
        "en": "pages for a browser",
    },
    "setup_medium_email": {
        "uk": "листи для поштового клієнта",
        "it": "email per un client di posta",
        "en": "emails for a mail client",
    },
    "setup_project_medium_hint": {
        "uk": "Зазвичай видно з розмітки. Вкажіть вручну, якщо у листі немає "
              "ні просторів імен Outlook, ні merge-тегів: у листа немає ні "
              "canonical, ні Open Graph, ні skip-link.",
        "it": "Di solito si vede dal markup. Indicalo a mano se l'email non "
              "ha né namespace Outlook né merge tag: un'email non ha "
              "canonical, né Open Graph, né skip link.",
        "en": "Usually visible in the markup. Say it by hand when the email "
              "carries neither an Outlook namespace nor a merge tag: an email "
              "has no canonical URL, no Open Graph and no skip link.",
    },
    "audit_category_accessibility": {
        "uk": "Доступність", "it": "Accessibilità", "en": "Accessibility",
    },
    "audit_category_performance": {
        "uk": "Продуктивність", "it": "Prestazioni", "en": "Performance",
    },
    "audit_category_seo": {"uk": "SEO", "it": "SEO", "en": "SEO"},
    "audit_category_geo": {
        "uk": "GEO-готовність", "it": "Prontezza GEO", "en": "GEO readiness",
    },
    "audit_category_best-practices": {
        "uk": "Найкращі практики", "it": "Best practice", "en": "Best practices",
    },
    "audit_category_security": {"uk": "Безпека", "it": "Sicurezza", "en": "Security"},
    "empty_audit_filtered_title": {
        "uk": "Показувати нічого, але знайдено не нічого",
        "it": "Niente da mostrare, ma qualcosa è stato trovato",
        "en": "Nothing to show, but not nothing found",
    },
    "empty_audit_filtered_body": {
        "uk": "Аудит дав {total} знахідок, і жодна не проходить обраний фільтр категорій та певності. Розширте вибір - прогін для цього повторювати не треба.",
        "it": "L'audit ha prodotto {total} rilievi e nessuno passa il filtro di categoria e certezza scelto. Allarga la selezione: non serve rifare la scansione.",
        "en": "The audit produced {total} findings and none of them passes the chosen category and certainty filter. Widen it - the run does not have to be repeated.",
    },
    # --- становий прохід: подорож формою ------------------------------------
    "a11y_state:form_field_unnamed_title": {
        "uk": "Поле форми без назви", "it": "Campo del modulo senza nome",
        "en": "Form field with no name",
    },
    "a11y_state:form_field_unnamed_found": {
        "uk": "Після виконання скриптів поле не має ані підпису, ані aria-label, ані title.",
        "it": "Dopo l'esecuzione degli script il campo non ha né etichetta, né aria-label, né title.",
        "en": "After the scripts have run the field has no label, no aria-label and no title.",
    },
    "a11y_state:form_field_unnamed_why": {
        "uk": "Програма читання оголошує «поле введення» і замовкає. Людина чує, що щось треба вписати, і не чує що саме - а помилка у формі коштує не рядка, а всієї справи, по яку вона прийшла.",
        "it": "Lo screen reader annuncia «campo di testo» e tace. La persona sente che deve scrivere qualcosa ma non cosa - e un errore in un modulo non costa una riga, costa l'intera operazione per cui è arrivata.",
        "en": "A screen reader announces \"edit text\" and stops. The person hears that something goes here but not what - and a mistake in a form costs not a line but the whole errand they came to do.",
    },
    "a11y_state:form_field_unnamed_fix": {
        "uk": "Дайте полю <label for=\"...\"> з тим самим id, або aria-label, якщо підпис не має бути видимим.",
        "it": "Dai al campo una <label for=\"...\"> con lo stesso id, oppure aria-label se l'etichetta non deve vedersi.",
        "en": "Give the field a <label for=\"...\"> with the matching id, or aria-label where the name must not be visible.",
    },
    "a11y_state:form_placeholder_as_label_title": {
        "uk": "Замість підпису - лише placeholder",
        "it": "Al posto dell'etichetta solo un placeholder",
        "en": "A placeholder instead of a label",
    },
    "a11y_state:form_placeholder_as_label_found": {
        "uk": "Єдина назва поля - його placeholder: «{placeholder}».",
        "it": "L'unico nome del campo è il suo placeholder: «{placeholder}».",
        "en": "The only name the field has is its placeholder: \"{placeholder}\".",
    },
    "a11y_state:form_placeholder_as_label_why": {
        "uk": "Placeholder зникає з першим введеним символом. Людина, яка відволіклась або повернулась перевірити вписане, більше не бачить, що це за поле; сірий текст до того ж майже завжди не проходить контраст.",
        "it": "Il placeholder sparisce al primo carattere digitato. Chi si distrae o torna a rileggere quello che ha scritto non vede più di che campo si tratti; e quel grigio quasi mai passa il contrasto.",
        "en": "A placeholder disappears with the first character typed. Anyone who looks away, or comes back to check what they wrote, can no longer see which field this is - and that grey almost never passes contrast.",
    },
    "a11y_state:form_placeholder_as_label_fix": {
        "uk": "Перенесіть ці слова у <label>, а placeholder лишіть для прикладу формату або приберіть.",
        "it": "Sposta quelle parole in una <label> e lascia il placeholder per un esempio di formato, o toglilo.",
        "en": "Move those words into a <label>, and keep the placeholder for an example of the format - or drop it.",
    },
    "a11y_state:form_invalid_not_announced_title": {
        "uk": "Браузер вважає поле невірним, і про це ніхто не каже",
        "it": "Il browser considera il campo non valido e nessuno lo dice",
        "en": "The browser calls the field invalid and nothing says so",
    },
    "a11y_state:form_invalid_not_announced_found": {
        "uk": "Поле не проходить власну перевірку браузера ({reason}), але не має aria-invalid=\"true\".",
        "it": "Il campo non supera la validazione del browser ({reason}) ma non ha aria-invalid=\"true\".",
        "en": "The field fails the browser's own validation ({reason}) but carries no aria-invalid=\"true\".",
    },
    "a11y_state:form_invalid_not_announced_why": {
        "uk": "Стан «невірно» існує лише візуально. Програма читання оголошує поле звичайним, тож людина дізнається про проблему хіба що після невдалої відправки - і без підказки, яке саме поле винне.",
        "it": "Lo stato «non valido» esiste solo visivamente. Lo screen reader annuncia un campo normale, quindi la persona lo scopre al massimo dopo un invio fallito, senza sapere quale campo sia.",
        "en": "The invalid state exists only visually. A screen reader announces an ordinary field, so the person finds out after a failed submit at best, with nothing saying which field it was.",
    },
    "a11y_state:form_invalid_not_announced_fix": {
        "uk": "Проставляйте aria-invalid=\"true\" разом із візуальною позначкою і знімайте його, коли значення виправлено.",
        "it": "Imposta aria-invalid=\"true\" insieme al segnale visivo e rimuovilo quando il valore è corretto.",
        "en": "Set aria-invalid=\"true\" alongside the visual marking, and remove it once the value is corrected.",
    },
    "a11y_state:form_error_not_associated_title": {
        "uk": "Повідомлення про помилку ні з чим не звʼязане",
        "it": "Il messaggio di errore non è collegato a nulla",
        "en": "The error message is attached to nothing",
    },
    "a11y_state:form_error_not_associated_found": {
        "uk": "На екрані є текст помилки - «{message}» - і жодне поле не посилається на нього через aria-describedby чи aria-errormessage.",
        "it": "Sullo schermo c'è un testo di errore - «{message}» - e nessun campo lo richiama con aria-describedby o aria-errormessage.",
        "en": "There is error text on screen - \"{message}\" - and no field refers to it through aria-describedby or aria-errormessage.",
    },
    "a11y_state:form_error_not_associated_why": {
        "uk": "Червоний рядок під полем бачить лише той, хто дивиться. Для програми читання його немає: людина знає, що форма не пройшла, і не знає чому.",
        "it": "La riga rossa sotto il campo la vede solo chi guarda. Per lo screen reader non esiste: la persona sa che il modulo non è passato, ma non perché.",
        "en": "A red line under a field is only there for someone looking at it. To a screen reader it does not exist: the person knows the form failed and not why.",
    },
    "a11y_state:form_error_not_associated_fix": {
        "uk": "Дайте повідомленню id і вкажіть його в aria-describedby (або aria-errormessage) поля, якого воно стосується.",
        "it": "Dai un id al messaggio e indicalo in aria-describedby (o aria-errormessage) del campo a cui si riferisce.",
        "en": "Give the message an id and name it in the aria-describedby (or aria-errormessage) of the field it is about.",
    },
    "setup_report_unsettled": {
        "uk": "Показувати й те, що не вдалося визначити",
        "it": "Mostrare anche ciò che non si è potuto stabilire",
        "en": "Also list what could not be decided",
    },
    "setup_report_unsettled_hint": {
        "uk": "Рушій каже «елемент на фоновому зображенні, перевірте вручну». Типово це не показується: на одній сторінці таких було 312 із 348 знахідок про контраст.",
        "it": "Il motore dice «elemento su un'immagine di sfondo, da verificare a mano». Di norma non si mostra: su una sola pagina erano 312 rilievi su 348 sul contrasto.",
        "en": "An engine saying \"this element is on a background image, check by hand\". Out by default: on one page that was 312 of 348 contrast findings.",
    },
    "tui_unsettled": {
        "uk": "Показувати й невизначене",
        "it": "Mostrare anche l'indeciso",
        "en": "Also list the undecided",
    },
    "audit_unsettled_hidden": {
        "uk": "{count} перевірок не вдалося вирішити - вони не в списку",
        "it": "{count} controlli non si sono potuti risolvere: non sono in elenco",
        "en": "{count} checks could not be decided and are not listed",
    },
    "diagnosis_saturated_rule_title": {
        "uk": "Правило спрацювало майже на всьому",
        "it": "Una regola è scattata quasi su tutto",
        "en": "A rule fired on nearly everything",
    },
    "diagnosis_saturated_rule_body": {
        "uk": "{rule} дало {findings} знахідок на {elements} оглянутих елементах. Така частка означає, що правило міряє себе, а не сторінку: воно заповнює список і виштовхує з нього все інше. Решта знахідок від цього не стає менш правдивою, але цю купу варто читати останньою.",
        "it": "{rule} ha prodotto {findings} rilievi su {elements} elementi esaminati. Una quota simile significa che la regola misura sé stessa e non la pagina: riempie l'elenco e spinge fuori tutto il resto. Gli altri rilievi non diventano meno veri, ma questo mucchio va letto per ultimo.",
        "en": "{rule} produced {findings} findings on {elements} elements examined. At that share the rule is measuring itself rather than the page: it fills the list and pushes everything else off it. The other findings are no less true for it, but this pile is the one to read last.",
    },
    "audit_agreement": {
        "uk": "{n} рушії згодні", "it": "{n} motori d'accordo",
        "en": "{n} engines agree",
    },
    "tui_label_certainty": {"uk": "певність", "it": "certezza", "en": "certainty"},
    "tui_all_categories": {"uk": "усі шість", "it": "tutte e sei", "en": "all six"},
    "tui_site_controls": {
        "uk": "Прочитати robots.txt і sitemap того самого домену",
        "it": "Leggere robots.txt e la sitemap dello stesso dominio",
        "en": "Read robots.txt and the same-domain sitemap",
    },
    # Said before a run, about depth rather than failure: what this run is
    # not going to reach, and which switch reaches it. The CLI has printed
    # these since `cli_impl/prerun.py`; the window said nothing at all.
    "diagnosis_auth_wall_title": {
        "uk": "Частина адрес відповіла формою входу",
        "it": "Alcuni indirizzi hanno risposto con una schermata di accesso",
        "en": "Some addresses answered with a login wall",
    },
    "diagnosis_auth_wall_body": {
        "uk": "{blocked} із {pages} прочитаних адрес - це вхід, а не сторінка ({signals}). Те, що стоїть за ними, цей прогін не читав, тож знахідки на цих адресах стосуються форми входу, а не застосунку за нею.",
        "it": "{blocked} indirizzi su {pages} letti sono un accesso, non una pagina ({signals}). Ciò che sta dietro non è stato letto da questa scansione, quindi i rilievi su quegli indirizzi riguardano il modulo di accesso, non l'applicazione dietro di esso.",
        "en": "{blocked} of the {pages} addresses read are a login, not a page ({signals}). What stands behind them was not read by this run, so findings at those addresses are about the sign-in form and not about the application behind it.",
    },
    "diagnosis_auth_wall_whole_title": {
        "uk": "Прочитано лише вхід - сайт не аудитувався",
        "it": "È stato letto solo l'accesso: il sito non è stato analizzato",
        "en": "Only the login was read - the site was not audited",
    },
    "diagnosis_auth_wall_whole_body": {
        "uk": "Усі {pages} адрес, які цей прогін прочитав, виявились формою входу ({signals}). Підсумок нижче стосується сторінки входу, і чистий результат тут не означає, що із сайтом усе гаразд. Увійдіть у сайт або вкажіть публічну адресу.",
        "it": "Tutti i {pages} indirizzi letti da questa scansione sono risultati una schermata di accesso ({signals}). Il riepilogo qui sotto riguarda la pagina di accesso, e un risultato pulito non significa che il sito stia bene. Accedi al sito oppure indica un indirizzo pubblico.",
        "en": "Every one of the {pages} addresses this run read turned out to be a login ({signals}). The summary below is about the sign-in page, and a clean result here does not mean the site is fine. Sign in to the site, or point the run at a public address.",
    },
    "diagnosis_missed_repo_title": {
        "uk": "Знахідки назвуть сторінку, а не файл",
        "it": "I rilievi indicheranno la pagina, non il file",
        "en": "Findings will name the page, not the file",
    },
    "diagnosis_missed_repo_body": {
        "uk": "Тека з кодом цього сайту не вказана, тож знайдений уривок матиме адресу сторінки і не матиме файла й рядка, де його написано. Вкажіть код за сайтом - і кожен уривок, який є в теці, отримає точне місце.",
        "it": "Non è indicata la cartella con il codice di questo sito, quindi un passaggio trovato avrà l'indirizzo della pagina e non il file e la riga in cui è scritto. Indica il codice dietro il sito e ogni passaggio presente nella cartella riceverà la sua posizione esatta.",
        "en": "No checkout was given for this site, so a passage that is found carries the page address and not the file and line where it is written. Point at the code behind the site and every passage that exists there gets an exact place.",
    },
    "diagnosis_missed_devserver_title": {
        "uk": "Проєкт міг би показати себе браузеру",
        "it": "Il progetto potrebbe mostrarsi a un browser",
        "en": "The project could serve itself to a browser",
    },
    "diagnosis_missed_devserver_body": {
        "uk": "Це схоже на проєкт {stack}, тобто він уміє запустити власний сервер. Прочитаний як вихідний код, він не проходить правила, яким потрібна намальована сторінка: контраст, порядок фокуса, розкладка на ширині та всі вимірювання.",
        "it": "Sembra un progetto {stack}, quindi può avviare un proprio server. Letto come codice sorgente, non passa le regole che richiedono una pagina renderizzata: contrasto, ordine del focus, layout a una certa larghezza e tutte le misurazioni.",
        "en": "This looks like a {stack} project, so it can serve itself. Read as source, it does not run the rules that need a rendered page: contrast, focus order, layout at a width, and every measurement.",
    },
    "diagnosis_missed_browser_title": {
        "uk": "Це лише статичне читання",
        "it": "Questa è solo la lettura statica",
        "en": "This is the static reading only",
    },
    "diagnosis_missed_browser_body": {
        "uk": "Браузер вимкнено, тож axe, HTML_CodeSniffer, станові правила і вимірювання не виконуються. Тиха відповідь тут не є тією самою відповіддю, яку дав би прогін із браузером.",
        "it": "Il browser è disattivato, quindi axe, HTML_CodeSniffer, le regole sugli stati e le misurazioni non vengono eseguite. Un risultato silenzioso qui non è la stessa risposta che darebbe una scansione con il browser.",
        "en": "The browser is off, so axe, HTML_CodeSniffer, the state rules and the measurements do not run. A quiet result here is not the answer a rendered run would give.",
    },
    "diagnosis_missed_breakpoints_title": {
        "uk": "Аудитується лише ширина робочого столу",
        "it": "Viene controllata solo la larghezza desktop",
        "en": "Only the desktop width is audited",
    },
    "diagnosis_missed_breakpoints_body": {
        "uk": "Планшет, мобільний і перевірка перекомпонування на 320 px не виконуються, а саме там живуть відмови адаптивної верстки.",
        "it": "Tablet, mobile e il controllo di reflow a 320 px non vengono eseguiti, ed è proprio lì che stanno i cedimenti del layout responsive.",
        "en": "Tablet, mobile and the 320 px reflow check do not run, and that is where responsive failures live.",
    },
    "diagnosis_pair_repo": {
        "uk": "Вказати код за сайтом",
        "it": "Indica il codice dietro il sito",
        "en": "Point at the code behind the site",
    },
    "diagnosis_all_breakpoints": {
        "uk": "Перевірити всі ширини",
        "it": "Controlla tutte le larghezze",
        "en": "Check every width",
    },
    "settings_max_files": {
        "uk": "Максимум файлів у теці",
        "it": "Numero massimo di file nella cartella",
        "en": "Most files in a folder",
    },
    "settings_max_files_note": {
        "uk": "Скільки файлів прогін відкриє в теці, перш ніж зупинитись. Великий монорепозиторій упирається в цю межу, і прогін про це каже - але змінити її досі можна було лише в командному рядку.",
        "it": "Quanti file una scansione apre in una cartella prima di fermarsi. Un monorepo grande raggiunge questo limite e la scansione lo dichiara, ma finora si poteva cambiarlo solo da riga di comando.",
        "en": "How many files a run opens in a folder before it stops. A large monorepo reaches this limit and the run says so - but until now the number could only be changed from the command line.",
    },
    "settings_sessions": {
        "uk": "Збережені сесії сайтів ({count}): {hosts}. Зберігається лише те, що сайт видав браузеру; ці значення не потрапляють ані у звіт, ані в журнал.",
        "it": "Sessioni di siti salvate ({count}): {hosts}. Viene conservato solo ciò che il sito ha dato al browser; quei valori non finiscono né nei report né nei log.",
        "en": "Stored site sessions ({count}): {hosts}. Only what the site gave the browser is kept, and those values never reach a report or a log.",
    },
    "settings_sessions_none": {
        "uk": "Збережених сесій сайтів немає. «Увійти на сайт» у вікні відкриває справжній браузер, щоб ви увійшли самі.",
        "it": "Nessuna sessione di sito salvata. «Accedi al sito» nella finestra apre un vero browser perché tu acceda di persona.",
        "en": "No stored site sessions. \"Sign in to the site\" in the window opens a real browser so you can sign in yourself.",
    },
    "settings_forget_sessions": {
        "uk": "Забути всі сесії", "it": "Dimentica tutte le sessioni",
        "en": "Forget every session",
    },
    "settings_forget_sessions_confirm": {
        "uk": "Видалити збережені сесії для: {hosts}? Наступний прогін цих сайтів читатиме їх так, як бачить сторонній.",
        "it": "Rimuovere le sessioni salvate per: {hosts}? La prossima scansione leggerà quei siti come li vede un estraneo.",
        "en": "Remove the stored sessions for: {hosts}? The next run reads those sites the way a stranger sees them.",
    },
    "compare_widths": {
        "uk": "Дві ширини поруч", "it": "Due larghezze affiancate",
        "en": "Two widths side by side",
    },
    "compare_widths_full": {
        "uk": "Показує сторінку водночас на найширшій і найвужчій із перевірених ширин. Перемикач вище й далі керує лівою панеллю, тож будь-яку ширину можна поставити проти 320 px - саме там живуть відмови адаптивної верстки.",
        "it": "Mostra la pagina contemporaneamente alla larghezza più ampia e a quella più stretta tra quelle controllate. Il selettore sopra continua a comandare il pannello di sinistra, così puoi confrontare qualsiasi larghezza con i 320 px, dove stanno i cedimenti del layout responsive.",
        "en": "Shows the page at the widest and the narrowest audited width at once. The switcher above still drives the left-hand pane, so any width can be put against 320 px - which is where responsive failures live.",
    },
    "compare_widths_caption": {
        "uk": "{width} px", "it": "{width} px", "en": "{width} px",
    },
    "sign_in_site_button": {
        "uk": "Увійти на сайт", "it": "Accedi al sito", "en": "Sign in to the site",
    },
    "sign_in_site_change": {
        "uk": "Сесія є - змінити", "it": "Sessione presente - cambia",
        "en": "Signed in - change",
    },
    "sign_in_site_full": {
        "uk": "Відкриває справжнє вікно браузера на цій адресі, щоб ви увійшли самі. Прогін після цього читатиме сайт як ви. Інструмент не бачить ні логіна, ні пароля.",
        "it": "Apre una vera finestra del browser su questo indirizzo perché tu acceda di persona. Dopo, la scansione leggerà il sito come te. Lo strumento non vede né nome utente né password.",
        "en": "Opens a real browser window on this address so you can sign in yourself. The run then reads the site as you. The tool sees neither your username nor your password.",
    },
    "sign_in_site_have": {
        "uk": "Для {host} на цій машині збережено сесію. Натисніть, щоб увійти знову або видалити її.",
        "it": "Per {host} è salvata una sessione su questa macchina. Premi per accedere di nuovo o per rimuoverla.",
        "en": "A session for {host} is stored on this machine. Press to sign in again or to remove it.",
    },
    "sign_in_site_needs_url": {
        "uk": "Спочатку вкажіть адресу сайту, на який треба увійти.",
        "it": "Indica prima l'indirizzo del sito a cui accedere.",
        "en": "Give the address of the site to sign in to first.",
    },
    "sign_in_site_title": {
        "uk": "Вхід на {host}",
        "it": "Accesso a {host}",
        "en": "Sign in to {host}",
    },
    "sign_in_site_note": {
        "uk": "Це справжнє вікно браузера на {host}. Увійдіть так, як звикли - разом із 2FA, SSO чи капчею. Інструмент не бачить ні логіна, ні пароля: він збереже лише те, що сайт видав цьому браузеру, і використає це в наступному прогоні. Натисніть «Готово», коли опинитесь усередині.",
        "it": "Questa è una vera finestra del browser su {host}. Accedi come fai di solito, anche con 2FA, SSO o captcha. Lo strumento non vede né nome utente né password: conserverà solo ciò che il sito ha dato a questo browser e lo userà nella prossima scansione. Premi «Fatto» quando sei dentro.",
        "en": "This is a real browser window on {host}. Sign in the way you normally do - including 2FA, SSO or a captcha. The tool sees neither your username nor your password: it keeps only what the site gave this browser, and uses that on the next run. Press \"Done\" once you are inside.",
    },
    "sign_in_site_incomplete": {
        "uk": "Вхід на {host} ще не завершено: SharePoint не видав цьому вікну сесію. Відкрийте в цьому вікні будь-яку сторінку сайту, дочекайтеся, поки вона завантажиться, і знову натисніть «Готово». Нічого не збережено.",
        "it": "L'accesso a {host} non è ancora completo: SharePoint non ha dato a questa finestra la sessione. Apri in questa finestra una pagina qualsiasi del sito, attendi che si carichi e premi di nuovo «Fatto». Non è stato salvato nulla.",
        "en": "Signing in to {host} is not complete yet: SharePoint has not given this window its session. Open any page of the site in this window, wait for it to load, then press \"Done\" again. Nothing was saved.",
    },
    "sign_in_site_checking": {
        "uk": "Перевіряю, чи сесія для {host} уже є…",
        "it": "Verifico se la sessione per {host} è già presente…",
        "en": "Checking whether the session for {host} is there yet…",
    },
    "sign_in_site_elsewhere": {
        "uk": "{target} не належить до входу на {host}, тому відкрито в системному браузері. У цьому вікні лишаються лише сайт і вхід.",
        "it": "{target} non fa parte dell'accesso a {host}, quindi è stato aperto nel browser di sistema. In questa finestra restano solo il sito e l'accesso.",
        "en": "{target} is not part of signing in to {host}, so it was opened in the system browser. This window stays on the site and its sign-in.",
    },
    "sign_in_site_on_idp": {
        "uk": "Завершіть вхід у цьому вікні. «Готово» стане доступною, коли сторінка повернеться на {host}.",
        "it": "Completa l'accesso in questa finestra. «Fatto» sarà disponibile quando la pagina tornerà su {host}.",
        "en": "Finish signing in in this window. \"Done\" becomes available once the page is back on {host}.",
    },
    "sign_in_site_back": {
        "uk": "Ви знову на {host}. Якщо бачите сайт, а не форму входу, натисніть «Готово».",
        "it": "Sei di nuovo su {host}. Se vedi il sito e non il modulo di accesso, premi «Fatto».",
        "en": "You are back on {host}. If you see the site rather than a sign-in form, press \"Done\".",
    },
    "sign_in_site_required": {
        "uk": "{host} - це SharePoint Online без збереженого входу. Натисніть «Увійти на сайт», увійдіть самі, і прогін прочитає весь сайт як ви.",
        "it": "{host} è SharePoint Online senza un accesso salvato. Premi «Accedi al sito», accedi di persona e la scansione leggerà tutto il sito come te.",
        "en": "{host} is SharePoint Online with no stored sign-in. Press \"Sign in to the site\", sign in yourself, and the run reads the whole site as you.",
    },
    "sharepoint_tree_reading": {
        "uk": "Читаю дерево сторінок SharePoint на {host}...",
        "it": "Lettura dell'albero delle pagine SharePoint su {host}...",
        "en": "Reading the SharePoint page tree on {host}...",
    },
    "tui_sharepoint_login": {
        "uk": "{host} - SharePoint Online, а збереженого входу немає: кожна адреса відповість сторінкою входу Microsoft. Спершу увійдіть: {command}",
        "it": "{host} è SharePoint Online e non c'è un accesso salvato: ogni indirizzo risponderà con la pagina di accesso Microsoft. Accedete prima: {command}",
        "en": "{host} is SharePoint Online with no stored sign-in: every address would answer with Microsoft's sign-in page. Sign in first: {command}",
    },
    "sign_in_site_done": {"uk": "Готово", "it": "Fatto", "en": "Done"},
    "sign_in_site_forget": {
        "uk": "Забути цю сесію", "it": "Dimentica questa sessione",
        "en": "Forget this session",
    },
    "sign_in_site_saved": {
        "uk": "Сесію для {host} збережено ({count} значень). Її вміст не потрапляє ні у звіт, ні в журнал.",
        "it": "Sessione per {host} salvata ({count} valori). Il contenuto non finisce né nel report né nei log.",
        "en": "The session for {host} is saved ({count} values). Its contents never reach a report or a log.",
    },
    "sign_in_site_forgotten": {
        "uk": "Сесію для {host} видалено з цієї машини.",
        "it": "La sessione per {host} è stata rimossa da questa macchina.",
        "en": "The session for {host} has been removed from this machine.",
    },
    "sign_in_site_active": {
        "uk": "Прогін виконано у сесії, у яку ви увійшли самі ({host}).",
        "it": "Scansione eseguita nella sessione a cui hai effettuato l'accesso ({host}).",
        "en": "This run used the session you signed in to yourself ({host}).",
    },
    "finding_written_in": {
        "uk": "Точний текст знайдено у {path}:{line}",
        "it": "Testo esatto trovato in {path}:{line}",
        "en": "Exact text found in {path}:{line}",
    },
    "source_mapping_exact_unique": {
        "uk": "Точний текст знайдено в одному місці вихідного коду.",
        "it": "Il testo esatto è presente in un solo punto del codice sorgente.",
        "en": "The exact text occurs at one source location.",
    },
    "source_mapping_ambiguous": {
        "uk": "Текст є в кількох місцях. Джерело неоднозначне; потрібен ручний вибір.",
        "it": "Il testo compare in più punti. L'origine è ambigua; serve una scelta manuale.",
        "en": "The text occurs at several locations. Its source is ambiguous; choose manually.",
    },
    "source_mapping_inferred": {
        "uk": "Є схожий текст після нормалізації. Привʼязка припущена; автоматична правка недоступна.",
        "it": "Testo simile dopo la normalizzazione. L'origine è dedotta; correzione automatica non disponibile.",
        "en": "Similar text after normalization. The mapping is inferred; automatic correction is unavailable.",
    },
    "paired_repo_placeholder": {
        "uk": "код за цим сайтом (не обовʼязково)",
        "it": "codice dietro questo sito (facoltativo)",
        "en": "the code behind this site (optional)",
    },
    "paired_repo_full": {
        "uk": "Тека з кодом, який обслуговує цей сайт. Знахідка в тексті отримає файл і рядок, де цей уривок написано, а не лише адресу сторінки. Порожньо - звичайний прогін.",
        "it": "La cartella con il codice che serve questo sito. Un rilievo nel testo riceverà il file e la riga in cui il passaggio è scritto, non solo l'indirizzo della pagina. Vuoto: scansione normale.",
        "en": "The checkout that serves this site. A text finding then carries the file and line where the passage is written, not just the page address. Empty is an ordinary run.",
    },
    "within_placeholder": {
        "uk": "лише ця частина сторінки, напр. .my-webpart",
        "it": "solo questa parte della pagina, es. .my-webpart",
        "en": "only this part of the page, e.g. .my-webpart",
    },
    "within_full": {
        "uk": "CSS-селектор частини сторінки, яку ви віддали замовнику: веб-частина, віджет, вбудований блок. Решта документа належить комусь іншому, і сторінкові правила до фрагмента не застосовуються. Якщо селектор нічого не знайшов, прогін скаже про це, а не поверне порожній результат.",
        "it": "Selettore CSS della parte di pagina che hai consegnato: una web part, un widget, un blocco incorporato. Il resto del documento è di qualcun altro e le regole di pagina non si applicano a un frammento. Se il selettore non trova nulla, la scansione lo dice invece di restituire un risultato vuoto.",
        "en": "A CSS selector for the part of the page you delivered: a web part, a widget, an embedded block. The rest of the document belongs to somebody else, and page-level rules do not apply to a fragment. A selector that matches nothing is reported, not returned as an empty result.",
    },
    "paired_repo_matched": {
        "uk": "Код за сайтом: {matched} із {total} уривків знайдено у теці.",
        "it": "Codice dietro il sito: {matched} passaggi su {total} trovati nella cartella.",
        "en": "The code behind the site: {matched} of {total} passages found in the checkout.",
    },
    "paired_repo_none": {
        "uk": "Код за сайтом: жоден із {total} уривків не знайдено у вибраній теці. Найімовірніше, це не той чекаут - або текст приходить із CMS.",
        "it": "Codice dietro il sito: nessuno dei {total} passaggi è stato trovato nella cartella scelta. Probabilmente non è quel checkout, oppure il testo arriva da un CMS.",
        "en": "The code behind the site: none of the {total} passages were found in the chosen folder. Most likely it is the wrong checkout - or the text comes from a CMS.",
    },
    "word_yes": {"uk": "так", "it": "sì", "en": "yes"},
    "word_no": {"uk": "ні", "it": "no", "en": "no"},
    # The window edge a focused element was scrolled to, as an adjective that
    # agrees with "edge" in the sentence that uses it (`focus-obscured`).
    "word_edge_top": {"uk": "верхнього", "it": "superiore", "en": "top"},
    "word_edge_bottom": {"uk": "нижнього", "it": "inferiore", "en": "bottom"},
    "severity_critical": {"uk": "критично", "it": "critico", "en": "critical"},
    "severity_serious": {"uk": "серйозно", "it": "serio", "en": "serious"},
    "severity_moderate": {"uk": "помірно", "it": "moderato", "en": "moderate"},
    "severity_minor": {"uk": "дрібно", "it": "minore", "en": "minor"},
    "tui_subtitle": {
        "uk": "v{version} · аналізатор тексту й доступності",
        "it": "v{version} · analizzatore di testo e accessibilità",
        "en": "v{version} · AI text & accessibility analyzer",
    },
    "tui_yes": {"uk": "Так", "it": "Sì", "en": "Yes"},
    "tui_no": {"uk": "Ні", "it": "No", "en": "No"},
    "tui_sum_target": {"uk": "ціль", "it": "obiettivo", "en": "target"},
    "tui_sum_by": {"uk": "за {detector}", "it": "per {detector}",
                    "en": "by {detector}"},
    "tui_sum_audit_severity": {
        "uk": "аудит · {severity}", "it": "audit · {severity}",
        "en": "audit {severity}",
    },
    "tui_sum_critical": {"uk": "критично", "it": "critico", "en": "critical"},
    "tui_sum_serious": {"uk": "серйозно", "it": "serio", "en": "serious"},
    "tui_sum_moderate": {"uk": "помірно", "it": "moderato", "en": "moderate"},
    "tui_sum_minor": {"uk": "незначно", "it": "minore", "en": "minor"},
    "tui_log_level_debug": {"uk": "налагодження", "it": "debug", "en": "debug"},
    "tui_log_level_info": {"uk": "інформація", "it": "info", "en": "info"},
    "tui_log_level_warning": {"uk": "попередження", "it": "avviso", "en": "warning"},
    "tui_log_level_error": {"uk": "помилка", "it": "errore", "en": "error"},
    "tui_log_event_audit_web_done": {
        "uk": "вебаудит завершено", "it": "audit web completato",
        "en": "web audit completed",
    },
    "tui_log_event_browser_engine_error": {
        "uk": "помилка браузерного рушія", "it": "errore del motore browser",
        "en": "browser engine error",
    },
    "tui_log_event_browser_skipped": {
        "uk": "браузерну перевірку пропущено", "it": "controllo browser saltato",
        "en": "browser check skipped",
    },
    "tui_log_event_command_done": {
        "uk": "команду завершено", "it": "comando completato",
        "en": "command completed",
    },
    "tui_log_event_command_failed": {
        "uk": "команда завершилася помилкою", "it": "comando non riuscito",
        "en": "command failed",
    },
    "tui_log_event_command_start": {
        "uk": "команду запущено", "it": "comando avviato",
        "en": "command started",
    },
    "tui_log_event_crawl_page": {
        "uk": "сторінку оброблено", "it": "pagina elaborata",
        "en": "page processed",
    },
    "tui_log_event_crawl_page_failed": {
        "uk": "не вдалося обробити сторінку", "it": "pagina non elaborata",
        "en": "page processing failed",
    },
    "tui_log_event_pairing_failed": {
        "uk": "не вдалося зіставити репозиторій", "it": "abbinamento repository non riuscito",
        "en": "repository pairing failed",
    },
    "tui_log_event_rule_raised": {
        "uk": "помилка правила аудиту", "it": "errore della regola di audit",
        "en": "audit rule error",
    },
    "tui_detector_heuristic": {
        "uk": "евристичний аналіз", "it": "analisi euristica",
        "en": "heuristic analysis",
    },
    "tui_detector_unicode_anomalies": {
        "uk": "аномалії Unicode", "it": "anomalie Unicode",
        "en": "Unicode anomalies",
    },
    "tui_detector_claude": {"uk": "Claude", "it": "Claude", "en": "Claude"},
    "tui_detector_claude_code": {
        "uk": "Claude Code", "it": "Claude Code", "en": "Claude Code",
    },
    "tui_detector_xformat": {"uk": "xFormat", "it": "xFormat", "en": "xFormat"},
    "tui_uninstall_item_command": {
        "uk": "{path} (командний файл у PATH)",
        "it": "{path} (comando nel PATH)",
        "en": "{path} (command on PATH)",
    },
    "tui_uninstall_item_app": {
        "uk": "{path} (застосунок)", "it": "{path} (applicazione)",
        "en": "{path} (application)",
    },
    "tui_uninstall_item_config": {
        "uk": "{path} (налаштування й кеш сканування)",
        "it": "{path} (impostazioni e cache delle scansioni)",
        "en": "{path} (settings and scan cache)",
    },
    "tui_uninstall_item_legacy_config": {
        "uk": "{path} (налаштування старої версії)",
        "it": "{path} (impostazioni della versione precedente)",
        "en": "{path} (previous-version settings)",
    },
    "tui_uninstall_item_keychain": {
        "uk": "Запис у Зв’язці ключів: {service} / {account}",
        "it": "Voce nel Portachiavi: {service} / {account}",
        "en": "Keychain entry: {service} / {account}",
    },
    "tui_uninstall_reports_left": {
        "uk": "Залишаться теки звітів ({n}) у {path}",
        "it": "Rimarranno {n} cartelle di report in {path}",
        "en": "{n} report folders will remain in {path}",
    },
    "tui_uninstall_old_reports_left": {
        "uk": "Залишаться старі звіти ({n}) на Робочому столі",
        "it": "Rimarranno {n} report precedenti sulla Scrivania",
        "en": "{n} older reports will remain on the Desktop",
    },
    "tui_uninstall_history_kept": {
        "uk": ".xanalyze/ та .xanalyze-ignore у ваших репозиторіях залишаться без змін",
        "it": ".xanalyze/ e .xanalyze-ignore nei repository resteranno invariati",
        "en": ".xanalyze/ history and .xanalyze-ignore files in repositories stay untouched",
    },
}


def t(key: str, lang: str = "uk", **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry.get("en") or key
    return template.format(**kwargs) if kwargs else template


def plural(n: int, lang: str, one: str, few: str, many: str | None = None) -> str:
    """The noun form that agrees with `n`, in whichever of the three
    languages the interface is showing.

    Ukrainian needs all three forms - "1 документ", "2 документи",
    "5 документів" - and the well-known exception that 11-14 take the
    "many" form even though they end in 1-4 (`11 документів`, not
    `11 документ`). Italian and English only distinguish one from the rest,
    so `few` is what they use whenever `n != 1`; `many` exists only for the
    languages that need a third form; a caller that also has no need for a
    third form (a case where "few" and "many" are the same word, such as
    `на 2 документах` and `на 5 документах`) can simply pass the same string
    as both, and the entire calculation still runs.
    """
    if lang != "uk":
        return one if n == 1 else few
    many = many if many is not None else few
    if n % 100 in (11, 12, 13, 14):
        return many
    if n % 10 == 1:
        return one
    if n % 10 in (2, 3, 4):
        return few
    return many
