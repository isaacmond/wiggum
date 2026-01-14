"""Secret quote mode - prints sycophantic Smithers quotes."""

import random

from smithers.console import console, print_header

SMITHERS_QUOTES: tuple[str, ...] = (
    # Sycophantic Devotion
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
    "Oh, you never cease to amaze me, sir.",
    "You looken sharpen todayen, Mein Herr.",
    "You are noble and poetic in defeat, sir.",
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
    # Unflappable Loyalty
    "Right, sir. It's... scalding me as we speak.",
    "But sir, I'm flaming!",
    "Careful, Smithers, that sponge has corners, you know. I'll go find a spherical one, sir.",
    "I think women and seamen don't mix.",
    "Oh the money you've contributed to anti-helmet laws has really paid off, sir.",
    "Oh my God, Mr. Burns is dead! Why do the good always die so young?",
    # Miscellaneous
    "They're fighting like Iran and Iraq! ...Persia and Mesopotamia.",
    "Hello Smithers. You're quite good at turning me on. Uh... you probably should ignore that.",
    "Absolutely, sir. Boy, would I!",
    "Priceless sir, you made the word 'ceremonies' frightening.",
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
