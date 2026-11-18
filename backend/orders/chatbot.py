import json
import random
import re

from django.db.models import Max, Min
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Dish, SiteSetting
from .views import MEAL_INFO, meal_list, meal_state

CONTACT = 'Visit us near the campus gate, call 90740 92355, or WhatsApp us from the Contact section at the bottom of the home page.'
ADDRESS = 'Homely Kitchen Canteen, near YMBC block, Kothamangalam'
MAPS_URL = 'https://www.google.com/maps/search/?api=1&query=Homely+Kitchen+Canteen+Kothamangalam'


def _location_actions():
    """Quick links shown under the location reply so the customer can jump
    straight to the map page or the home page's Contact section, instead of
    only getting the address as plain text."""
    return [
        {'label': '📍 Open Location page', 'url': reverse('location')},
        {'label': '📞 Contact section', 'url': reverse('menu') + '#contact'},
    ]

# Dish-name words that are too generic / collide with everyday phrasing to use
# as a lone match anchor ("meals" collides with "today's meals", etc.).
_ANCHOR_STOPWORDS = {'meals'}
_MEAL_WORDS = ('breakfast', 'lunch', 'dinner')


def has(msg, *words):
    return any(w in msg for w in words)


def word(msg, token):
    """Whole-word match — avoids 'rs' matching inside 'orders', 'hours', etc."""
    return re.search(r'\b' + re.escape(token) + r'\b', msg) is not None


def any_word(msg, *tokens):
    return any(word(msg, t) for t in tokens)


def _anchor_words(name):
    """Distinctive tokens from a dish name worth matching on their own,
    e.g. 'Biriyani-Full' -> ['biriyani', 'full']. Short/common words are
    dropped unless explicitly allow-listed (so 'egg' still matches)."""
    allow_short = {'egg'}
    out = []
    for w in re.split(r'[^a-z]+', name.lower()):
        if not w:
            continue
        if w in _ANCHOR_STOPWORDS:
            continue
        if len(w) >= 4 or w in allow_short:
            out.append(w)
    return out


def _dish_matches(msg):
    """Find every distinct dish name mentioned in msg. Rows with the same
    name across different meals (e.g. Appam at breakfast and dinner) are
    merged. If the message spells out a dish's full name exactly, that wins
    alone — e.g. 'chicken fry' shouldn't also drag in 'Chicken Curry' just
    because they share the word 'chicken'. Partial anchor-word matching is
    only used as a fallback when no exact full name is present."""
    by_name = {}
    for d in Dish.objects.all():
        by_name.setdefault(d.name, []).append(d)

    exact = [(name, rows) for name, rows in by_name.items() if name.lower() in msg]
    if exact:
        return exact

    return [(name, rows) for name, rows in by_name.items() if any_word(msg, *_anchor_words(name))]


def _dish_line(name, rows):
    meals = ', '.join(sorted({MEAL_INFO[r.meal]['label'] for r in rows}))
    prices = sorted({r.price for r in rows})
    price_txt = f'Rs {prices[0]:.0f}' if len(prices) == 1 else f'Rs {prices[0]:.0f}–{prices[-1]:.0f}'
    any_in_stock = any(r.is_available for r in rows)
    stock = 'available' if any_in_stock else 'sold out right now'
    cap = next((r.daily_limit for r in rows if r.daily_limit), 0)
    line = f'{name}: {price_txt}, served at {meals.lower()}. It is {stock}.'
    if cap:
        line += f' Limited to {cap} portions a day.'
    return line


def _next_meal_specials():
    """The upcoming meal and the dishes you can pre-order for it right now,
    even though nothing is being cooked this exact minute."""
    upcoming = [m for m in meal_list() if meal_state(m['key']) == 'later']
    nxt = upcoming[0] if upcoming else meal_list()[0]
    when = 'later today' if upcoming else 'tomorrow'
    names = list(Dish.objects.filter(meal=nxt['key'], is_available=True)
                 .order_by('category', 'name').values_list('name', flat=True))
    return nxt, when, names


