"""
2026 FSSAI news posts, one per development, under Navneet's byline.

Kept separate from blog_seed.py so the article bodies do not drown the seeding
logic. blog_seed.ARTICLES extends this list.

Sourcing discipline, same as blog_seed: every date and figure below comes from
reporting or notifications between Feb and Aug 2026, and anything FSSAI has
only proposed is labelled a draft in the body AND in a dated status line at the
foot of the post. Readers make label decisions on this.
"""

NEWS_ARTICLES = [
    # ── Licensing overhaul ──────────────────────────────────────────────────
    {
        "title": "Your FSSAI Licence Is Now Perpetual. That Is Not the Same as Permanent.",
        "slug": "fssai-perpetual-licence-turnover-thresholds-2026",
        "image": "/static/img/blog/blog-licensing.png",
        "cat": ("FSSAI Compliance", "fssai-compliance"),
        "tags": "FSSAI, licensing, FoSCoS, turnover threshold, registration, perpetual licence",
        "meta_title": "FSSAI Perpetual Licence & New Turnover Thresholds 2026 | Regbite",
        "meta_description": "FSSAI licences no longer expire and the registration threshold moved from Rs 12 lakh to Rs 1.5 crore. Navneet on what perpetual validity actually means, and the trap inside it.",
        "excerpt": "Notified 10 March 2026 and effective 1 April, the licensing overhaul ends renewal cycles and lifts the registration ceiling from Rs 12 lakh to Rs 1.5 crore. Both changes are good news. One of them is also a trap.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>The Food Safety and Standards (Licensing and Registration of Food Businesses) Amendment Regulations, 2026 were notified on <strong>10 March 2026</strong>, with the revised turnover thresholds effective from <strong>1 April 2026</strong>. Two things changed that matter to every nutraceutical business in India.</p>

<h2>Licences are now perpetual</h2>

<p>The renewal cycle is gone. Once granted, a licence or registration remains valid indefinitely. It ceases only in three circumstances: <strong>suspension</strong> by the food authority for non-compliance, <strong>cancellation</strong> following a formal proceeding, or <strong>voluntary surrender</strong>.</p>

<p>Here is the part I keep having to repeat: <strong>the annual fee is still payable.</strong> Perpetual validity removed the renewal application, not the money. The fee remains due annually, and may be paid in advance for any number of years.</p>

<p>So the failure mode has changed shape rather than disappeared. It used to be &ldquo;I forgot to renew and my licence expired.&rdquo; Now it is &ldquo;I stopped thinking about my licence entirely because someone told me it was permanent, and nobody has paid the annual fee.&rdquo; The second is quieter, and therefore worse &mdash; nothing prompts you, right up until it becomes a compliance proceeding.</p>

<h2>The turnover thresholds moved a long way</h2>

<ul>
<li><strong>Registration</strong> &mdash; annual turnover up to <strong>&#8377;1.5 crore</strong> (previously &#8377;12 lakh)</li>
<li><strong>State Licence</strong> &mdash; above &#8377;1.5 crore, up to &#8377;50 crore</li>
<li><strong>Central Licence</strong> &mdash; above &#8377;50 crore</li>
</ul>

<p>The registration ceiling went up more than twelvefold. A large number of small supplement brands that were pushed into a State Licence purely by turnover now sit inside Registration.</p>

<h2>Do not downgrade on turnover alone</h2>

<p>This is where I see people about to make an expensive mistake, so let me be direct.</p>

<p>Turnover is <em>one</em> trigger for licence category. It is not the only one. Manufacturing, importing, and operating across more than one state carry their own requirements regardless of how small your revenue is. If you import a single raw material, your turnover figure is not the operative question.</p>

<p>Before anyone in your business &ldquo;downgrades to Registration because we are under &#8377;1.5 crore,&rdquo; have someone confirm that no other trigger applies to your operation. Getting this wrong means operating on the wrong licence class &mdash; which is not a paperwork problem, it is an operating-without-a-valid-licence problem.</p>

<h2>What I would do this quarter</h2>

<ol>
<li><strong>Write down your annual fee date.</strong> Not the renewal date, which no longer exists. The fee date. Put it somewhere that will chase you.</li>
<li><strong>Re-check your licence category against every trigger</strong> &mdash; manufacturing, import, multi-state operation and the product categories you actually handle &mdash; not just turnover.</li>
<li><strong>Update the licence number on your artwork</strong> if your category genuinely changes. The 14-digit number on pack has to match the licence you hold.</li>
<li><strong>Do not read &ldquo;perpetual&rdquo; as &ldquo;handled.&rdquo;</strong> Suspension and cancellation remain live routes, and both are driven by compliance findings elsewhere in your business.</li>
</ol>

<p>Regbite tracks licence categories and fee dates per entity and sends the reminder before the date rather than after. That mattered less when an annual renewal forced everyone to look. It matters considerably more now that nothing does.</p>

<hr>
<p><em>Status as at August 2026. General guidance, not legal advice &mdash; confirm your licence category against the operative notification on fssai.gov.in and your FoSCoS record before acting.</em></p>
""",
    },

    # ── Advertising & Claims ────────────────────────────────────────────────
    {
        "title": "&ldquo;100% Natural&rdquo; Is Now a Liability. FSSAI Finalised the Claims Rules.",
        "slug": "fssai-advertising-claims-amendment-2026",
        "image": "/static/img/blog/blog-claims.png",
        "cat": ("Nutraceuticals", "nutraceuticals"),
        "tags": "FSSAI, advertising, health claims, misleading claims, substantiation, penalties",
        "meta_title": "FSSAI Advertising & Claims Rules 2026 — What You Can No Longer Say | Regbite",
        "meta_description": "FSSAI finalised its Advertising and Claims amendments: absolute claims like '100% natural' are out unless unequivocally substantiated, and penalties reach Rs 10 lakh per offence.",
        "excerpt": "The long-pending draft amendments to the Advertising and Claims Regulation are now final. Absolute claims, medical terminology and unsubstantiated health benefits are all squarely in scope — with penalties up to Rs 10 lakh per offence.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>FSSAI's long-pending draft amendments to the Advertising and Claims Regulation have been published as a final amendment, and enforcement through 2026 has been noticeably sharper. If you sell a supplement in India, this is the single regulatory development most likely to change what is printed on your pack this year.</p>

<h2>Three categories of language are now clearly in scope</h2>

<h3>Absolute claims</h3>
<p>Sweeping superlatives &mdash; <strong>&ldquo;100% pure&rdquo;, &ldquo;100% natural&rdquo;, &ldquo;100% safe&rdquo;</strong> &mdash; are not permitted unless they can be unequivocally substantiated. &ldquo;Unequivocally&rdquo; is doing real work in that sentence. For most formulated supplements a 100% claim is not substantiable in principle, because the product contains excipients, carriers or a capsule shell.</p>

<p>I audit a lot of labels. &ldquo;100% natural&rdquo; on a product containing magnesium stearate and an HPMC capsule is among the most common findings I make &mdash; and now among the most expensive.</p>

<h3>Medical and disease terminology</h3>
<p>Claims that a food can prevent, treat, cure or diagnose a disease, or substitute for medical treatment, are not permitted. The principle has not changed; the enforcement has. The moment your pack makes a disease claim, the regulator can treat your food as an unlicensed drug &mdash; which moves the problem out of the FSS Act and into the Drugs and Cosmetics Act.</p>

<h3>Unsubstantiated health benefits</h3>
<p>This is the one brands most often believe they have covered. <strong>A lab report is necessary but not sufficient.</strong> A certificate of analysis proves what is in the product. It does not prove that what is in the product produces the benefit you are claiming, in the population you are selling to.</p>

<p>What is expected is validated scientific evidence or peer-reviewed literature supporting <em>that specific claim</em> for <em>your target audience</em>. Evidence for a 500 mg dose does not substantiate a claim on your 100 mg product. Evidence in an elderly cohort does not substantiate a claim aimed at athletes.</p>

<h2>The penalty is what changes the arithmetic</h2>

<p>Penalties for misleading advertisement run up to <strong>&#8377;10 lakh per offence</strong> under Section 53 of the FSS Act. Per offence. For a brand with a dozen SKUs each carrying the same non-compliant phrase across pack and marketplace listings, that adds up uncomfortably fast.</p>

<p>That is what has shifted the risk calculus. A phrase that used to be a mild regulatory annoyance is now a line item.</p>

<h2>A three-hour exercise worth doing this week</h2>

<ol>
<li><strong>Export every claim you make.</strong> Pack artwork, website, Amazon and Flipkart titles and bullets, and your ads. One spreadsheet, one row per claim, one column for where it appears.</li>
<li><strong>Flag every absolute.</strong> Search for &ldquo;100%&rdquo;, &ldquo;pure&rdquo;, &ldquo;natural&rdquo;, &ldquo;safe&rdquo;, &ldquo;guaranteed&rdquo;, &ldquo;no side effects&rdquo;, &ldquo;chemical-free&rdquo;. Each needs substantiation or removal.</li>
<li><strong>Flag every disease word.</strong> Diabetes, arthritis, cholesterol, blood pressure, immunity <em>from</em> illness, cure, treat, prevent, heal.</li>
<li><strong>For everything left, name the evidence.</strong> If you cannot put a citation in the next column, that claim is unsubstantiated today &mdash; regardless of whether it happens to be true.</li>
</ol>

<p>Regbite's claim validator runs this pass automatically against your label extraction and flags each phrase with the rule code it offends, so you hand your formulation team a list rather than an opinion. But the first version of that audit is a spreadsheet and an afternoon, and I would rather you did it this week than waited for anything.</p>

<p>The brands that get hurt here will not be the ones making outrageous claims. They will be the ones who wrote &ldquo;100% natural&rdquo; on a pack in 2019 because everyone did, and never revisited it.</p>

<hr>
<p><em>Status as at August 2026. General guidance, not legal advice. Verify the operative amendment text on fssai.gov.in before making label decisions.</em></p>
""",
    },

    # ── Packaging draft ─────────────────────────────────────────────────────
    {
        "title": "FSSAI Is Redefining What Counts as Food Packaging. NIAS Is the Word to Learn.",
        "slug": "fssai-packaging-amendment-nias-2026",
        "image": "/static/img/blog/blog-packaging.png",
        "cat": ("Regulatory Intelligence", "regulatory-intelligence"),
        "tags": "FSSAI, packaging, NIAS, food contact material, rPET, draft regulation",
        "meta_title": "FSSAI Packaging Amendment 2026 — Food Contact Materials & NIAS | Regbite",
        "meta_description": "FSSAI's draft packaging amendment defines food contact material, NIAS, aseptic and modified atmosphere packaging. Navneet on what to do before it is notified.",
        "excerpt": "FSSAI published a draft packaging amendment on 26 February 2026 introducing formal definitions for food contact materials and non-intentionally added substances. It is still a draft — but the direction is unambiguous.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>On <strong>26 February 2026</strong>, FSSAI published a draft amendment to the Food Safety and Standards (Packaging) Regulations, 2018. The 60-day consultation closed on <strong>10 May 2026</strong>.</p>

<p><strong>This is a draft.</strong> It has not been notified, the text can change, and there is no compliance date. I am writing about it anyway because the definitions it introduces show clearly where packaging regulation in India is heading &mdash; and because packaging lead times are long enough that waiting for notification is the expensive option.</p>

<h2>The new vocabulary</h2>

<p>The draft introduces formal definitions for several terms that have been used loosely in the Indian market for years:</p>

<ul>
<li><strong>Food contact material</strong> and <strong>food grade contact material</strong></li>
<li><strong>Food packaging</strong></li>
<li><strong>Modified atmosphere packaging</strong></li>
<li><strong>Aseptic packaging</strong></li>
<li><strong>Non-intentionally added substances (NIAS)</strong></li>
</ul>

<p>The last is the one to pay attention to.</p>

<h2>What NIAS means, and why it is harder than it sounds</h2>

<p>Non-intentionally added substances are exactly what the name says: things that end up in your product from the packaging without anyone deciding to put them there. Reaction by-products, breakdown products from the polymer, residues from printing inks or adhesives, contaminants carried in from the raw material.</p>

<p>The difficulty is structural. You cannot check NIAS against your own recipe, because by definition they are not in it. Establishing what migrates out of a given packaging material into a given product under given storage conditions is a question for your <em>packaging supplier</em> &mdash; and most supplement brands in India have never asked it.</p>

<p>If this draft is notified in anything like its current form, &ldquo;we buy food-grade bottles from a reputable supplier&rdquo; stops being a sufficient answer. You will need something on paper from that supplier.</p>

<h2>On recycled plastic</h2>

<p>Worth knowing alongside this: under the Packaging First Amendment Regulations, 2025 (published 28 March 2025), <strong>recycled PET is the only recycled plastic permitted for food contact</strong>, subject to the conditions FSSAI has notified. If a supplier offers you recycled packaging in any other polymer for a food product, that is a conversation to stop and check.</p>

<h2>What to do while it is still a draft</h2>

<ol>
<li><strong>Ask each packaging supplier what they can document.</strong> Food-grade certification, migration testing, and whether they hold any NIAS assessment at all. The answer tells you how exposed you are, and it costs you an email.</li>
<li><strong>Find out what your bottles and blisters are actually made of.</strong> A surprising number of brands cannot answer this without calling their supplier &mdash; which is itself the finding.</li>
<li><strong>Check any recycled-content packaging against the rPET-only position.</strong></li>
<li><strong>Do not redesign packaging yet.</strong> The text can change. Gathering documentation is useful whatever the final wording; retooling to a draft is not.</li>
</ol>

<p>We track this file in Regbite and will move it from &ldquo;draft&rdquo; to a scored rule the moment it is notified, so your portfolio is re-checked automatically rather than you finding out from a LinkedIn post. Until then the honest status is: watch it, document your supply chain, do not spend money on artwork.</p>

<hr>
<p><em>Status as at August 2026: the packaging amendment remains a draft and has not been notified. General guidance, not legal advice.</em></p>
""",
    },

    # ── Labelling & Display ─────────────────────────────────────────────────
    {
        "title": "FSSAI Set One Labelling Deadline for Everything: 1 July. Here Is Why That Helps You.",
        "slug": "fssai-labelling-display-amendment-2026",
        "image": "/static/img/blog/blog-labelling.png",
        "cat": ("FSSAI Compliance", "fssai-compliance"),
        "tags": "FSSAI, labelling, display, non-retail container, enforcement date, small packs",
        "meta_title": "FSSAI Labelling & Display Amendment 2026 — In Force July 2027 | Regbite",
        "meta_description": "FSSAI's Labelling and Display Amendment was notified 24 March 2026 and comes into force 1 July 2027. Navneet on the annual 1 July enforcement date and what actually changed.",
        "excerpt": "Notified on 24 March 2026 and in force from 1 July 2027, the labelling amendment changes non-retail containers, small-pack logo rules and infant nutrition declarations. The bigger story is the date itself.",
        "content": """<p><em>By Navneet, Chief Regulatory Expert at Regbite</em></p>

<p>The Food Safety and Standards (Labelling and Display) Amendment Regulations, 2026 were notified on <strong>24 March 2026</strong> and come into force on <strong>1 July 2027</strong>. That is a long runway, and I want to talk about the runway before the contents.</p>

<h2>The most useful change is the calendar, not the clauses</h2>

<p>FSSAI has moved toward a <strong>consistent annual labelling enforcement date of 1 July</strong>. New labelling requirements land on that date rather than scattered across the year.</p>

<p>If you have ever run a packaging change in India you will understand immediately why that matters. Artwork revision, regulatory review, printer lead time, minimum order quantities and running down existing stock are all slow. A labelling change commencing in mid-February means either scrapping printed stock or running non-compliant for a few weeks.</p>

<p>A predictable annual date lets you batch. Hold one artwork revision cycle a year, fold every pending change into it, print once. For a brand with thirty SKUs that is the difference between one print run and several.</p>

<p>My advice: <strong>put a standing artwork review in your calendar each January</strong>, covering everything that commences the following 1 July. That single habit will save you more money than any individual clause below.</p>

<h2>What actually changed</h2>

<ul>
<li><strong>Non-retail containers</strong> &mdash; the most substantive change. Mandatory traceability information and clear <strong>&ldquo;NON-RETAIL CONTAINER&rdquo;</strong> identification. If you ship bulk to a packer or contract manufacturer, this is you.</li>
<li><strong>Small packs</strong> &mdash; the FSSAI logo may be omitted where the package surface area is <strong>100 cm&sup2; or less</strong>. The information must still appear on the multi-unit pack. Relevant for sachets, sample sizes and single-serve sticks.</li>
<li><strong>Infant nutrition products</strong> &mdash; no longer required to declare per-serve %RDA contribution or the number of servings per pack.</li>
<li><strong>Minimally processed foods</strong> &mdash; now defined: foods slightly altered for preservation (cleaning, grinding, refrigeration, pasteurisation) without substantially changing nutritional content.</li>
<li><strong>Warnings</strong> &mdash; revised requirements for pan masala and for aspartame&ndash;acesulfame sweetener combinations.</li>
</ul>

<h2>Which of these touch a supplement brand</h2>

<p>Honestly, for most nutraceutical brands: two.</p>

<p><strong>Non-retail containers</strong>, if you move bulk material between sites or send product to a contract packer. The traceability requirement is the substantive one, and it may need changes to how your bulk labels are <em>generated</em>, not just what they say.</p>

<p><strong>Small packs</strong>, if you sell sachets or sample sizes. The 100 cm&sup2; relief is genuinely useful &mdash; it removes a real design constraint from a panel that never had room for the logo in the first place.</p>

<p>The infant nutrition and pan masala provisions will not apply to you unless you are in those categories. I mention them because I would rather you know what a change does <em>not</em> require than assume it applies and spend money on it.</p>

<h2>Between now and July 2027</h2>

<p>You have over a year, which is genuinely comfortable &mdash; provided someone owns the date. In my experience the risk with a long runway is not that the work is hard; it is that nobody starts, and then it is March 2027.</p>

<p>Regbite holds commencement dates per provision rather than per notification, so a change notified in March 2026 that commences in July 2027 sits on your dashboard under the date that actually matters to you, and the reminder arrives in time to act on it.</p>

<hr>
<p><em>Status as at August 2026. General guidance, not legal advice. Confirm the operative text and commencement date on fssai.gov.in before making artwork decisions.</em></p>
""",
    },
]
