"""Scripted meetings used to generate seed audio.

These are invented conversations between invented people at an invented company.
No real person, recording, or company data is involved.

They are written to sound like real meetings rather than clean demo scripts:
people interrupt, correct themselves, use filler words, quote real numbers, and
occasionally commit to things vaguely. That matters — a transcript that reads too
tidily is the fastest way to make a demo look fake, and a summariser that has only
seen tidy input has not really been tested.

Voice mapping uses the three SAPI voices Windows ships with, which are distinct
enough for the diarizer to separate: David (male, US), Hazel (female, GB),
Zira (female, US).
"""

from __future__ import annotations

VOICES = {
    "rahul": "Microsoft David Desktop",
    "priya": "Microsoft Hazel Desktop",
    "sneha": "Microsoft Zira Desktop",
}

# Slight rate differences make the voices easier to tell apart, and real people
# don't all talk at the same speed. SAPI rate is -10..10.
RATES = {"rahul": 0, "priya": 1, "sneha": -1}


SPRINT_STANDUP = {
    "slug": "sprint-standup",
    "title": "",  # left blank on purpose: the AI names this one
    "lines": [
        ("priya", "Okay, let's start. Rahul, where are we on the payments API?"),
        ("rahul", "So, the endpoints are done. Both of them. But I hit a problem with the auth layer yesterday."),
        ("priya", "What kind of problem?"),
        (
            "rahul",
            "The token refresh. When two requests come in at the same time, both of them try to refresh, "
            "and one gets rejected. So the user gets logged out randomly.",
        ),
        ("sneha", "Oh, that's the thing I saw on staging last week. I thought it was my network."),
        ("rahul", "No, it's a real bug. I know how to fix it, I just need a day."),
        ("priya", "Is that going to push the Friday deadline?"),
        (
            "rahul",
            "Honestly? Yes. If I fix the refresh thing properly, payments slips to Monday. "
            "I can do a quick patch by Friday but it will break again.",
        ),
        ("priya", "No, don't patch it. Do it properly. I would rather ship Monday than debug this again in production."),
        ("rahul", "Okay. Then I will take Monday for payments."),
        ("priya", "Sneha, what about the dashboard?"),
        (
            "sneha",
            "Dashboard is mostly done. The charts are rendering, filters work. "
            "But I am blocked on the analytics endpoint. I need the aggregated numbers from the backend.",
        ),
        ("rahul", "That's on me too. I can get you a stub by tomorrow with fake numbers so you can keep going."),
        ("sneha", "Yes please. That unblocks me completely."),
        ("priya", "Good. Sneha, can you have the dashboard ready for review by Thursday?"),
        ("sneha", "If I get the stub tomorrow, then yes, Thursday works."),
        ("priya", "Okay. One more thing. The client asked about the export feature."),
        ("sneha", "Export to what? CSV?"),
        ("priya", "CSV and PDF. They want both."),
        (
            "rahul",
            "PDF is a lot of work. That's not a two day thing. If they want PDF we need to add it to the next sprint, "
            "not this one.",
        ),
        ("priya", "That's fair. I will tell them CSV this sprint, PDF next sprint. Rahul, is CSV doable?"),
        ("rahul", "CSV is easy. Half a day. But not this week, I am full."),
        ("sneha", "I can do the CSV export. It's mostly frontend anyway."),
        ("priya", "Perfect. Sneha takes CSV export. Let's target next Wednesday for that."),
        ("sneha", "Next Wednesday, noted."),
        ("priya", "Anything else? Any blockers I should know about?"),
        ("rahul", "Just the staging environment. It keeps running out of memory. Someone needs to look at it."),
        ("priya", "I will raise it with infra today. Okay, that's it. Thanks everyone."),
    ],
}