def available_now():
    """Dishes that can be ordered this minute: meal is being served and the
    dish is not sold out. If nothing is live right now, show the next meal's
    specials instead, since pre-orders are accepted any time."""
    if not SiteSetting.load().accepting_orders:
        return 'Nothing is available right now. We are not taking pre-orders at the moment, please check back soon.'

    live = next((m for m in meal_list() if meal_state(m['key']) == 'open'), None)
    if live:
        names = list(Dish.objects.filter(meal=live['key'], is_available=True)
                     .order_by('category', 'name').values_list('name', flat=True))
        if names:
            msg = f'Available now ({live["label"]}, until {live["end_label"]}):\n' + '\n'.join(f'- {n}' for n in names)
        else:
            msg = f'Every {live["label"].lower()} dish is sold out right now.'
        # Even while a meal is live, the next meal can already be pre-ordered —
        # surface its specials too so the customer can plan ahead.
        nxt, when, next_names = _next_meal_specials()
        if next_names and nxt['key'] != live['key']:
            msg += (f'\n\nYou can also pre-order {nxt["label"]} ({nxt["start_label"]}–{nxt["end_label"]}, '
                    f'{when}):\n' + '\n'.join(f'- {n}' for n in next_names))
        return msg

    nxt, when, names = _next_meal_specials()
    if names:
        specials = '\n'.join(f'- {n}' for n in names)
        return (f'Nothing is being served this exact minute — {nxt["label"]} starts {when} at {nxt["start_label"]}.\n'
                f'But you can pre-order now for {nxt["label"]} and collect between '
                f'{nxt["start_label"]} and {nxt["end_label"]}:\n{specials}')
    return f'Nothing is available right now. {nxt["label"]} starts {when} at {nxt["start_label"]}, and the menu is being updated.'


