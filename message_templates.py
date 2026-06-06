CONNECTION_REQUEST_NOTE = (
    "Hi {first_name}, I'm Prashil from Storylane! "
    "I noticed your recent post about us and loved it. "
    "Would love to connect and chat about a potential collaboration."
)

INFLUENCER_PITCH_MESSAGE = """Hi {first_name}! 👋

Thanks so much for connecting — and again, really appreciated your LinkedIn post about Storylane. It clearly resonated with your audience.

We're building out a **Customer Influencer Program** and I think you'd be a great fit. Here's the idea:

- You create LinkedIn posts sharing your experience with Storylane (authentic takes, tips, use cases — whatever feels natural to you)
- We track impressions and engagement on each post
- You get **paid per post based on performance** (similar to the $100/1K impressions structure from before, but with better rates for our influencers)
- We also amplify your content through our channels

The people who did best in our last campaign had posts that felt genuine and shared specific wins. I'd love to learn more about how you use Storylane and explore what a longer-term partnership could look like.

Would you be open to a quick 15-min chat this week?"""

FOLLOW_UP_MESSAGE = """Hey {first_name}, just following up on my earlier message about Storylane's Customer Influencer Program.

Totally understand if the timing isn't right — but if you're interested, I'd love to set up a quick call. No pressure at all!"""

HIGH_POTENTIAL_PITCH = """Hi {first_name}! 👋

Thanks for connecting! I came across your profile and your content around {topic_area} is really impressive.

I'm Prashil from Storylane — we help companies build interactive product demos. Given your audience and expertise in {topic_area}, I think there could be a really interesting collaboration opportunity.

We're launching a Customer Influencer Program where select creators share authentic content about tools they use, and get compensated based on post performance.

Would love to chat for 15 mins if you're open to it — I think this could be a great fit for your audience."""


def format_message(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
