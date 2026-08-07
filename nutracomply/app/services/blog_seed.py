"""
Trending-topic blog posts, published under Navneet's byline.

Every regulatory claim here is sourced from reporting published between
Nov 2025 and Aug 2026 and is deliberately hedged where FSSAI has signalled an
intent but has not yet notified a regulation. That distinction matters: readers
make label decisions on this, and overstating a draft as binding is exactly the
failure mode a compliance blog cannot afford.

Seeding is idempotent by slug and runs at startup, so a deploy publishes these
without anyone having to hit an admin endpoint.
"""

from datetime import datetime

from app.models import BlogCategory, BlogPost, BlogPostStatus, User

AUTHOR_NAME = "Navneet"
AUTHOR_EMAIL = "navneet@regbite.com"


def _get_author(db):
    """
    Resolve the byline user.

    The blog templates render `post.author.name`, so a byline needs a User row.
    If Navneet has no account we create a deliberately INACTIVE one with an
    unusable password: it exists to render a name, not to be a login vector.
    """
    user = (
        db.query(User)
        .filter(User.name.ilike(f"%{AUTHOR_NAME}%"))
        .first()
    )
    if user:
        return user

    user = db.query(User).filter(User.email == AUTHOR_EMAIL).first()
    if user:
        return user

    user = User(
        email=AUTHOR_EMAIL,
        name="Navneet",
        hashed_password="!",        # not a valid bcrypt hash — cannot authenticate
        is_active=False,            # cannot sign in
        is_admin=False,
    )
    db.add(user)
    db.flush()
    return user


