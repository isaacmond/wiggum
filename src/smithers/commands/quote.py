"""Secret quote mode - prints sycophantic Smithers quotes."""

import random

from smithers.console import console, print_header

SMITHERS_QUOTES: tuple[str, ...] = (
    # Sycophantic Devotion (Seasons 1-12)
    (
        "Actually, I value every second we're together. From the moment I squeeze his "
        "orange juice in the morning, till I tuck him in at night. He's not just my boss, "
        "he's my best friend too."
    ),
    "Somebody down here likes you too, sir!",
    "May I, sir?",
    "No! Don't make me take a vacation! Without you, I'll wither and die!",
    (
        "Sir, in the spirit of the festival and everything, I'd just like to say that... "
        "I... love you. In those colors!"
    ),
    "You are noble and poetic in defeat, sir.",
    "Oh, you never cease to amaze me, sir.",
    "For the love of God, sir! There are two seats!",
    "Oh, who am I kidding? The boathouse was the time!",
    "You've been reading my wishbook, sir.",
    # Work & Duties
    (
        "Your new duties will include answering Mr. Burns' phone, preparing his tax return, "
        "moistening his eyeballs, assisting with his chewing and swallowing, lying to "
        "Congress, and some light typing."
    ),
    (
        "Now, I realize caring for Mr. Burns seems like a big job... but actually it's "
        "just 2,800 small jobs."
    ),
    (
        "I've got to find a replacement who won't outshine me. Perhaps if I search the "
        "employee evaluations for the word 'incompetent'."
    ),
    (
        "Homer Simpson, sir. One of your organ banks from Sector 7G. All the recent events "
        "of your life have revolved around him in some way."
    ),
    (
        "Mr. Burns can't stand talking to his mother. He never forgave her for having that "
        "affair with President Taft."
    ),
    (
        "Sir, I'm afraid all those players have retired and... passed on. In fact, your "
        "right fielder has been dead for 130 years."
    ),
    (
        "Oh, in the meantime, sir, may I suggest a random firing? Just to throw the fear "
        "of God into them?"
    ),
    (
        "Well, I caught up on my laundry, wrote a letter to my mother, oh, here's a kicker, "
        "and I took Hercules out to be clipped."
    ),
    (
        "Well sir, you have certainly vanquished your enemies. The elementary school, the "
        "local tavern, the old age home. You must be very proud."
    ),
    (
        "Attention Homer Simpson, you have been promoted. You are now an executive. "
        "Take three minutes to say goodbye to your former friends and report to room 503 "
        "for reassignment to a better life."
    ),
    (
        "I let Mr. Burns treat me like a pet. Why do I put up with this? "
        "What am I doing with my life?"
    ),
    # Unflappable Loyalty
    "Right, sir. It's... scalding me as we speak.",
    "But sir, I'm flaming!",
    "I think women and seamen don't mix.",
    "Uh, if you did it, sir?",
    # Exasperation & Wit
    "I'm allergic to bee stings. They cause me to, uh, die.",
    "A little mincing would be nice.",
    "Oh great. It's the Bobbsey Twins. Well, take your prying eyes elsewhere.",
    "Fine, good. I don't care anymore.",
    "Aren't there any healthy animals in this forest?",
    (
        "How could you do this to me, Mr. Burns, after all I've done for you? Why, if you "
        "were here, I'd kick you right in your bony, old behind!"
    ),
    "Damn this common gutter blood in my veins!",
    (
        "There isn't any food in any of these trees. Please, Bart, we've got to hurry! "
        "I can't be the last one to reach the cabin."
    ),
    # Burns' Schemes & Villainy
    (
        "But sir, every plant and tree will die, owls will deafen us with incessant hooting, "
        "the town's sundial will be useless. I don't want any part of this project. "
        "It's unconscionably fiendish."
    ),
    # More Verified Classics
    "This resume is very impressive. Let me be the first to say 'abibu gazini'.",
    "I work for Monty Burns, M-M-M-M-Monty Burns!",
    "People like dogs, Mr. Burns.",
    # Not actually Smithers - this is Burns' computer speaking TO him. Too funny to omit.
    ("Hello, Smithers. You're quite good at turning me on. You probably should ignore that."),
)


def get_random_quote() -> str:
    """Return a random Smithers quote."""
    return random.choice(SMITHERS_QUOTES)


def print_random_quote() -> None:
    """Print a random Smithers quote (for use at app startup)."""
    selected_quote = get_random_quote()
    console.print(f'[dim italic]"{selected_quote}"[/dim italic]')
    console.print()


def quote() -> None:
    """Print a sycophantic Smithers quote."""
    print_header("Smithers Quote Mode")
    line = get_random_quote()
    console.print(f"[cyan]{line}[/cyan]")
