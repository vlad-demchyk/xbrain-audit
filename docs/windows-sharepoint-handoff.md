# Windows і аудит SharePoint-сайту: контекст роботи

Документ передачі контексту для гілки `feat/windows-sharepoint`. Його мета: продовжити роботу на
іншому пристрої без втрати рішень. Репозиторій публічний, тому тут **немає** реальних
ідентифікаторів замовника: URL тенанта, назв сайтів, tenant id. Цільовий сайт передається окремо,
поза репозиторієм. Приклади нижче використовують `https://contoso.sharepoint.com/sites/ExampleSite`.

Гілку створено від `refactor/mvvm-state-machine` 0.72.3 (на 2026-11-11 вона збігалась з
`origin/main` і `origin/HEAD`).

## Технічне завдання

1. Перейти на актуальну гілку останньої розробки.
2. Підтримка роботи у Windows.
3. Конфігурація і детекція SharePoint: задаємо URL сайту, відкривається вікно авторизації, людина
   сама входить (Microsoft 365 / Entra ID, можливо MFA), після чого аналізатор працює коректно.
4. Мапа аналізу: частину сторінки, яку додає Microsoft, пропускати (на неї немає впливу);
   аудитувати кастомні SPFx-компоненти і контент, який додає автор.
5. Розширити можливості, виправити помилки, кросперевірка.
6. Живий аудит на тестовому сайті замовника.
7. Дерево сторінок: зібрати всі сторінки сайту і проаналізувати весь сайт.
8. Звіт, коміт в окрему гілку, push.

## Ухвалені рішення

**Зони сторінки** (замовник погодив):

| Зона | Що входить | Що робимо |
|---|---|---|
| `microsoft` | suite bar, app bar, хедер сайту і hub-навігація, командна панель, коментарі, футер платформи, обгортки поза канвасом | не аудитуємо, рахуємо як пропущене |
| `custom` | SPFx web parts (GUID з manifest репозиторія, коли є `--repo`, або `webPartId` поза переліком OOTB Microsoft), application customizer placeholders | аудитуємо все, підписуємо назвою part |
| `author` | Text web part, заголовок і банер сторінки, OOTB web parts (Image, Quick links, Hero, News) | для OOTB лише контентні правила: alt, текст посилань, заголовки, мова, кольори в rich text, AI-текст, медіа. Структурні та ARIA-знахідки в розмітці Microsoft відносяться до Microsoft і рахуються як пропущені |

- **Класифікація без репозиторія.** Сайт може не мати репозиторію SPFx. Основний сигнал: атрибути
  DOM. Перелік GUID OOTB не вигадуємо з памʼяті, а поповнюємо з живого DOM.
- **Обсяг обходу.** Лише заданий сайт і його підсайти. Інші site collections тенанта відкидаються.
- **Документи з бібліотек** (PDF, DOCX) потрапляють в інвентар, їхній вміст поки не аудитується.
- **Ніяких паролів.** Вхід робить людина у вікні. Для краулера зберігаються лише cookies
  `*.sharepoint.com` цільового тенанта, без `login.microsoftonline.com`.

## Що виявила розвідка коду (до змін)

- `crawler.py`: таймаут рендера через `signal.SIGALRM`, якого немає на Windows. Помилка
  перехоплювалась, тож рендер JS-сторінок на Windows тихо не працював.
- `audit/authwall.py`: не впізнавав редирект на `login.microsoftonline.com/<tid>/oauth2/authorize`,
  бо там нестандартний шлях і закодовані ключі `redirect%5Furi`. Також лише слабким сигналом
  читав `403` з `X-Forms_Based_Auth_Required`. Без сесії сторінка входу Microsoft аудитувалась би
  як сайт.
- `ui/site_sign_in.py`: збирає cookies усіх доменів, разом з `ESTSAUTH*` від
  `login.microsoftonline.com`.
- `run_profile.py`: SharePoint розпізнавався лише з `--repo` на SPFx. Режиму «SharePoint-сайт за
  URL» не було.
