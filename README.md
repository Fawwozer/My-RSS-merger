# RSS Feed Merger — GitHub Actions

Аўтаматычна аб'ядноўвае некалькі RSS-стужак у адну, з падтрымкай прыярытэтных тэм, чорнага спісу і выдаленнем дублікатаў.

## Як гэта працуе

```
Кожныя 30 хвілін (або ўручную)
        ↓
  Загрузка ўсіх RSS з secrets
        ↓
  Фільтрацыя чорнага спісу
        ↓
  Выдаленне дублікатаў (па GUID / URL / загалоўку)
        ↓
  Выдаленне запісаў старэй за MAX_AGE_DAYS
        ↓
  Сартыроўка: прыярытэтныя ↑ → потым ад новых да старых
        ↓
  Захаванне ў docs/feed.xml → commit + push
```
---

## Наладка

### 1. Дадаць Secrets and variables

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Апісанне | Прыклад |
|---|---|---|
| `RSS_FEEDS` | URL фідаў — адзін на радок або праз коску | `https://example.com/rss`<br>`https://news.ycombinator.com/rss` |
| `PRIORITY_TOPICS` | Ключавыя словы для прыярытэту (праз коску або новы радок) | `AI, машыннае навучанне, Python` |
| `BLACKLIST_TOPICS` | Ключавыя словы для выключэння | `рэклама, спонсар, sponsored` |
| `OUTPUT_TITLE` | Назва выніковага фіда | `Мой зборны RSS` |
| `OUTPUT_DESCRIPTION` | Апісанне фіда | `Аб'яднаны RSS` |
| `OUTPUT_LINK` | Спасылка фіда (URL вашых Pages) | `https://user.github.io/repo/feed.xml` |
| `MAX_ITEMS` | Максімальная колькасць запісаў (змоўч. 300) | `100` |
| `MAX_AGE_DAYS` | Выдаляць запісы старэй за N дзён (0 = не выдаляць, змоўч. 30) | `14` |

> **Абавязковы** толькі `RSS_FEEDS`. Астатнія — апцыянальныя.

### 3. Дазволіць Actions рабіць push

`Settings → Actions → General → Workflow permissions → Read and write permissions ✓`

---

## Структура праекта

```
.
├── .github/
│   └── workflows/
│       └── merge-rss.yml      # GitHub Actions workflow
├── scripts/
│   └── merge_rss.py           # Скрыпт зліцця
├── docs/
│   └── feed.xml               # Выніковы фід (аўта-генеруецца)
└── README.md
```

---

## Логіка прыярытэтаў

1. **Чорны спіс** — запісы з ключавымі словамі з `BLACKLIST_TOPICS` выдаляюцца цалкам.
2. **Прыярытэт** — запісы з ключавымі словамі з `PRIORITY_TOPICS` атрымліваюць балы (адзін бал за кожнае супадзенне).
3. **Сартыроўка**: спачатку прыярытэтныя (ад большага балу да меншага), затым усе астатнія — у абодвух групах ад новых да старых.

---

## Ручны запуск

`Actions → Merge RSS Feeds → Run workflow`

---

## Змена расклада

У файле `.github/workflows/merge-rss.yml` адрэдагуйце радок `cron`:

```yaml
- cron: '*/30 * * * *'   # кожныя 30 хвілін
- cron: '0 * * * *'      # кожную гадзіну
- cron: '0 */6 * * *'    # кожныя 6 гадзін
```
