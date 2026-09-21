# Product glossary data

JSON files that tell Stash which category an everyday item, brand or merchant
belongs to (`dahi` -> Groceries, `pgvcl` -> Bills, `fafda` -> Snacks ...).
The matching engine is `app/glossary/engine.py`; the ask-the-user learning
loop is `app/services/category_learning.py`. See ARCHITECTURE.md for how it
plugs into the chat pipeline.

```
data/
  expense/   one file per expense category (groceries.json, snacks.json, ...)
  income/    one file per income source   (salary.json, freelance.json, ...)
```

## File format

```json
{
  "category": "Groceries",
  "type": "expense",
  "description": "one line on what belongs here",
  "groups": {
    "dairy": ["dahi", "curd", "paneer", "..."],
    "vegetables": ["aloo", "pyaz", "..."]
  }
}
```

- `category` must be one of the app's categories (`CATEGORIES_EXPENSE` /
  `CATEGORIES_INCOME` in `app/ai/prompts.py`). No new categories are created
  by the glossary.
- `groups` are only labels for humans (and for the "why was this categorized"
  explanation) - put terms wherever they read best.
- Terms are case-insensitive, accent-insensitive and matched on whole words.
  Hindi / Gujarati script terms are fine.
- You do NOT need to list plurals: `biscuit` also matches `biscuits`
  (last word only; `mango` -> `mangoes`, `berry` -> `berries`).
- Multi-word terms win over the words inside them, so `milk tea` -> Tea even
  though `milk` -> Groceries, and `dahi vada` -> Snacks even though `dahi`
  -> Groceries.
- Listing an item under **Other** means "known, deliberately uncategorised" -
  Stash will not ask the user about it.

## Conventions used for the 13 expense categories

| Category | What goes here |
| --- | --- |
| Groceries | Kirana/supermarket staples, dairy, produce, raw meat/fish, packaged pantry items, household & personal-care consumables (soap, detergent, sanitary pads), quick-commerce apps |
| Snacks | Street food, packaged snacks, mithai/sweets, ice cream, bakery, chocolates, cold drinks and juices |
| Tea | Tea/coffee as a drink (tapri, cafes, coffee chains). Tea/coffee *powder* is Groceries |
| Food | Cooked meals: restaurants, thali, tiffin/mess, delivery apps, fast-food chains, everyday Indian dishes |
| Petrol | Fuel, EV charging, and vehicle running costs (service, tyres, puncture, car wash) |
| Shopping | Clothes, footwear, jewellery, gadgets, appliances, furniture, cosmetics, gifts, toys, sports gear, hardware, e-commerce/brand stores |
| Bills | Electricity, water, LPG cylinder, internet, recharge, DTH, rent, EMI, insurance, subscriptions/OTT, household help, bank fees, gym |
| Travel | Cabs/autos/buses/trains/flights, hotels & stays, tolls, parking, tours |
| Entertainment | Movies, events (garba passes), parties/nightlife, alcohol, games, amusement parks, hobbies |
| Medical | Medicines, doctors, hospitals, lab tests, dental, eye care, supplements |
| Education | School/college fees, tuition/coaching, online courses, exams, books, stationery |
| Investment | SIP/stocks/brokers, FD/RD/PPF/NPS, gold & silver as an asset, crypto, property, chit funds |
| Other | Charity/religious offerings, tips, tobacco, salon/spa, courier, fines |

Where the old hard-coded keyword hints in `app/ai/extractor.py` already
decided a placement (Netflix -> Bills, gold -> Investment, books ->
Education ...) the glossary follows the same decision, so behaviour doesn't
flip.

## Avoid

- Very generic single words (`order`, `ticket`, `fee`, `gram`, `fair`): they
  collide with too many contexts. The old hint tables still handle a few of
  these as a fallback.
- The same term in two categories - the validator rejects it. If a word is
  genuinely ambiguous (`apple`: fruit vs phone), list only the unambiguous
  phrases (`apple watch`) and let the LLM / the ask-the-user flow handle the
  bare word.

## Checking your change

```bash
python3 scripts/validate_glossary.py   # also runs in CI
```

It fails on malformed JSON, unknown categories, wrong folder, and terms that
appear under two categories. To try a lookup by hand:

```python
from app.glossary import lookup
lookup("spent on dahi", "expense")   # Resolution(category='Groceries', term='dahi', ...)
```

## Where the terms came from

Curated by hand for Indian everyday spending (English, Hinglish, and
Hindi/Gujarati script), cross-checked against public taxonomies: the
COICOP 2018 consumption classification used by India's CPI (MoSPI), and
Wikipedia's *List of snack foods from the Indian subcontinent*. It is a
starting point, not an exhaustive scrape - items that are missing are
handled at runtime by the ask-the-user flow, which saves each user's answer
in the `user_glossary` table. To promote commonly-taught terms into these
files, look at that table (`SELECT term, category_or_source, COUNT(*) FROM
user_glossary GROUP BY 1, 2 ORDER BY 3 DESC`) and add them here.