CLIENT_CALL = {
    "slug": "client-call",
    "title": "",
    "lines": [
        ("priya", "Thanks for making the time. I know you had a hard stop, so let's get straight into it."),
        ("sneha", "No problem. We have about twenty five minutes."),
        (
            "priya",
            "So, we walked through your requirements internally. The good news is most of it is straightforward. "
            "The integration is the part I want to talk about.",
        ),
        ("sneha", "The Salesforce integration?"),
        ("priya", "Yes. You mentioned you want it two way. Data going both directions, syncing live."),
        ("sneha", "That's what the team asked for, yes."),
        (
            "rahul",
            "Can I jump in? Two way sync is technically possible but it is genuinely difficult. "
            "The problem is conflicts. If someone edits a record in Salesforce and someone edits the same record "
            "in our system at the same time, which one wins?",
        ),
        ("sneha", "Hmm. I hadn't thought about that."),
        (
            "rahul",
            "Nobody does until it breaks. And when it breaks, it corrupts data silently. "
            "You don't find out for weeks.",
        ),
        ("sneha", "So what do you recommend?"),
        (
            "rahul",
            "One way sync first. Salesforce is the source of truth, data flows into us. "
            "That we can build in about three weeks and it will be reliable. "
            "Then if you actually need two way after using it, we do that as a phase two.",
        ),
        ("sneha", "And how long would phase two be?"),
        ("rahul", "Realistically six to eight weeks. It is a much bigger piece of work."),
        ("sneha", "Okay. Let me take that back to the team. What does that do to the price?"),
        (
            "priya",
            "Phase one, one way sync, stays inside the number we quoted. Eighteen lakhs. "
            "Phase two would be a separate scope and a separate quote.",
        ),
        ("sneha", "And the timeline for everything else? The reporting module, the user management?"),
        ("priya", "Those are unaffected. We are still looking at end of March for the full first release."),
        ("sneha", "End of March. That's what I will tell the board."),
        (
            "priya",
            "One caveat. That assumes we get the API credentials from your IT team. "
            "We asked two weeks ago and we still don't have them.",
        ),
        ("sneha", "Really? I will chase that. Who do I ask?"),
        ("rahul", "It's a sandbox account with API access enabled. Your IT team will know what that means."),
        ("sneha", "Okay. I will get you those credentials by end of this week."),
        ("priya", "That would genuinely help. Every day we wait on that is a day off the March date."),
        ("sneha", "Understood. I will make it a priority."),
        (
            "priya",
            "Great. So to summarise. We go with one way sync for phase one, price stays at eighteen lakhs, "
            "end of March for release, and you get us the credentials this week.",
        ),
        ("sneha", "That's right. And I will come back to you on two way sync after the team discusses it."),
        ("priya", "Perfect. I will send you a written summary of this call today."),
        ("sneha", "Thank you. This was helpful."),
    ],
}


PRODUCT_PLANNING = {
    "slug": "product-planning",
    "title": "",
    "lines": [
        ("sneha", "Right, so the question on the table is what goes into the next quarter."),
        (
            "rahul",
            "Before we prioritise, can I say something about tech debt? We have been pushing features for three "
            "quarters straight. The codebase is getting hard to work in.",
        ),
        ("sneha", "How hard?"),
        (
            "rahul",
            "Things that used to take a day take three. Not because they are complicated, "
            "but because I have to be careful not to break something else.",
        ),
        ("priya", "Do you have a number? Like, how much time would it take to fix?"),
        (
            "rahul",
            "The worst part is the notification system. It's about two weeks to rewrite properly. "
            "After that everything touching notifications gets faster.",
        ),
        ("priya", "Two weeks is a lot in a twelve week quarter."),
        ("rahul", "It is. But we are already losing more than that in slowdown. We just don't measure it."),
        ("sneha", "Okay, I hear you. Let me put it on the list and we will see what it competes with."),
        (
            "sneha",
            "The three big feature asks are: mobile app, the reporting revamp, and single sign on. "
            "Single sign on is coming from enterprise sales.",
        ),
        ("priya", "How many deals are blocked on single sign on?"),
        ("sneha", "Four. Roughly forty lakhs of pipeline."),
        ("priya", "Then that's not really a question, is it? Forty lakhs is more than everything else combined."),
        ("rahul", "Single sign on is not that bad, actually. Two to three weeks if we use an existing library."),
        ("sneha", "Which library?"),
        ("rahul", "I would need to evaluate. There are a few good options. Give me two days to look and I will write it up."),
        ("sneha", "Okay. Rahul evaluates single sign on libraries, writes a recommendation. When?"),
        ("rahul", "By Thursday."),
        ("sneha", "Thursday. Good. Now, mobile app versus reporting revamp."),
        (
            "priya",
            "I want to push back on the mobile app. We have looked at the usage data. "
            "Eighty percent of sessions are desktop, during work hours. Nobody is asking for mobile except one client.",
        ),
        ("sneha", "It's a big client though."),
        (
            "priya",
            "It is. But a mobile app is a whole quarter minimum, and then we maintain it forever. "
            "For one client, that is a bad trade.",
        ),
        ("rahul", "We could make the web app work properly on mobile. That's maybe two weeks, not twelve."),
        ("sneha", "Would that satisfy them?"),
        ("priya", "I think so. When I asked what they actually wanted, they said they want to check things on the go. "
                  "A responsive web app does that."),
        ("sneha", "Okay, that changes things. So the plan is: single sign on, responsive web, notification rewrite, "
                  "and reporting revamp with whatever is left."),
        ("rahul", "That I can live with. That's a real quarter."),
        ("priya", "And no mobile app?"),
        ("sneha", "No mobile app this quarter. I will explain it to the client. Priya, can you pull together the usage "
                  "numbers so I have something concrete to show them?"),
        ("priya", "Yes. I will have that by Monday."),
        ("sneha", "Great. Then we are agreed."),
    ],
}


ALL_MEETINGS = [SPRINT_STANDUP, CLIENT_CALL, PRODUCT_PLANNING]
