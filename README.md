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
  Сартыроўка: прыярытэтныя ↑ → потым ад новых да старых
        ↓
  Захаванне ў docs/feed.xml → commit + push
```

Гатовы XML даступны праз **GitHub Pages** па адрасе:
`https://<user>.github.io/<repo>/feed.xml`

---

## Наладка

### 1. Дазволіць Actions рабіць push

`Settings → Actions → General → Workflow permissions → Read and write permissions ✓`


### 2. Дадаць Secrets

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Апісанне | Прыклад |
|---|---|---|
| `RSS_FEEDS` | URL фідаў — адзін на радок або праз коску | `https://example.com/rss`<br>`https://news.ycombinator.com/rss` |
| `PRIORITY_TOPICS` | Ключавыя словы для прыярытэту (праз коску або новы радок) | `AI, машыннае навучанне, Python` |
| `BLACKLIST_TOPICS` | Ключавыя словы для выключэння | `рэклама, спонсар, sponsored` |
| `OUTPUT_TITLE` | Назва выніковага фіда | `Мой зборны RSS` |
| `OUTPUT_DESCRIPTION` | Апісанне фіда | `Аб'яднаны RSS` |
| `OUTPUT_LINK` | Спасылка фіда (URL вашых Pages) | `https://user.github.io/repo/feed.xml` |
| `MAX_ITEMS` | Максімальная колькасць запісаў (змоўч. 200) | `300` |

> **Абавязковы** толькі `RSS_FEEDS`. Астатнія — апцыянальныя.

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
