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