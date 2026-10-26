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
        "Color of Mario’s Underwear...",
        "How Much Does a Totodile weigh?",
        "Can Kirby Choke?",
        "Is Waluigi Employed?",
        "Does Link Have a Lisp?",
        "What is Sonic's Ringtone?",
        "Does Bowser Pay Child Support?",
        "Is PacMan Unhappy in his Marriage?",
        "How Does Luigi Afford His Mansion?",
        "Can You Legally Own a Chocobo?",
        "What Do Slimes Taste Like?",
        "Pics of the Master Cheeks...",
        "Geralt's Coffee Order...",
        "Did Han Shoot First?",
        "Looking for a Land Card...",
        "Can You Legally Adopt a Mimic?",
        "Can You Play BlueEyes White Dragon in Court?",
        "Is Exodia Just 5 Pieces of Expensive Paper?",
        "How Many Friendships Has Catan Destroyed?",
        "Can You Sue Someone for Betrayal in Diplomacy?",
        "Are PodRacers Road Legal in Utah?",
        "Teletubbies Magic Crossover....",
        "Half-Life Four Release Date",
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