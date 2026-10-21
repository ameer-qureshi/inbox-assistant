"""30 fictional emails for the demo, with the expected label of each one.

`hours_ago` keeps the data fresh: a part of it is always "today".
`expected` is the ground truth used by the AI evaluation script.
"""

ME = "me@demo-inbox.example"

# (key, thread, hours_ago, from_name, from_address, subject, body, expected_category, expected_priority)
EMAILS: list[dict] = [
    # --- clients ---
    dict(k="c1", t="t-acme", h=2, n="Sophie Bernard", a="sophie.bernard@acme-retail.example",
         s="Urgent: website down since this morning",
         b="Hello,\n\nOur online shop has been showing an error 500 since 8am. We are losing sales. "
           "Can you look at it today? You can call me on 06 12 34 56 78.\n\nSophie", c="client", p=1),
    dict(k="c1r", t="t-acme", h=1.5, n="Me", a=ME, out=True,
         s="Re: Urgent: website down since this morning",
         b="Hi Sophie, I'm on it, I'll update you within the hour.", c=None, p=None),
    dict(k="c1b", t="t-acme", h=0.5, n="Sophie Bernard", a="sophie.bernard@acme-retail.example",
         s="Re: Urgent: website down since this morning",
         b="Thanks. It still does not work on mobile. Any news?", c="client", p=1),
    dict(k="c2", t="t-quote", h=5, n="Marc Dubois", a="marc.dubois@dubois-btp.example",
         s="Request for a quote: new customer portal",
         b="Good morning,\n\nWe would like a quote for a customer portal (login, documents, "
           "invoices). Budget around 15k. Could we talk this week?\n\nMarc Dubois", c="client", p=2),
    dict(k="c3", t="t-feedback", h=26, n="Laura Chen", a="laura@chenstudio.example",
         s="Feedback on the new mockups",
         b="Hi! The team loved the new mockups. Two small changes: bigger logo, and the blue "
           "should be a bit darker. No rush, next week is fine.", c="client", p=2),
    dict(k="c4", t="t-thanks", h=30, n="Paul Lefèvre", a="paul.lefevre@lefevre-avocats.example",
         s="Thank you for the delivery",
         b="Just a quick note to say thank you, everything works perfectly. Have a nice day!",
         c="client", p=3),
    dict(k="c5", t="t-access", h=4, n="Nadia Rahmani", a="nadia@greenleaf.example",
         s="Cannot log in to the admin panel",
         b="Hello, since the update I cannot log in to the admin panel, the password reset "
           "email never arrives. Our team needs it for tomorrow's launch.", c="client", p=1),
    dict(k="c6", t="t-contract", h=50, n="Thomas Girard", a="t.girard@girard-conseil.example",
         s="Contract renewal for 2027",
         b="Hello,\n\nOur maintenance contract ends in December. Can you send the renewal "
           "proposal before the end of the month?\n\nThomas", c="client", p=2),
    # --- invoices ---
    dict(k="i1", t="t-inv-ovh", h=3, n="Billing - CloudHost", a="billing@cloudhost.example",
         s="Invoice CH-2026-10-4471 available",
         b="Your invoice CH-2026-10-4471 of 89.90 EUR is available in your account. It will be "
           "charged automatically on 25/10.", c="invoice", p=3),
    dict(k="i2", t="t-inv-late", h=6, n="Accounting - Imprimerie Lumière",
         a="compta@imprimerie-lumiere.example", s="Reminder: unpaid invoice F-2026-0912",
         b="Hello,\n\nUnless we are mistaken, invoice F-2026-0912 (1 250.00 EUR, due 30/09) is "
           "still unpaid. Please transfer to IBAN FR76 3000 6000 0112 3456 7890 189 within "
           "7 days.\n\nRegards", c="invoice", p=1),
    dict(k="i3", t="t-inv-freelance", h=28, n="Julie Morel", a="julie.morel.design@example.com",
         s="My invoice for September",
         b="Hi, please find my invoice for September's design work (12 days). Payment by "
           "transfer as usual. Thanks!", c="invoice", p=2),
    dict(k="i4", t="t-inv-quote", h=72, n="Sales - OfficePro", a="sales@officepro.example",
         s="Your quote Q-88231 for office chairs",
         b="As requested, here is quote Q-88231 for 6 ergonomic chairs. The offer is valid "
           "for 30 days.", c="invoice", p=3),
    # --- appointments ---
    dict(k="a1", t="t-meet", h=1, n="Claire Fontaine", a="claire.fontaine@acme-retail.example",
         s="Meeting tomorrow at 10am?",
         b="Hi, can we meet tomorrow at 10am to review the Q4 roadmap? Otherwise Thursday "
           "afternoon works too. Let me know.", c="appointment", p=1),
    dict(k="a2", t="t-dentist", h=8, n="Cabinet Dentaire Saint-Michel",
         a="rdv@dentaire-saintmichel.example", s="Reminder: your appointment on 22/10 at 9:30",
         b="Reminder of your appointment on Thursday 22/10 at 9:30. To cancel, call "
           "01 23 45 67 89 at least 24h in advance.", c="appointment", p=3),
    dict(k="a3", t="t-interview", h=20, n="Hugo Martin", a="hugo.martin@talentup.example",
         s="Interview slot for the developer position",
         b="Hello, I'd like to schedule the interview with our candidate. Would Monday 26/10 at "
           "2pm or Tuesday 27/10 at 11am suit you?", c="appointment", p=2),
    dict(k="a3r", t="t-interview", h=18, n="Me", a=ME, out=True,
         s="Re: Interview slot for the developer position",
         b="Hi Hugo, Tuesday 27/10 at 11am is perfect.", c=None, p=None),
    dict(k="a3b", t="t-interview", h=7, n="Hugo Martin", a="hugo.martin@talentup.example",
         s="Re: Interview slot for the developer position",
         b="Great, confirmed for Tuesday 11am. I'll send the video link the day before.",
         c="appointment", p=3),
    dict(k="a4", t="t-webinar", h=48, n="Events - DevConf", a="events@devconf.example",
         s="Your registration: webinar on 29/10",
         b="Your registration for the 'Scaling APIs' webinar on 29/10 at 6pm is confirmed. "
           "Add it to your calendar.", c="appointment", p=3),
    # --- newsletters ---
    dict(k="n1", t="t-nl1", h=9, n="Tech Weekly", a="newsletter@techweekly.example",
         s="This week: 10 Python tips, new JS frameworks",
         b="Welcome to Tech Weekly #212. In this issue: 10 Python tips, a review of new JS "
           "frameworks, and our job board. Unsubscribe at any time.", c="newsletter", p=3),
    dict(k="n2", t="t-nl2", h=33, n="Design Digest", a="hello@designdigest.example",
         s="October inspiration: 25 landing pages",
         b="Our monthly selection of the best landing pages, color palettes and free fonts. "
           "You receive this email because you subscribed.", c="newsletter", p=3),
    dict(k="n3", t="t-nl3", h=55, n="Shop Deals", a="promo@shopdeals.example",
         s="-30% on everything this weekend only",
         b="Our autumn sale is here: -30% on the whole catalogue until Sunday midnight. "
           "Click to discover the offers.", c="newsletter", p=3),
    # --- probable spam ---
    dict(k="s1", t="t-spam1", h=4.5, n="Security Team", a="security@paypa1-verify.example",
         s="Your account will be suspended",
         b="We detected unusual activity. Confirm your identity within 24 hours by entering "
           "your card number at http://paypa1-verify.example/login or your account will be "
           "closed.", c="spam", p=3),
    dict(k="s2", t="t-spam2", h=27, n="Mr. Johnson", a="johnson.lawyer@inheritance-fund.example",
         s="Inheritance of 4.5 million dollars",
         b="Dear friend, I am a lawyer and a late client left 4.5 million dollars without heir. "
           "I need your bank details to transfer your share.", c="spam", p=3),
    dict(k="s3", t="t-spam3", h=60, n="SEO Expert", a="growth@rank-first-now.example",
         s="Get #1 on Google in 7 days guaranteed",
         b="Hi, I checked your website. Pay 99$ and I guarantee first page on Google in 7 days. "
           "Reply YES to start.", c="spam", p=3),
    # --- other ---
    dict(k="o1", t="t-github", h=10, n="GitHub", a="noreply@github.example",
         s="[inbox-assistant] CI failed on main",
         b="The workflow 'tests' failed on branch main (commit 4f2a9c1). View the logs for "
           "details.", c="other", p=2),
    dict(k="o2", t="t-hr", h=24, n="HR - People Team", a="people@mycompany.example",
         s="Please submit your holiday requests",
         b="Reminder: holiday requests for December must be submitted in the HR tool before "
           "31/10.", c="other", p=2),
    dict(k="o3", t="t-friend", h=12, n="Léa Petit", a="lea.petit@example.org",
         s="Dinner Saturday?",
         b="Hey! We're organising a dinner at our place on Saturday night, are you in? Bring "
           "dessert if you can :)", c="other", p=3),
    dict(k="o4", t="t-delivery", h=40, n="Parcel Service", a="tracking@parcel-service.example",
         s="Your parcel has been delivered",
         b="Your parcel 7781-2290 was delivered today at 11:42 to your mailbox.", c="other", p=3),
    dict(k="o5", t="t-domain", h=3.5, n="DomainRegistry", a="renewals@domainregistry.example",
         s="Your domain expires in 5 days",
         b="The domain demo-inbox.example expires on 24/10. Renew it now to avoid any "
           "interruption of your website and emails.", c="other", p=1),
    dict(k="o6", t="t-survey", h=80, n="Customer Care - Telco", a="survey@telco.example",
         s="How was your experience?",
         b="Thanks for contacting our support. Please rate your experience in 1 click.",
         c="other", p=3),
]

assert len(EMAILS) == 30