- `crawler.crawl`: BFS лише за `<a href>`, без REST, без обмеження по шляху, без `Retry-After`.
- Браузерний прохід (axe) ігнорував `--web-parts` і сканував усю сторінку.
- Вхід є в GUI і в `cli.py login`, у TUI немає.

## Пакети робіт

| Пакет | Файли | Суть |
|---|---|---|
| Windows | `platform_dirs.py`, `config.py`, `cli.py`, `app_entry.py`, `applog.py`, `scan_cache.py`, `uninstaller.py`, `llm/credentials.py`, `packaging/XAnalyze-windows.spec`, `scripts/build_windows.ps1`, таймаут рендера в `crawler.py` | середовище, тести, платформні шляхи, збірка, README x3 |
| B. Зони | новий `audit/sharepoint_zones.py`, `audit/engine.py`, `audit/within.py`, `audit/browser.py`, `report/*`, `cli_impl/reports.py`, `finding_contract.py` | класифікатор зон, усі екземпляри part, include/exclude для axe, поле `zone` у звіті |
| C. Дерево | новий `sharepoint_tree.py` | REST: `_api/web`, `GetList('<web>/SitePages')` з пагінацією, підсайти, навігація, пошук, 429 з повтором, детекція «потрібен вхід» |
| A. Вхід і детекція | `audit/authwall.py`, `site_session.py`, `ui/site_sign_in.py`, `project_profile.py`, `run_profile.py` | IdP-редиректи, фільтр cookies, стек `sharepoint` за хостом |
| D. Інтеграція | `cli.py`, `cli_impl/auditpass.py`, `ui/*`, TUI, `i18n`, README x3, `config.APP_VERSION` | режим SharePoint наскрізно, seed-список із дерева в краулер, прокрутка для лінивих web parts |

Порядок: Windows, B і C паралельно; далі A (після звільнення `site_session.py`) і інтеграція
`sharepoint_tree` у `crawler.py`; потім D; потім живий аудит.

## Відкриті ризики

- Conditional Access тенанта може заблокувати вхід через QtWebEngine (не Edge). Перевіряється
  першим кроком живого входу.
- Селектори зон і GUID OOTB web parts не звірені з живим DOM. Після входу треба зняти дамп
  сторінки і `CanvasContent1` і уточнити класифікатор.
- FedAuth спливає. Браузер перелогінюється тихо, а requests ні. Потрібне чесне повідомлення
  «сесія спливла».
- Великий сайт: рендер SharePoint займає кілька секунд на сторінку. Потрібні бюджет і лічильник
  «не дійшли».

## Як продовжити на іншому пристрої

```bash
git fetch origin
git switch feat/windows-sharepoint
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/
```

Стан пакетів і результати живого аудиту дописуються в розділ нижче при кожному коміті гілки.

## Поточний стан

- 2026-11-11: розвідка завершена; пакети Windows, B і C у роботі.
- 2026-11-11, проміжний коміт (WIP, щоб не втратити роботу):
  - **Готово і перевірено:** Windows (pytest 3430 passed, лишились 2 відомі падіння:
    `test_render_activity` і `test_claims_match_coverage`), B (зони), C (дерево сторінок, з
    виправленнями кросперевірки), A (вхід і детекція).
  - **Живий вхід** на тестовий сайт через `cli.py login` пройшов: Conditional Access вбудований
    браузер не заблокував, сесію збережено.
  - **У роботі на момент коміту**, файли можуть бути незавершені:
    - D1: CLI-конвеєр (`crawler.py` seeds/site_scope, `cli.py` прапорці `--page-tree`,
      `--site-scope`, `--ootb-registry`, `cli_impl/auditpass.py`);
    - D2: прокрутка лінивих web parts у `audit/driver.py`, GUI, TUI, i18n, README, 0.73.0;
    - чистка назв клієнтів з коментарів і корпусу;
    - звірка селекторів зон із живим DOM.
  - **Далі:** завершити D1/D2, уточнити `sharepoint_zones.py` за живим DOM, повний аудит сайту,
    звіт.
