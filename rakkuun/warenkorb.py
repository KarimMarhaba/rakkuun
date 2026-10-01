"""MyTime-Warenkorb befüllen – mit einem ferngesteuerten Browser, eingeloggt wie ein Mensch.

- Zugangsdaten nur aus den Umgebungsvariablen MYTIME_EMAIL und MYTIME_PSWD.
- Es wird nur hinzugefügt, was zum Wochenbedarf noch fehlt. Ein zweiter Lauf legt also
  nichts doppelt hinein, und Artikel, die schon im Warenkorb liegen, bleiben unberührt.
- Es wird nie zur Kasse gegangen. Bestellen bleibt immer ein Schritt des Nutzers.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

from .data import Catalog
from .shopping import ShoppingPlan

BASE = "https://www.mytime.de"
PROXY_CA = "/root/.ccr/agent-proxy-ca.crt"


@dataclass
class CartItem:
    sku: str
    name: str
    quantity: int


@dataclass
class FillResult:
    added: list[tuple[str, str, int]] = field(default_factory=list)      # (sku, name, Menge)
    already: list[tuple[str, str, int]] = field(default_factory=list)    # schon ausreichend im Korb
    failed: list[tuple[str, str]] = field(default_factory=list)          # (Name, Grund)
    skipped: list[tuple[str, str]] = field(default_factory=list)         # (Name, Grund)
    cart: list[CartItem] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)


def _proxy_args() -> tuple[dict | None, list[str]]:
    """Im Cloud-Container läuft der Verkehr über einen Proxy mit eigener CA. Chromium vertraut
    dann gezielt nur dieser CA (über deren Schlüssel-Hash), nicht pauschal allen Zertifikaten."""
    proxy = os.environ.get("HTTPS_PROXY")
    if not proxy or not os.path.exists(PROXY_CA):
        return None, []
    spki = subprocess.run(
        f"openssl x509 -in {PROXY_CA} -pubkey -noout | openssl pkey -pubin -outform der"
        " | openssl dgst -sha256 -binary | base64",
        shell=True, capture_output=True, text=True, check=True).stdout.strip()
    return {"server": proxy}, [f"--ignore-certificate-errors-spki-list={spki}"]


class MyTimeShop:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def __enter__(self) -> "MyTimeShop":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        proxy, args = _proxy_args()
        self._browser = self._pw.chromium.launch(headless=self.headless, proxy=proxy, args=args)
        self.page = self._browser.new_context(locale="de-DE").new_page()
        self.page.set_default_timeout(30000)
        return self

    def __exit__(self, *exc) -> None:
        self._browser.close()
        self._pw.stop()

    def _goto(self, path: str) -> None:
        self.page.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(1500)
        consent = self.page.locator("dialog.cookie-dialog [data-action*=acceptNecessary]")
        if consent.count() and consent.first.is_visible():
            consent.first.click()          # nur notwendige Cookies
            self.page.wait_for_timeout(500)

    def _relogin_if_asked(self) -> None:
        """Manche Kontoseiten verlangen eine erneute Anmeldung."""
        if self.page.locator("#login-username").count() and self.page.locator("#login-username").first.is_visible():
            self.page.fill("#login-username", os.environ["MYTIME_EMAIL"])
            self.page.fill("#login-password", os.environ["MYTIME_PSWD"])
            self.page.click("form[action*='login'] button[type=submit]")
            self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_timeout(2500)

    def last_order(self) -> dict | None:
        """Letzte Bestellung: Nummer, Bestelldatum, Status und Lieferdatum (aus 'Meine Bestellungen')."""
        from datetime import datetime
        self._goto("/account/orders")
        self._relogin_if_asked()
        text = self.page.inner_text("body")
        m = re.search(r"(\d{10})\s+(\d{2}\.\d{2}\.\d{4})\s+([^\t\n]+?)\s+[\d.,]+\s*€", text)
        if not m:
            return None
        number, ordered, status = m.group(1), m.group(2), m.group(3).strip()
        self._goto(f"/account/orders/{number}")
        self._relogin_if_asked()
        detail = self.page.inner_text("body")
        d = re.search(r"Lieferdatum\s+(\d{2}\.\d{2}\.\d{4})", detail)
        parse = lambda x: datetime.strptime(x, "%d.%m.%Y").date()
        return {"nummer": number, "bestellt": parse(ordered), "status": status,
                "lieferung": parse(d.group(1)) if d else None}

    def login(self) -> None:
        email, password = os.environ.get("MYTIME_EMAIL"), os.environ.get("MYTIME_PSWD")
        if not email or not password:
            raise RuntimeError("MYTIME_EMAIL und MYTIME_PSWD sind nicht gesetzt.")
        self._goto("/login")
        self.page.fill("#login-username", email)
        self.page.fill("#login-password", password)
        self.page.click("form[action='/login'] button[type=submit]")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(2500)
        if "/login" in self.page.url:
            raise RuntimeError("Login bei MyTime fehlgeschlagen – Zugangsdaten prüfen.")

    def cart(self) -> tuple[list[CartItem], dict[str, str]]:
        self._goto("/cart")
        items = []
        for row in self.page.locator("li.product-card--basket").all():
            form = row.locator("form.product-card__order")
            sku = form.get_attribute("data-sku") if form.count() else None
            if not sku:
                continue
            name = row.locator(".product-card__name__link").first.inner_text().strip()
            qty = row.locator("input[name=quantity]").first.input_value()
            items.append(CartItem(sku, name, int(qty or 0)))
        summary = {}
        text = self.page.locator(".basket__summary").first.inner_text() if self.page.locator(".basket__summary").count() else ""
        for label in ("Einkaufswert", "Versandkosten", "Gesamtsumme"):
            m = re.search(label + r"\*?\s*([\d.,]+\s*€)", text)
            if m:
                summary[label] = m.group(1)
        m = re.search(r"[Nn]och\s*([\d.,]+\s*€)", text)
        if m:
            summary["bis versandkostenfrei"] = m.group(1)
        return items, summary

    def add(self, sku: str, query: str, quantity: int) -> None:
        """Artikel über die Suche finden und mit der gewünschten Menge in den Warenkorb legen.
        Nach dem Klick wird geprüft, ob der Shop den Artikel als 'im Warenkorb' markiert; sonst ein
        zweiter Versuch."""
        for attempt in range(2):
            for q in (query, sku):
                self._goto(f"/search?query={q}")
                form = self.page.locator(f"form.product-card__order[data-listtype=cart][data-sku='{sku}']")
                if not form.count():
                    continue
                form = form.first
                form.scroll_into_view_if_needed()
                form.locator("input[name=quantity]").fill(str(quantity))
                button = form.locator("button[data-add-to-cart]")
                button.click()
                try:
                    self.page.wait_for_function(
                        "b => b.classList.contains('btn--added')", arg=button.element_handle(), timeout=8000)
                    self.page.wait_for_timeout(800)
                    return
                except Exception:
                    break   # nicht bestätigt -> zweiter Versuch mit frisch geladener Seite
            else:
                raise LookupError("Artikel in der Suche nicht gefunden")
        raise RuntimeError("Shop hat das Hinzufügen nicht bestätigt")


def fill_cart(catalog: Catalog, shopping: ShoppingPlan, headless: bool = True,
              extras: dict[str, tuple[str, str, int]] | None = None) -> FillResult:
    """Bitte während des Laufs den Warenkorb nicht in App/Browser öffnen: MyTime verträgt keine zwei
    gleichzeitigen Sitzungen am selben Warenkorb – eine überschreibt dann die andere."""
    result = FillResult()
    wanted: dict[str, tuple[str, str, int]] = dict(extras or {})
    for delivery in shopping.deliveries:
        for line in delivery.lines + delivery.filler:
            ing = catalog.ingredients[line.ingredient_id]
            sku = ing.mytime.get("sku")
            if not sku or line.status == "fehlt":
                result.skipped.append((line.name, "kein MyTime-Produkt zugeordnet"))
                continue
            name, query, qty = wanted.get(sku, (line.product or line.name, ing.mytime_query, 0))
            wanted[sku] = (name, query, qty + line.packages)

    with MyTimeShop(headless=headless) as shop:
        shop.login()
        in_cart = {item.sku: item.quantity for item in shop.cart()[0]}
        errors: dict[str, str] = {}
        for sku, (name, query, qty) in wanted.items():
            if qty - in_cart.get(sku, 0) <= 0:
                result.already.append((sku, name, in_cart[sku]))
        # Bis zu zwei Runden: Wird der Warenkorb zwischendurch von einer anderen Sitzung (App/Browser)
        # überschrieben, fehlen danach Artikel – die werden in der zweiten Runde ergänzt.
        for _ in range(2):
            pending = {sku: qty - in_cart.get(sku, 0) for sku, (_, _, qty) in wanted.items()
                       if qty - in_cart.get(sku, 0) > 0}
            if not pending:
                break
            for sku, missing in pending.items():
                name, query, _ = wanted[sku]
                try:
                    shop.add(sku, query, missing)
                    if not any(a[0] == sku for a in result.added):
                        result.added.append((sku, name, missing))
                    errors.pop(sku, None)
                except Exception as e:  # einzelner Artikel darf den Rest nicht blockieren
                    errors[sku] = str(e).splitlines()[0][:120]
            in_cart = {item.sku: item.quantity for item in shop.cart()[0]}
        result.failed += [(wanted[sku][0], why) for sku, why in errors.items()]
        result.cart, result.summary = shop.cart()

    # Gegenprobe: liegt jetzt wirklich die gewünschte Menge im Korb?
    final = {item.sku: item.quantity for item in result.cart}
    for sku, (name, _, qty) in wanted.items():
        if final.get(sku, 0) < qty and not any(f[0] == name for f in result.failed):
            result.failed.append((name, f"im Warenkorb {final.get(sku, 0)} statt {qty}"))
    return result


def render_result(result: FillResult) -> str:
    out = ["# MyTime-Warenkorb", ""]
    if result.added:
        out += ["## Hinzugefügt"] + [f"- {qty}× {name}" for _, name, qty in result.added] + [""]
    if result.already:
        out += ["## War schon im Warenkorb"] + [f"- {qty}× {name}" for _, name, qty in result.already] + [""]
    if result.failed:
        out += ["## ⚠️ Nicht geklappt"] + [f"- {name}: {why}" for name, why in result.failed] + [""]
    if result.skipped:
        out += ["## Übersprungen"] + [f"- {name}: {why}" for name, why in result.skipped] + [""]
    out += ["## Warenkorb jetzt"] + [f"- {i.quantity}× {i.name}" for i in result.cart]
    if result.summary:
        out += [""] + [f"**{k}:** {v}" for k, v in result.summary.items()]
    out += ["", "_Nichts bestellt. Zur Kasse gehst du selbst, wenn alles passt._"]
    return "\n".join(out) + "\n"
