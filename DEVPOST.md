# SnapShop — see it, shop it

## Inspiration

You spot something you love in the real world, a friend's snapback, a hoodie on the subway, a water bottle on someone's desk, and actually finding it online is a pain. You squint at the logo, guess keywords, and scroll through results that are kind of close.

We wanted to collapse that whole loop into one gesture: **look at a product, get the exact thing, ready to buy directly through the merchant.** Two things made it feel possible right now: multimodal models (Gemini) are finally good enough to recognize a specific product from a casual photo, and Shopify's **Universal Commerce Protocol (UCP)** exposes a global, agent-queryable catalog, so an AI agent can actually _shop_, not just describe. We also wanted the camera to be where your eyes already are, so we targeted **Meta Ray-Ban glasses** from day one.

## What it does

Point your Meta glasses at any product. SnapShop:

1. **Identifies it** : the photo (plus an optional spoken hint like _"the green hoodie"_) goes to **Gemini Vision**, which extracts a structured description: product type, brand, colorway, logo placement, distinguishing features, and a compact search query.
2. **Finds it for sale** : we query **Shopify's UCP global catalog** with that query (fanning out a precise + a broad query for recall).
3. **Picks the right one** : a second **Gemini multimodal pass** compares _your photo_ against the candidate product images and re-ranks them, trusting pixels over titles.
4. **Stays honest** : if nothing is a true match, SnapShop doesn't pretend. It shows **"Not sure this is your exact product, here's the closest"** plus alternatives.
5. **Gets you to checkout** : tap the result to open the merchant cart with the item already in it. Everything you scan drops into a **local cart** you can swipe-to-delete, persisted on device.

## How we built it

**Backend : FastAPI (Python).**

- **Gemini** via the `google-genai` SDK with **structured output** so the model returns validated JSON instead of fragile free text.
- **Shopify UCP** spoken directly over `search_catalog` against the global catalog, with a deep-link cart hand-off (`continue_url`).
- A **two-stage retrieve-then-rerank** pipeline: a cheap keyword ranker for recall, then a Gemini visual reranker for precision. The reranker scores type, brand, **construction**, **colorway**, and **logo scale/placement/color**.

**iOS : SwiftUI.**

- **Meta Wearables DAT SDK** for glasses capture, **Speech** for voice-guided scans, local persistent cart (UserDefaults), and item-found push notifications.
- A clean purple/white design with a custom scan flow.

We deliberately kept the agent **UCP-native** instead of scraping a search engine, the protocol is the point.

## Challenges we ran into

- **Getting the re-ranking right.** Finding candidates was easy; picking the _right_ one was the real fight. Trusting the catalog's top hit returned a generic Takeya bottle for a ThermoFlask, and ranking by keyword overlap was color-blind, a white shirt matched a _black_ one whose title read _"White-Haired Pirate"_ (a character, not a color). The fix was our two-stage **retrieve-then-rerank**: keyword recall first, then a Gemini pass that judges the **actual product images** against your photo, so pixels beat titles. And when nothing truly matches, we surface the closest result honestly instead of faking an exact hit.
- **Shopify's own UCP tool was broken.** UCP is brand new, and the official `@shopify/ucp-cli` is still in early developer preview. Every single request, including the examples from Shopify's own Quickstart documentation failed with `MCP_INVALID_RESPONSE`. The CLI literally couldn't read what its own servers were sending back. Therefore, we bypassed the CLI entirely and wrote our own minimal MCP client that speaks JSON-RPC directly to `catalog.shopify.com/api/ucp/mcp`, skipping the broken client-side validation. We managed to get real merchants and real products flowing through SnapShop, even when the official tool wasn't working.
- **The hardware button we couldn't unlock.** Our initial idea was super simple: you see a product, you press the capture button on your Meta Ray-Bans, and SnapShop does the rest. No pulling out your phone, no opening an app, no tapping a "scan" button, the whole point of smart glasses is that the camera is already where your eyes are. The friction has to be zero. The reality: Meta's Wearables DAT SDK (currently in developer preview) doesn't expose the glasses' physical capture button as an event your app can subscribe to. The hardware button is reserved for Meta's own first-party capture flow. We could read frames from the camera once an app session was active, but we couldn't start that session from a button press on the glasses themselves, it had to be initiated from the phone. So our hands-free, glance-and-scan dream collapsed into a "press a button on your phone, then look at the product" flow that defeated the whole point of using glasses.

## Accomplishments that we're proud of

- A **real, on-device app** that goes from a casual photo to a checkout-ready merchant cart.
- A reranker that respects the visual product details, a black snapback isn't a white one.
- Staying **100% in-protocol** with UCP, our coverage grows automatically as more merchants adopt the standard.
- It sends real buyers to small Shopify merchants. A scan searches the whole UCP catalog, not just big brands, so an independent shop can win the sale just by being on Shopify, and the shopper lands straight in its cart. Discovery for small businesses, no ad budget required.

## What we learned

- **Recall and precision are different jobs.** The search query should be short and title-like (for recall); the rich descriptive detail belongs to the _reranker_ (for precision). Stuffing the query hurts.
- **Prompt design scales by principle, not by enumeration.** Give the model the goal plus a few examples — not a rule per product category.
- **Structured output > prompt-and-parse.** Pydantic schemas removed a whole class of bugs.
- **Calibrated honesty beats confident guessing** in a shopping context.
- **Building a native iOS app from scratch.** We picked up **Swift / SwiftUI** and learned to integrate third-party **SDKs** (Meta Wearables DAT, Speech) — plus the real-world side of code-signing and deploying to a physical iPhone.
- A lot about the **emerging agentic-commerce stack** (UCP, MCP).

## What's next for SnapShop

- **Full Meta glasses flow** — capture and shop entirely hands-free, "from glance to cart."
- **Voice refinement** — _"the cheaper one"_, _"in black"_, _"under $50"_ to steer the search live.
- **Broader in-protocol coverage** — more UCP-enabled catalogs as the ecosystem grows, plus Shopify's image-similarity search once it's available on the public endpoint.
- **Deeper checkout** — UCP account-linking for one-tap, pre-filled purchases.
- **Smarter cart** — price drop alerts and "find it cheaper elsewhere" across merchants.
- **On-lens results with the built-in display**, on Ray-Ban Display glasses, show the match, price, and a confirm action right in your field of view, see a product, get the answer in-lens, no phone at all.