def answer(raw):
    msg = raw.lower().strip()
    if not msg:
        return 'Type a question and I will help.'
    options = '100%'  # checkout always charges the full amount online (see views.advance_options)

    # 1. A dish (or dishes) was named: price, meal, stock, daily limit.
    hits = _dish_matches(msg)
    if len(hits) == 1:
        name, rows = hits[0]
        return _dish_line(name, rows)
    if len(hits) > 1:
        return 'Here’s what I found:\n' + '\n'.join(f'- {_dish_line(n, r)}' for n, r in hits)

    # 2. Asking what's cooking right now / "today's specials".
    asks_timing = has(msg, 'time', 'timing', 'hours', 'when', 'open', 'schedule')
    asks_available = has(msg, 'available', 'now', 'serving', 'in stock', 'stock', 'special', 'specials')
    if asks_available and not asks_timing:
        return available_now()
    if asks_timing or has(msg, 'available', 'now', 'serving'):
        names = {'open': 'serving now', 'later': 'starts later today', 'closed': 'finished for today'}
        lines = [f'{m["label"]}: {m["start_label"]} to {m["end_label"]} ({names[meal_state(m["key"])]})'
                 for m in meal_list()]
        return "Today's meals:\n" + '\n'.join(lines)

    # 3. Trying to order more than one meal in the same cart.
    meal_mentions = sum(1 for m in _MEAL_WORDS if word(msg, m))
    if meal_mentions >= 2 or has(msg, 'together', 'combine', 'mix', 'same order', 'both meals'):
        return ('You can only order one meal at a time — all dishes in a cart must be from the same '
                'meal (Breakfast, Lunch or Dinner). Place a separate order for each meal you want.')

    # 4. Where the place actually is.
    if has(msg, 'located', 'location', 'address', 'direction', 'map', 'reach you', 'find you',
           'parking', 'get there', 'how to reach', 'how do i reach') \
       or (has(msg, 'where') and not has(msg, 'order')):
        text = f'We’re at {ADDRESS}. Open in Maps: {MAPS_URL}. Or call/WhatsApp us — see the Contact section on the home page.'
        return text, _location_actions()

    # 5. What E-Homely even is.
    if has(msg, 'about', 'who are you', 'what is e-homely', 'what is ehomely', 'your restaurant', 'your story', 'tell me about'):
        return ('E-Homely brings home-style Kerala meals to campus students and staff. Pick a meal, '
                'pre-order any time, pay the full amount online, and collect hot at the counter with your token.')

    if has(msg, 'cancel', 'refund'):
        return ('You can cancel from your token page until the kitchen starts preparing the order. '
                'For a refund of the advance, please speak to the counter.')

    if has(msg, 'token', 'expire', 'valid', 'timer', 'late'):
        return 'Your token does not expire. Keep the number and show it at the counter when you collect.'

    if has(msg, 'advance', 'razorpay', 'upi', 'card', 'pay', 'payment', 'cash'):
        return (f'You pay {options} of the bill online (Razorpay) to get your token, '
                'and the rest at the counter when you collect.')

    if has(msg, 'pickup', 'pick up', 'collect', 'delivery', 'deliver'):
        return ('Pickup only — no delivery. You can pre-order any time, then collect during the meal\'s '
                'serving window. Show your token number at the counter.')

    # 6. How many orders a customer can have open at once.
    if has(msg, 'how many orders', 'multiple orders', 'second order', 'another order', 'two orders') \
       or (has(msg, 'limit') and has(msg, 'order')):
        return ('You can have up to 2 open paid orders at a time per phone number. '
                'Pick up or cancel one before placing a third.')

    # 7. Daily caps on popular dishes (fallback if no specific dish matched above).
    if has(msg, 'daily limit', 'sold out for today', 'how many left', 'limited'):
        capped = list(Dish.objects.filter(daily_limit__gt=0).values_list('name', 'daily_limit').distinct())
        if capped:
            lines = '\n'.join(f'- {n}: {c} portions/day' for n, c in capped)
            return 'A few dishes are capped per day:\n' + lines
        return 'No dishes are limited today — order as much as you like.'

    if word(msg, 'rs') or has(msg, 'price', 'cost', 'cheap', 'rupee'):
        r = Dish.objects.aggregate(lo=Min('price'), hi=Max('price'))
        if r['lo'] is None:
            return 'The menu is being updated. Please check back soon.'
        return f'Dishes range from Rs {r["lo"]:.0f} to Rs {r["hi"]:.0f}. Ask me about a dish for its exact price.'

    if has(msg, 'order', 'how'):
        return ('How to order:\n1. Pick a meal and add dishes (you can pre-order any time!)\n'
                '2. Go to checkout, enter your name and phone\n'
                f'3. Pay {options} of the bill online\n'
                '4. Get your token — collect during your meal\'s serving window at the counter')

    if has(msg, 'menu', 'food', 'dish', 'eat', 'what do you have', "what's on"):
        return available_now()

    if has(msg, 'contact', 'support', 'help', 'phone', 'call'):
        return CONTACT

    if has(msg, 'thanks', 'thank you', 'thx', 'ty'):
        return 'You\'re welcome! Anything else I can help with?'

    if has(msg, 'hi', 'hello', 'hey'):
        return 'Hi! Ask me about meal timings, prices, payment, location or how to order.'

    return random.choice([
        'Could you tell me more? I can help with timings, prices, the menu, location and ordering.',
        'Try asking: "What\'s available now?" or "How to order?"',
    ])


@require_POST
def chat(request):
    try:
        message = json.loads(request.body).get('message', '')
    except (ValueError, AttributeError):
        message = ''
    result = answer(str(message)[:200])
    # Most answers are a plain string. A few (like the location reply) are a
    # (text, actions) pair, where actions is a list of {label, url} quick
    # links the frontend renders as clickable buttons under the message.
    if isinstance(result, tuple):
        reply, actions = result
    else:
        reply, actions = result, None
    payload = {'reply': reply}
    if actions:
        payload['actions'] = actions
    return JsonResponse(payload)
