"""Cuisine classifier: maps source cuisine labels + free text onto one canonical set.

Order matters in CANON (it's the chip order in the UI). A single offer can carry
several cuisines (e.g. a Pakistani place that also sells burgers).
"""
import re

# canonical cuisine -> (source labels that map to it, keyword regex over names/captions)
CANON = {
    "Pakistani":     ({"pakistani"}, r"\b(karahi|kadai|nihari|haleem|chapli|sajji|lahori|peshawari|paya|seekh|chargha|halwa puri|pakistani|desi)\b"),
    "Indian":        ({"indian", "north indian", "south indian", "kerala", "indian sweets"}, r"\b(dosa|idli|vada|thali|masala|paneer|butter chicken|tandoori|naan|kerala|malabar|parotta|porotta|indian|chaat|samosa)\b"),
    "Biryani":       ({"biryani"}, r"\b(biryani|biriyani|pulao|pulav)\b"),
    "Burgers":       ({"burgers", "burger", "american", "hot dogs"}, r"\b(burgers?|smash|sliders?|cheeseburger)\b"),
    "Pizza":         ({"pizza"}, r"\b(pizzas?|pepperoni|margherita)\b"),
    # Talabat's plain "Chicken" label covers grills/shawarma too, so it deliberately doesn't count here
    "Fried Chicken": ({"fried chicken", "broasted", "wings"}, r"\b(broast(ed)?|fried chicken|crispy chicken|wings|nuggets|strips|zinger|tenders|chicken bites|popcorn chicken|chicken bucket|bucket)\b"),
    "Shawarma":      ({"shawarma", "wraps"}, r"\b(shawarma|shawerma|shawurma)\b"),
    "Arabic":        ({"arabic", "bahraini", "middle eastern", "yemeni", "saudi", "mandi", "emirati", "iraqi", "syrian", "egyptian", "moroccan", "khaleeji", "manaqeesh", "falafel", "mezze"},
                      r"\b(mandi|madhbi|machboos|majboos|kabsa|harees|madghoot|madfoon|bukhari|mezze|hummus|manakish|manaqeesh|falafel|foul|khaleeji)\b"),
    "Lebanese":      ({"lebanese"}, r"\b(lebanese|tawook|shish taouk|fattoush|tabbouleh)\b"),
    "Turkish":       ({"turkish"}, r"\b(turkish|doner|döner|iskender|pide|lahmacun|kunefe|künefe)\b"),
    "Iranian":       ({"iranian", "persian"}, r"\b(iranian|persian|chelo|kabab koobideh|koobideh)\b"),
    "Grills & BBQ":  ({"grills", "bbq", "kebab", "steak", "steakhouse"}, r"\b(grill(ed|s)?|bbq|barbe?cue|kebabs?|kababs?|tikka|steaks?|mixed grill)\b"),
    "Seafood":       ({"seafood", "fish", "fresh meat & fish"}, r"\b(seafood|shrimps?|prawns?|fish|hamour|lobster|crab|calamari)\b"),
    "Chinese":       ({"chinese", "indo-chinese"}, r"\b(chinese|chow mein|manchurian|dim ?sum|kung pao|fried rice)\b"),
    "Japanese & Sushi": ({"japanese", "sushi", "ramen"}, r"\b(sushi|ramen|maki|sashimi|japanese|teriyaki|katsu|udon)\b"),
    "Asian":         ({"asian", "thai", "korean", "filipino", "vietnamese", "indonesian", "malaysian", "noodles"}, r"\b(thai|korean|filipino|vietnamese|pho|pad thai|noodles?|bibimbap|k-?food)\b"),
    "Italian & Pasta": ({"italian", "pasta"}, r"\b(pasta|italian|lasagn[ae]|risotto|carbonara|alfredo)\b"),
    "Mexican":       ({"mexican", "tex-mex"}, r"\b(tacos?|burritos?|quesadillas?|nachos|mexican)\b"),
    "Sandwiches":    ({"sandwiches", "subs", "street food", "cafeteria", "snacks"}, r"\b(sandwich(es)?|subs?|panini|toasties?|karak.*sandwich)\b"),
    "Breakfast":     ({"breakfast", "pancakes", "waffles", "crepes"}, r"\b(breakfast|brunch|pancakes?|waffles?|crepes?|omelett?e)\b"),
    "Healthy":       ({"healthy", "salad", "keto", "vegan", "vegetarian", "poke"}, r"\b(healthy|salads?|keto|vegan|protein|poke|low ?cal)\b"),
    "Desserts":      ({"desserts", "ice cream", "cakes", "donuts", "arabic sweets", "pastries & sweets", "frozen yogurt", "sweets", "kunafa", "chocolate", "cookies"},
                      r"\b(desserts?|cakes?|ice ?cream|donuts?|doughnuts?|kunafa|knafeh|kanafany|cookies?|brownies?|gelato|cheesecake|froyo)\b"),
    "Bakery":        ({"bakery", "pastries", "manaqeesh"}, r"\b(bakery|croissants?|pastr(y|ies)|bread|samoon)\b"),
    "Coffee & Drinks": ({"coffee", "cafe", "beverages", "juices", "smoothies", "milkshakes", "bubble tea", "tea", "karak"},
                      r"\b(coffee|latte|cappuccino|espresso|karak|chai|juices?|smoothies?|milkshakes?|mojito|bubble tea|boba|frappe)\b"),
}

ORDER = list(CANON)
_LABEL = {lab: c for c, (labels, _) in CANON.items() for lab in labels}
_RX = {c: re.compile(rx, re.I) for c, (_, rx) in CANON.items()}

# Arabic keywords for Instagram captions (Bahraini accounts often post in Arabic)
_AR = {
    "Burgers": "برجر|برغر", "Pizza": "بيتزا", "Shawarma": "شاورما|شاورمة",
    "Fried Chicken": "بروستد|دجاج مقلي|كرسبي", "Biryani": "برياني", "Arabic": "مندي|مضبي|مجبوس|كبسة|هريس|فلافل",
    "Seafood": "سمك|روبيان|هامور|مأكولات بحرية", "Desserts": "حلويات|كيك|آيس كريم|كنافة", "Coffee & Drinks": "قهوة|كرك|عصير",
    "Grills & BBQ": "مشاوي|مشويات|كباب|تكة", "Japanese & Sushi": "سوشي", "Breakfast": "فطور|ريوق", "Italian & Pasta": "باستا|معكرونة",
    "Pakistani": "باكستاني", "Indian": "هندي", "Lebanese": "لبناني", "Turkish": "تركي", "Bakery": "مخبز|معجنات",
}
_AR_RX = {c: re.compile(rx) for c, rx in _AR.items()}


def primary(labels, name):
    """A restaurant's main cuisine(s): its FIRST source label plus what its name says
    (e.g. "Pizza Hut", "Bazooka Fried Chicken"). Used so that picking a cuisine shows every
    dish at a specialist, but only the matching dishes at a place where it's a side line."""
    return classify(list(labels)[:1], name)


def classify(labels=(), text=""):
    """labels: source cuisine tags (e.g. Talabat's); text: names/captions to keyword-scan."""
    found = []
    for lab in labels:
        c = _LABEL.get(lab.strip().lower())
        if c and c not in found:
            found.append(c)
    if text:
        for c in ORDER:
            if c not in found and (_RX[c].search(text) or (c in _AR_RX and _AR_RX[c].search(text))):
                found.append(c)
    # Pakistani/Indian places that only say "biryani" still get the Biryani chip; don't guess nationality
    return sorted(found, key=ORDER.index)
