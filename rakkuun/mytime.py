"""MyTime-Anbindung, lesender Teil: Produktsuche über die öffentlichen Suchseiten.

Nutzt nur /search und Produktseiten (laut robots.txt erlaubt), nicht die interne
/api/. Zwischen Anfragen wird eine Pause eingehalten."""

from __future__ import annotations

import html
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = "https://www.mytime.de"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
PAUSE_S = 1.0

_last_request = 0.0


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    weight: str          # wie auf der Seite angegeben, z. B. "250 g", "1 l", "10 Stück"
    price_eur: float
    bulk_price: str      # z. B. "7,00 €/1 kg"
    url: str
    min_quantity: int = 1
    step: int = 1

    @property
    def grams(self) -> float | None:
        return parse_weight(self.weight)


def parse_weight(text: str) -> float | None:
    """'250 g' -> 250, '1 kg' -> 1000, '1 l' -> 1000, '4 x 125 g' -> 500. Stückangaben -> None."""
    t = text.lower().replace(",", ".")
    multi = re.match(r"\s*(\d+)\s*x\s*(.+)", t)
    factor = 1.0
    if multi:
        factor, t = float(multi.group(1)), multi.group(2)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", t)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    return factor * value * (1000 if unit in ("kg", "l") else 1)


def _get(url: str) -> str:
    global _last_request
    wait = PAUSE_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE"})
    with urllib.request.urlopen(request, timeout=30) as response:
        _last_request = time.monotonic()
        return response.read().decode("utf-8", errors="replace")


def _price(text: str) -> float:
    return float(re.sub(r"[^\d,]", "", text).replace(",", "."))


_CARD_START = re.compile(r'<li class="product-card\s*"\s+data-listitemid=')


def parse_search(page: str) -> list[Product]:
    starts = [m.start() for m in _CARD_START.finditer(page)] + [len(page)]
    products = []
    for card in (page[a:b] for a, b in zip(starts, starts[1:])):
        name = re.search(r'class="product-card__name__link">\s*(.*?)\s*</a>', card, re.S)
        price = re.search(r'product-card__price--current"\s*>\s*<strong[^>]*>\s*(.*?)\s*</strong>', card, re.S)
        sku = re.search(r'data-sku="(\d+)"', card)
        if not (name and price and sku):
            continue
        weight = re.search(r'class="product-card__weight">\s*(.*?)\s*</small>', card, re.S)
        bulk = re.search(r'class="product-card__bulk-price"[^>]*>\s*(.*?)\s*</div>', card, re.S)
        url = re.search(r'class="product-card__name__link"', card) and re.search(r'href="(/[^"]+\.html)"', card)
        qty = re.search(r'name="quantity"[^>]*', card)
        minimum = re.search(r'min="(\d+)"', qty.group(0)) if qty else None
        step = re.search(r'step="(\d+)"', qty.group(0)) if qty else None
        products.append(Product(
            sku=sku.group(1),
            name=html.unescape(re.sub(r"\s+", " ", name.group(1))),
            weight=html.unescape(weight.group(1).strip()) if weight else "",
            price_eur=_price(price.group(1)),
            bulk_price=html.unescape(re.sub(r"\s+", " ", bulk.group(1))) if bulk else "",
            url=BASE + url.group(1) if url else "",
            min_quantity=int(minimum.group(1)) if minimum else 1,
            step=int(step.group(1)) if step else 1,
        ))
    return products


def search(query: str) -> list[Product]:
    return parse_search(_get(f"{BASE}/search?query={urllib.parse.quote(query)}"))


def find_by_sku(sku: str, query: str) -> Product | None:
    """Aktuellen Preis eines zugeordneten Artikels holen (Suche nach Begriff, Treffer per SKU)."""
    for product in search(query):
        if product.sku == sku:
            return product
    for product in search(sku):
        if product.sku == sku:
            return product
    return None