ARTICLES = [
    # ── 1. Energy drinks ─────────────────────────────────────────────────────
    {
        "title": "FSSAI Just Took “Energy Drink” Off the Label. If You Sell Caffeine, Read This.",
        "slug": "fssai-energy-drink-label-ban-2026",
        "cat": ("FSSAI Compliance", "fssai-compliance"),
        "tags": "FSSAI, energy drinks, caffeine, labelling, health claims, enforcement",
        "meta_title": "FSSAI Energy Drink Label Ban 2026 — What Changed | Regbite",
        "meta_description": "FSSAI has told high-caffeine beverage makers to drop the words 'energy drink' and give them 90 days. Navneet, Regbite's Chief Regulatory Expert, on what actually changed and who else is exposed.",
        "excerpt": "In July 2026 FSSAI told makers of high-caffeine beverages to stop calling them energy drinks — and gave them 90 days. The drinks were not banned. The word was. That distinction is the whole lesson.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>In July 2026, FSSAI told companies selling high-caffeine beverages in India to stop using the words <strong>“energy drink”</strong> on their packaging. Reporting at the time put the compliance window at <strong>90 days</strong> from a meeting between the regulator and industry executives. PepsiCo's Sting, Red Bull, Monster, Reliance's Campa Energy and Hell Energy were all named in coverage of the directive.</p>

<p>Almost every headline I read got the story slightly wrong. So let me be precise about what happened, because the precision is the point.</p>

<h2>The drinks were not banned. The description was.</h2>

<p>This is not a product withdrawal. Those beverages remain legal to manufacture and sell. What FSSAI objected to was the <em>descriptor</em> and the <em>claims travelling with it</em>.</p>

<p>The regulator's stated reasoning was simple: India has no defined standard for a product category called an “energy drink.” If there is no standard, there is no lawful basis for the term on a label — and a term with no standard behind it becomes, in the regulator's view, a claim. Alongside it, FSSAI objected to claim language about boosting the body or mind, or relieving general weakness.</p>

<p>So the products must be sold under the caffeinated-beverage standards that actually exist, with the caffeine limits and warning requirements attached to that category — rather than under a marketing label that exists only in advertising.</p>

<h2>Why this should worry nutraceutical brands, not just beverage brands</h2>

<p>I have spent three years building Regbite's rule base, and if you watch FSSAI long enough you stop reading enforcement as a series of unrelated events and start reading it as a pattern. The pattern here is one I see constantly in supplements:</p>

<p><strong>A category name that implies a benefit is treated as a health claim.</strong></p>

<p>Think about how much of the supplement shelf is built on exactly that move. “Immunity booster.” “Fat burner.” “Brain health formula.” “Detox.” “Stamina support.” None of these are defined product categories under the FSS (Health Supplements, Nutraceuticals, Food for Special Dietary Use…) Regulations, 2022. They are marketing descriptors that carry an implied physiological benefit.</p>

<p>The energy drink direction is FSSAI demonstrating that it will act on that construction — that if your <em>category name itself</em> promises an outcome, the regulator can treat the name as an unsubstantiated claim, independent of anything in your ingredient list.</p>

<p>If you sell a product whose category descriptor does the selling, you are exposed to the same reasoning.</p>

<h2>What I would do this month if I were you</h2>

<ol>
<li><strong>Separate your product category from your benefit claim.</strong> The category should describe what the product <em>is</em> (a health supplement, a food for special dietary use), not what it promises to do. Move the benefit into a substantiated structure–function claim where it belongs.</li>
<li><strong>Audit the front of pack, not the back.</strong> In almost every enforcement action I have reviewed, the problem was on the principal display panel — the part designed by marketing, not the part reviewed by regulatory.</li>
<li><strong>Check your e-commerce listings separately.</strong> Your Amazon and Flipkart titles are label claims in the regulator's eyes. I regularly find brands whose physical label is clean and whose marketplace title is not.</li>
<li><strong>Write down the substantiation for every claim before you need it.</strong> If you cannot produce the dossier within the response window of a show-cause notice, having the science is the same as not having it.</li>
</ol>

<h2>The 90-day window is the part people underestimate</h2>

<p>Ninety days sounds generous until you cost it out. Artwork revision, regulatory sign-off, printer lead times, existing packaging stock, marketplace listing updates across every SKU and every platform. For a brand with thirty SKUs, ninety days is tight. For a brand that finds out on day sixty because nobody was watching the notifications page, it is not enough.</p>

<p>That is the specific problem we built Regbite to remove. Our engine monitors FSSAI publications and maps each change against your actual product portfolio, so the alert you get names <em>your</em> SKU and <em>your</em> ingredient rather than linking a forty-page PDF. Our claim validator flags exactly the class of language at issue here — category descriptors that function as unsubstantiated health claims — before the artwork goes to print, not after a notice arrives.</p>

<p>The brands that will handle this well are not the ones with the best lawyers. They are the ones who knew on day one instead of day sixty.</p>

<hr>
<p><em>This article summarises regulatory developments reported in July 2026 and is general guidance, not legal advice. Verify the operative text of any FSSAI direction against the notification on fssai.gov.in before making label decisions.</em></p>
""",
    },

    # ── 2. Liquor crackdown ─────────────────────────────────────────────────
    {
        "title": "Old Monk, Royal Challenge, Bagpiper: What the Liquor Crackdown Should Teach Supplement Brands",
        "slug": "fssai-liquor-crackdown-lesson-supplement-brands-2026",
        "cat": ("FSSAI Compliance", "fssai-compliance"),
        "tags": "FSSAI, alcoholic beverages, labelling deadline, enforcement, Old Monk",
        "meta_title": "FSSAI Liquor Crackdown 2026 — The Lesson for Supplement Brands | Regbite",
        "meta_description": "FSSAI extended the alcohol labelling deadline to 1 July 2026, then prohibited select variants of Old Monk, Royal Challenge and Bagpiper. Navneet on why an extension is not amnesty.",
        "excerpt": "FSSAI moved the alcoholic beverage labelling deadline from January to July 2026. Weeks after it passed, select variants of Old Monk, Royal Challenge, Antiquity Blue and Bagpiper were prohibited. There is a lesson in that sequence.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>In August 2026, FSSAI prohibited the sale of select variants of some of the most recognisable liquor brands in India — Old Monk, Royal Challenge, Antiquity Blue and Bagpiper among them. The coverage focused on the brand names, which is understandable. I want to focus on the calendar, because the calendar is where the lesson is.</p>

<h2>The sequence</h2>

<ul>
<li>The FSS (Alcoholic Beverages) Standards were amended, with provisions on product standards, composition and quality parameters taking effect <strong>1 January 2026</strong>.</li>
<li>The <em>labelling</em> provisions were originally to be enforced from <strong>1 January 2026</strong> as well — then pushed to <strong>1 July 2026</strong> by a Direction dated <strong>27 November 2025</strong>.</li>
<li>The extension existed for a practical reason. Alcoholic beverage labels also have to clear state excise registration, which typically happens at the start of the excise year — 1 April or 1 July. Enforcing a January date would have forced the industry to print labels, discard them, reprint and re-register.</li>
<li>Weeks after the extended deadline passed, enforcement action followed.</li>
</ul>

<h2>An extension is not amnesty. It is a countdown with a new end date.</h2>

<p>I have watched this misunderstanding cost brands real money for three years. A deadline gets extended, and somewhere between the notification and the factory floor the message becomes “this got dropped.” It did not get dropped. It got rescheduled — and the regulator now has a documented record that industry asked for more time and received it, which makes the eventual enforcement considerably easier to justify.</p>

<p>If anything, an extension makes the post-deadline period <em>more</em> dangerous, not less. The regulator has already absorbed the argument that compliance was operationally difficult and has already granted relief for it. That argument is spent.</p>

<h2>Where nutraceutical brands are sitting on the same trap right now</h2>

<p>The supplement industry has its own set of dates that have moved, and I find brands treating them the same way:</p>

<ul>
<li><strong>Labelling amendments with transition windows.</strong> Every time FSSAI grants a transition period for a new declaration, a portion of the market treats the transition period as optional. It is not — it is the period during which non-compliance is tolerated, and it ends.</li>
<li><strong>Ingredient limit revisions with reformulation windows.</strong> A four-month window to reformulate assumes you started in month one. Most brands start in month three, discover their supplier cannot deliver the revised grade in time, and then need an extension that will not come.</li>
<li><strong>Category-specific standards that arrive quietly.</strong> Composition standards frequently commence before labelling provisions do, exactly as they did here. Brands read the labelling date, miss the composition date, and are non-compliant on formulation while their label is still legal.</li>
</ul>

<p>That last one is the sharpest edge, and it is precisely what happened in the alcohol timeline above: two different commencement dates inside one amendment.</p>

<h2>The operational fix</h2>

<p>You do not need a bigger regulatory team. You need a list — of every FSSAI date that applies to your specific SKUs, with the date it commences and the date your artwork actually changes, reviewed monthly.</p>

<p>Most brands do not have that list. They have a consultant who calls once a month and a WhatsApp group where someone occasionally forwards a circular. That is how a rescheduled deadline becomes an enforcement action.</p>

<p>Building and maintaining that list for every customer is essentially what Regbite does. We track commencement dates per provision rather than per notification — because as the alcohol amendment shows, one notification can carry several different dates — and map each one to the SKUs in your portfolio it actually touches. When a deadline moves, the date on your dashboard moves with it, and the reminder still arrives.</p>

<p>The brands that got caught in August were not unaware the rules existed. They were working from a date that had changed.</p>

<hr>
<p><em>This article summarises regulatory developments reported between November 2025 and August 2026 and is general guidance, not legal advice. Alcoholic beverages are also governed by state excise law, which is outside FSSAI's remit and outside Regbite's coverage.</em></p>
""",
    },

    # ── 3. Protein supplements ──────────────────────────────────────────────
    {
        "title": "FSSAI Is Coming for Protein Supplements. Fix These Four Things First.",
        "slug": "fssai-protein-supplement-crackdown-2026",
        "cat": ("Nutraceuticals", "nutraceuticals"),
        "tags": "FSSAI, protein supplements, nutrition claims, label accuracy, nitrogen spiking",
        "meta_title": "FSSAI Protein Supplement Crackdown 2026 — What to Fix | Regbite",
        "meta_description": "FSSAI is preparing stricter rules for protein supplements after finding questionable claims and inaccurate nutrition data. Navneet on the four things to fix before the notification lands.",
        "excerpt": "FSSAI has signalled stricter regulation of protein supplements following a study that found questionable health claims and inaccurate nutritional information on products sold in stores, gyms and online. Here is what to fix while it is still cheap.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>FSSAI has signalled that it intends to tighten the rules around protein supplements — particularly those making unauthorised medical or health claims, and those whose declared nutritional information does not survive testing. The trigger was a study finding that a meaningful share of products on store shelves, in gyms and on e-commerce platforms carried questionable claims or inaccurate nutrition data.</p>

<p><strong>An important caveat before you act on anything below:</strong> at the time of writing this is a stated regulatory intent, not a notified regulation. There is no gazette notification you can read, no clause number to cite and no compliance deadline. Anyone telling you otherwise is selling you something.</p>

<p>But I have watched enough of these cycles to tell you what the notified version usually looks like — and every item below is <em>already</em> required or already defensible under the existing framework. So you lose nothing by fixing them now, and you gain a head start measured in months.</p>

<h2>1. Your declared protein has to survive a lab test</h2>

<p>The single most common finding in protein testing studies is that declared protein exceeds measured protein. Sometimes that is sloppy formulation. Sometimes it is nitrogen spiking — adding cheap non-protein nitrogen sources so a Kjeldahl test reads higher than the true protein content.</p>

<p>Kjeldahl measures nitrogen and infers protein. It cannot distinguish protein nitrogen from free amino acid or other added nitrogen. If your supplier's certificate of analysis uses Kjeldahl alone, you do not actually know your protein content — you know your nitrogen content.</p>

<p><strong>What to do:</strong> get batch-level testing from an NABL-accredited laboratory, and ask specifically whether the method distinguishes true protein. If your contract manufacturer resists that question, you have learned something important about your supply chain.</p>

<h2>2. Every claim needs a dossier that exists today, not one you could assemble</h2>

<p>Under the 2022 nutraceutical framework, structure–function claims require substantiation you can produce on request. In practice, most brands I audit can describe their substantiation but cannot hand it over. During a show-cause response window, those are the same thing.</p>

<p><strong>What to do:</strong> for each on-pack claim, keep one file containing the claim as worded, the evidence relied on, and who approved it. If the claim strays anywhere near treating, preventing or curing a condition, it is a drug claim and it does not belong on a food label at all — that is the boundary that turns a labelling problem into a Drugs and Cosmetics Act problem.</p>

<h2>3. The amino acid profile is not optional decoration</h2>

<p>If you are declaring a profile, it has to match the product. If you are declaring protein quality — PDCAAS or DIAAS — the figure needs to correspond to the blend you actually shipped, not the blend you formulated on paper before your supplier substituted a cheaper input.</p>

<p><strong>What to do:</strong> reconcile your declared profile against incoming raw material CoAs every time a supplier or grade changes. Most divergence I find is not fraud. It is a formulation change that never made it back to the artwork.</p>

<h2>4. Your marketplace listing is a label</h2>

<p>I will keep repeating this because brands keep being surprised by it. The claims in your Amazon title, your Flipkart bullet points and your own product page are treated as label claims. A clean physical label and a non-compliant listing is still a non-compliant product.</p>

<p><strong>What to do:</strong> audit listings on the same cycle as artwork. In my experience the listing is usually worse, because it is edited by whoever runs performance marketing and never goes past regulatory.</p>

<h2>Why acting before the notification is the cheap option</h2>

<p>When a regulation is notified, you get a transition window — typically three to six months. That window has to absorb reformulation, retesting, artwork revision, printing, existing stock and every marketplace listing you own. Brands that begin in the window rarely finish inside it.</p>

<p>Brands that fixed the underlying accuracy problems beforehand spend the transition window updating artwork, which is the only part that genuinely requires the final notified text.</p>

<p>This is the reasoning behind how we built Regbite's checks: the engine tests your label against the 64 rules in force today across FSSAI, Legal Metrology and AYUSH, and every finding cites the specific rule code it came from so you can verify it rather than take our word for it. When the protein rules are notified, they become new rules in the same engine and your portfolio is re-scored against them automatically — you do not start from a blank page.</p>

<p>The brands that will struggle are the ones whose declared numbers were never quite right. That is not a labelling problem you can fix with artwork.</p>

<hr>
<p><em>This article discusses regulatory intent reported in 2026. No protein-specific regulation had been notified at the time of writing. This is general guidance, not legal advice.</em></p>
""",
    },

    # ── 4. FOPNL ────────────────────────────────────────────────────────────
    {
        "title": "Front-of-Pack Labelling Has Been “Coming Soon” Since 2022. Here's What to Actually Do About It.",
        "slug": "fssai-front-of-pack-labelling-fopnl-2026",
        "cat": ("Regulatory Intelligence", "regulatory-intelligence"),
        "tags": "FSSAI, FOPNL, front of pack, Health Star Rating, HFSS, labelling",
        "meta_title": "FSSAI Front-of-Pack Labelling (FOPNL) 2026 Status | Regbite",
        "meta_description": "FSSAI's front-of-pack labelling draft has been pending since 2022 with 14,000+ comments. A Parliamentary panel has now pushed for finalisation. Navneet on what to prepare and what to ignore.",
        "excerpt": "The FOPNL draft has been pending since September 2022 under more than 14,000 stakeholder comments. A Parliamentary committee has now urged FSSAI to finalise it. Here is how to prepare without guessing at text that does not exist yet.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>Front-of-Pack Nutrition Labelling is the longest-running “about to happen” in Indian food regulation. The draft was released in <strong>September 2022</strong>. It attracted more than <strong>14,000 stakeholder comments</strong>. Those comments have been under examination ever since.</p>

<p>In 2026 a Parliamentary committee urged FSSAI to finalise and notify the regulations within a defined timeline, criticising the delay directly. That is the most concrete movement this file has seen in years — but I want to be careful with you: <strong>a Parliamentary committee urging action is not a notification.</strong> There is still no operative text, no symbol specification you can design to, and no commencement date.</p>

<p>So the useful question is not “when will it land.” It is “what can I do now that will not be wasted if the final text differs from the draft?”</p>

<h2>What is reasonably settled</h2>

<p>Across the draft and the surrounding policy direction, a few things have been consistent enough to plan around:</p>

<ul>
<li><strong>Something goes on the front of pack.</strong> Whether it is a Health Star Rating, a warning symbol, or a hybrid, the principal display panel is losing space.</li>
<li><strong>The trigger is nutrient thresholds</strong> — total sugar, sodium and saturated fat, assessed per serving or per 100g.</li>
<li><strong>Salt, sugar and fat declarations are being pushed toward greater prominence</strong>, including bolder and larger type in the nutrition panel.</li>
<li><strong>It is aimed at HFSS products</strong> — high in fat, salt or sugar.</li>
</ul>

<h2>What is genuinely unsettled — and where I would not spend money yet</h2>

<ul>
<li>The <em>symbol system</em> itself. Health Star Rating and warning labels imply very different artwork. Designing final packaging to either one right now is a gamble.</li>
<li>The exact <em>thresholds</em>. These moved between drafts and are the single most lobbied element.</li>
<li>The <em>size and placement</em> specification, which determines how much of your front panel you lose.</li>
<li>Whether, and how, it applies to <em>nutraceuticals and health supplements</em> specifically rather than general packaged food. This is the question I get asked most and the one with the least clarity.</li>
</ul>

<h2>What I would actually do in the next quarter</h2>

<ol>
<li><strong>Calculate where every SKU sits against the draft thresholds.</strong> Not to design artwork — to find out which products would carry a mark. If a product is comfortably under, FOPNL is a non-event for it. Knowing which of your SKUs are the problem is most of the work, and that analysis holds regardless of which symbol system wins.</li>
<li><strong>Reformulate the marginal ones now.</strong> If a SKU sits just over a threshold, reformulation is a product decision with a long lead time. Starting it after notification means carrying a mark for a year while you fix it. Flavoured protein powders, gummies and anything with added sugar are where I find the marginal cases.</li>
<li><strong>Leave space in your artwork template.</strong> Not a designed symbol — space. Front panels are already crowded with your product name, the FSSAI licence number, the veg/non-veg mark and the “NOT FOR MEDICINAL USE” statement. The brands that will scramble are those with no room left.</li>
<li><strong>Do not buy a “FOPNL-ready” service that claims to know the final rules.</strong> Nobody does. Anyone selling certainty here is selling you a guess.</li>
</ol>

<h2>The honest position</h2>

<p>I would rather tell you that a rule is uncertain than have you reprint packaging twice. A regulatory adviser whose every answer is “this is coming, act now” is not giving you intelligence — they are giving you urgency, which is a different product.</p>

<p>What Regbite does here is narrower and, I think, more useful: we track this file and tell you when the status actually changes, rather than when someone writes an article speculating that it might. If and when FOPNL is notified, it becomes a rule in the engine, your portfolio is scored against it, and you get told which of your SKUs carry a mark — with the threshold calculation shown, so your formulation team can argue with it.</p>

<p>Until then, the useful work is knowing your numbers. That part you can do today, and it will not be wasted whichever way the final text goes.</p>

<hr>
<p><em>Status as at August 2026: FOPNL remains un-notified. This article is general guidance, not legal advice, and should be re-checked against fssai.gov.in before any packaging decision.</em></p>
""",
    },
]


def seed_trending_posts(db) -> dict:
    """Idempotent by slug. Safe to call on every startup."""
    author = _get_author(db)
    created, skipped = [], []

    for art in ARTICLES:
        if db.query(BlogPost).filter(BlogPost.slug == art["slug"]).first():
            skipped.append(art["slug"])
            continue

        cat_name, cat_slug = art["cat"]
        cat = db.query(BlogCategory).filter(BlogCategory.slug == cat_slug).first()
        if not cat:
            cat = BlogCategory(name=cat_name, slug=cat_slug)
            db.add(cat)
            db.flush()

        db.add(BlogPost(
            title=art["title"],
            slug=art["slug"],
            excerpt=art["excerpt"],
            content=art["content"],
            status=BlogPostStatus.PUBLISHED,
            category_id=cat.id,
            author_id=author.id,
            tags=art["tags"],
            meta_title=art["meta_title"],
            meta_description=art["meta_description"],
            is_featured=False,
            published_at=datetime.utcnow(),
        ))
        created.append(art["slug"])

    db.commit()
    return {"created": created, "skipped": skipped, "author": author.name}
