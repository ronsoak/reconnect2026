# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Seed Date
#
# This is a data file called by another script to populate the databases after deployment.
#
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
LOGIC = {
    "AD_SIZE": [
        "Feed Small",
        "Feed Medium",
        "Feed Large",
    ],
    "CATEGORY": [
        "Video Games",
        "Tabletop",
        "TCG's",
        "TTRPGs",        
    ],    

    "CLICK_TYPE": [
        "Article",
        "Advert",
        "RSS",
    ],

    "KEYWORD": [
        "Coming Soon",
        "Hogwarts",
        "Layoff",
        "Layoffs",
    ],

    # Titles containing one of these whole words are left out of the newsletter export
    "NEWSLETTER_EXCLUDED_TERM": [
        "Review",
    ],

    # Silly phrases shown at random in the search bar. Add your own here or in the admin.
    "SEARCH_PLACEHOLDER": [
        "Search articles, games, topics, and more...",
        "Color of Mario’s Underwear",
        "How Much Does a Totodile weigh?",
        "Who Pays for the Roads in Mario Kart?",
        "Can Kirby Choke?",
        "Is Waluigi Employed?",
        "How Does Sonic Pay His Taxes?",
        "Can Sims Swim?",
        "Does Link Have a Lisp?",
        "How Many Rings Has Sonic Eaten?",
        "Does Bowser Pay Child Support?",
        "Is Pac-Man Unhappy in his Marriage?",
        "Why Do Pokémon Trainers Never Age?",
        "How Does Luigi Afford His Mansion?",
        "Can You Legally Own a Chocobo?",
        "Do NPCs Know They're NPCs?",
        "Is the Mushroom Kingdom a Dictatorship?",
        "What Do Slimes Taste Like",
        "Do Dark Souls NPCs sweat?",
        "Pics of the Master Cheeks",
        "Geralt's Coffee Order",
        "Did Han Shoot First?",
        "Looking for a Land Card",
        "Can You Legally Adopt a Mimic?",
        "How Much Child Support Does a Bard Owe?",
        "Can You Seduce a Door?",
        "Do Paladins Have to Pay Taxes on Loot?",
        "How Do Druids Feel About Indoor Plumbing?",
        "Could a Level 20 Peasant Beat a Level 1 Dragon?",
        "Is My Dungeon Master Legally Allowed to Do That?",
        "Can You Play Blue-Eyes White Dragon in Court?",
        "How Much Is Too Much to Spend on Cardboard?",
        "Could a Pokémon Card Defeat a Lion?",
        "Is Exodia Just Five Pieces of Extremely Expensive Paper?",
        "Can You Declare Bankruptcy During a Booster Box Opening?",
        "Is There a Lore Reason This Card Costs $400?",
        "How Many Friendships Has Catan Destroyed?",
        "Can You Sue Someone for Betrayal in Diplomacy?",
        "Why Does Nobody Actually Finish a game of Risk?",
        "Could Batman Survive a D&D Campaign?",
        "Are Pod-Racers Road Legal in Utah?",

    ],

    "SITE_TYPE": [
        "Substack",
        "Medium",
        "Blogspot",
        "Website",
    ],

    "TAG": [
        "News",
        "Reviews",
        "Retro",
        "Indie",
        "History",
        "Analytics",
        "Design",
        "Industry",
        "Commentary",
    ]
}