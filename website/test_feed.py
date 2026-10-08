import random
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase

from website.feed import (
    build_dynamic_feed,
    ceil_percent,
    pick_newest,
    pick_popular,
    pick_random,
    visible_articles,
)
from website.models import Adverts, Articles, Logic, Sites

TODAY = date(2026, 10, 8)
GOOD_IMAGE = "https://img.example.com/picture.jpg"


class CeilPercentTests(SimpleTestCase):
    def test_rounds_up_uneven_numbers(self):
        self.assertEqual(ceil_percent(97, 50), 49)
        self.assertEqual(ceil_percent(97, 30), 30)
        self.assertEqual(ceil_percent(97, 20), 20)

    def test_exact_numbers_are_not_rounded_up(self):
        self.assertEqual(ceil_percent(100, 50), 50)
        self.assertEqual(ceil_percent(100, 30), 30)
        self.assertEqual(ceil_percent(100, 20), 20)

    def test_zero(self):
        self.assertEqual(ceil_percent(0, 50), 0)


class FeedTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.cards = Logic.objects.create(logic_type="CATEGORY", value="Card Games")
        cls.board = Logic.objects.create(logic_type="CATEGORY", value="Board Games")
        cls.news = Logic.objects.create(logic_type="TAG", value="News")
        cls.industry = Logic.objects.create(logic_type="TAG", value="Industry")
        cls.small = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        cls.medium = Logic.objects.create(logic_type="AD_SIZE", value="Feed Medium")
        cls.large = Logic.objects.create(logic_type="AD_SIZE", value="Feed Large")

    def make_site(self, name, category, tags=(), hidden=False):
        site = Sites.objects.create(
            name=name,
            url=f"https://{name.lower().replace(' ', '-')}.example.com",
            rss_feed=f"https://{name.lower().replace(' ', '-')}.example.com/feed",
            category=category,
            description="Test site",
            hidden=hidden,
        )
        site.tags.set(tags)
        return site

    def make_articles(self, site, count, first_age=0, image=GOOD_IMAGE, **extra):
        # Article number i was published (first_age + i) days before TODAY
        articles = [
            Articles(
                title=f"{site.name} article {i}",
                url=f"{site.url}/article-{first_age + i}",
                image_url=image,
                site=site,
                published=TODAY - timedelta(days=first_age + i),
                **extra,
            )
            for i in range(count)
        ]
        return Articles.objects.bulk_create(articles)

    def make_advert(self, title, start_offset=-5, end_offset=5, concurrency=1, size=None):
        return Adverts.objects.create(
            title=title,
            message=title,
            site_url="https://advert.example.com",
            start_date=TODAY + timedelta(days=start_offset),
            end_date=TODAY + timedelta(days=end_offset),
            concurrency=concurrency,
            advert_size=size or self.small,
        )

    def feed(self, **kwargs):
        kwargs.setdefault("today", TODAY)
        kwargs.setdefault("rng", random.Random(1))
        return build_dynamic_feed(**kwargs)

    def article_cards(self, cards):
        return [card for card in cards if not card.is_advert]

    def advert_cards(self, cards):
        return [card for card in cards if card.is_advert]


class FeedFilterTests(FeedTestCase):
    def setUp(self):
        self.video_site = self.make_site("Video Site", self.video, [self.news])
        self.card_site = self.make_site("Card Site", self.cards, [self.industry])
        self.board_site = self.make_site("Board Site", self.board, [self.news, self.industry])
        for site in (self.video_site, self.card_site, self.board_site):
            self.make_articles(site, 40)

    def site_ids(self, cards):
        return {card.item.site_id for card in self.article_cards(cards)}

    def test_no_filters_use_every_visible_site(self):
        cards = self.feed(feed_size=100)
        self.assertEqual(
            self.site_ids(cards),
            {self.video_site.pk, self.card_site.pk, self.board_site.pk},
        )

    def test_multiple_categories_are_an_or(self):
        cards = self.feed(category_ids=[self.video.pk, self.cards.pk], feed_size=60)
        self.assertEqual(self.site_ids(cards), {self.video_site.pk, self.card_site.pk})

    def test_multiple_tags_are_an_or_without_duplicates(self):
        cards = self.feed(tag_ids=[self.news.pk, self.industry.pk], feed_size=100)
        ids = [card.item.pk for card in self.article_cards(cards)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            self.site_ids(cards),
            {self.video_site.pk, self.card_site.pk, self.board_site.pk},
        )

    def test_category_and_tag_must_both_match(self):
        cards = self.feed(category_ids=[self.video.pk, self.board.pk], tag_ids=[self.industry.pk])
        self.assertEqual(self.site_ids(cards), {self.board_site.pk})

    def test_restrictive_filter_returns_fewer_cards(self):
        cards = self.feed(category_ids=[self.video.pk], feed_size=100)
        self.assertEqual(len(cards), 40)

    def test_filter_with_no_matching_sites_returns_nothing(self):
        cards = self.feed(category_ids=[self.video.pk], tag_ids=[self.industry.pk])
        self.assertEqual(cards, [])


class FeedVisibilityTests(FeedTestCase):
    def test_hidden_articles_and_sites_never_appear(self):
        visible_site = self.make_site("Visible Site", self.video)
        hidden_site = self.make_site("Hidden Site", self.video, hidden=True)
        self.make_articles(visible_site, 30)
        self.make_articles(hidden_site, 30)
        hidden_article = Articles.objects.filter(site=visible_site).first()
        hidden_article.hidden = True
        hidden_article.save()
        site_hidden_article = Articles.objects.filter(site=visible_site).last()
        site_hidden_article.site_hide = True
        site_hidden_article.save()

        cards = self.feed(feed_size=200)
        ids = {card.item.pk for card in cards}
        self.assertEqual(len(ids), 28)
        self.assertNotIn(hidden_article.pk, ids)
        self.assertNotIn(site_hidden_article.pk, ids)
        self.assertEqual({card.item.site_id for card in cards}, {visible_site.pk})


class FeedBucketTests(FeedTestCase):
    def setUp(self):
        self.site = self.make_site("Only Site", self.video)
        self.make_articles(self.site, 200)
        self.pool = visible_articles()

    def test_total_is_one_hundred_without_adverts(self):
        cards = self.feed(feed_size=100)
        self.assertEqual(len(cards), 100)
        ids = [card.item.pk for card in cards]
        self.assertEqual(len(ids), len(set(ids)))

    def test_newest_articles_are_always_included(self):
        newest_ids = {
            article.pk
            for article in Articles.objects.filter(published__gte=TODAY - timedelta(days=49))
        }
        cards = self.feed(feed_size=100)
        feed_ids = {card.item.pk for card in cards}
        self.assertTrue(newest_ids.issubset(feed_ids))

    def test_newest_tie_breaks_on_lowest_run_id(self):
        Articles.objects.all().delete()
        Articles.objects.bulk_create(
            [
                Articles(
                    title=f"Run {run_id}",
                    url=f"{self.site.url}/run-{run_id}",
                    image_url=GOOD_IMAGE,
                    site=self.site,
                    published=TODAY,
                    run_id=run_id,
                )
                for run_id in (5, 3, 4)
            ]
        )
        newest = pick_newest(visible_articles(), 2)
        self.assertEqual([article.run_id for article in newest], [3, 4])

    def test_random_articles_are_older_than_seven_days(self):
        picked = pick_random(self.pool, 30, set(), TODAY, random.Random(2))
        self.assertEqual(len(picked), 30)
        cutoff = TODAY - timedelta(days=7)
        self.assertTrue(all(article.published < cutoff for article in picked))

    def test_random_skips_excluded_articles(self):
        old_ids = set(
            Articles.objects.filter(published__lt=TODAY - timedelta(days=7)).values_list("pk", flat=True)
        )
        picked = pick_random(self.pool, 30, old_ids, TODAY, random.Random(2))
        self.assertEqual(picked, [])

    def test_random_returns_fewer_when_not_enough_old_articles(self):
        Articles.objects.filter(published__lt=TODAY - timedelta(days=10)).delete()
        picked = pick_random(self.pool, 30, set(), TODAY, random.Random(2))
        self.assertEqual(len(picked), 3)

    def test_popular_comes_from_the_top_ranked_and_skips_excluded(self):
        # Articles aged 0-149 days get 150-1 clicks, so the youngest are the most popular
        for article in Articles.objects.filter(published__gte=TODAY - timedelta(days=149)):
            clicks = 150 - (TODAY - article.published).days
            Articles.objects.filter(pk=article.pk).update(clicks=clicks)
        ranked_ids = list(Articles.objects.order_by("-rank", "pk").values_list("pk", flat=True))
        excluded = set(ranked_ids[:10])
        picked = pick_popular(self.pool, 20, excluded, random.Random(3))
        picked_ids = {article.pk for article in picked}
        self.assertEqual(len(picked), 20)
        self.assertTrue(picked_ids.isdisjoint(excluded))
        # With 10 excluded, the next ranked articles fill the pool, which is still 100 deep
        self.assertTrue(picked_ids.issubset(set(ranked_ids[:110])))

    def test_popular_returns_fewer_when_pool_is_small(self):
        picked = pick_popular(self.pool, 500, set(), random.Random(3))
        self.assertEqual(len(picked), 200)

    def test_feed_is_shuffled_not_in_bucket_order(self):
        cards = self.feed(feed_size=100)
        published = [card.item.published for card in cards]
        self.assertNotEqual(published, sorted(published, reverse=True))


class FeedRoundingTests(FeedTestCase):
    def test_uneven_article_count_rounds_up_each_bucket(self):
        site = self.make_site("Only Site", self.video)
        self.make_articles(site, 300)
        for index in range(3):
            self.make_advert(f"Advert {index}")
        cards = self.feed(feed_size=100)
        self.assertEqual(len(self.advert_cards(cards)), 3)
        # 97 article slots become 49 + 30 + 20
        self.assertEqual(len(self.article_cards(cards)), 99)
        self.assertEqual(len(cards), 102)


class FeedAdvertTests(FeedTestCase):
    def setUp(self):
        self.site = self.make_site("Only Site", self.video)
        self.make_articles(self.site, 300)

    def advert_indexes(self, cards):
        return [index for index, card in enumerate(cards) if card.is_advert]

    def test_only_live_adverts_are_used(self):
        live = self.make_advert("Live")
        self.make_advert("Ended", start_offset=-20, end_offset=-1)
        self.make_advert("Not started", start_offset=1, end_offset=20)
        cards = self.feed()
        self.assertEqual([card.item for card in self.advert_cards(cards)], [live])

    def test_end_date_is_inclusive(self):
        self.make_advert("Last day", start_offset=-5, end_offset=0)
        self.assertEqual(len(self.advert_cards(self.feed())), 1)

    def test_concurrency_sets_how_many_times_an_advert_appears(self):
        one = self.make_advert("One", concurrency=1)
        two = self.make_advert("Two", concurrency=2)
        items = [card.item for card in self.advert_cards(self.feed())]
        self.assertEqual(items.count(one), 1)
        self.assertEqual(items.count(two), 2)

    def test_advert_with_zero_concurrency_never_appears(self):
        self.make_advert("Silent", concurrency=0)
        self.assertEqual(self.advert_cards(self.feed()), [])

    def test_never_in_first_five_and_spaced_apart(self):
        self.make_advert("One", concurrency=3)
        self.make_advert("Two", concurrency=4)
        for seed in range(10):
            cards = self.feed(rng=random.Random(seed))
            indexes = self.advert_indexes(cards)
            self.assertEqual(len(indexes), 7)
            self.assertGreaterEqual(indexes[0], 5)
            for earlier, later in zip(indexes, indexes[1:]):
                self.assertGreaterEqual(later - earlier - 1, 5)

    def test_adverts_are_spread_evenly(self):
        self.make_advert("One", concurrency=3)
        indexes = self.advert_indexes(self.feed())
        gaps = [later - earlier for earlier, later in zip(indexes, indexes[1:])]
        self.assertLessEqual(max(gaps) - min(gaps), 1)

    def test_advert_size_comes_from_the_model(self):
        self.make_advert("Big", size=self.large)
        self.make_advert("Mid", size=self.medium)
        self.make_advert("Small", size=self.small)
        sizes = {card.item.title: card.size for card in self.advert_cards(self.feed())}
        self.assertEqual(sizes, {"Big": "large", "Mid": "medium", "Small": "small"})

    def test_restrictive_filter_falls_back_to_one_advert_at_the_end(self):
        tiny_site = self.make_site("Tiny Site", self.cards)
        self.make_articles(tiny_site, 8)
        self.make_advert("Later", start_offset=-1, concurrency=2)
        earliest = self.make_advert("Earliest", start_offset=-9)
        cards = self.feed(category_ids=[self.cards.pk])
        self.assertEqual(len(cards), 9)
        self.assertTrue(cards[-1].is_advert)
        self.assertEqual(cards[-1].item, earliest)
        self.assertEqual(len(self.advert_cards(cards)), 1)

    def test_too_many_adverts_for_the_feed_falls_back_to_one(self):
        earliest = self.make_advert("Earliest", start_offset=-9)
        self.make_advert("Greedy", concurrency=30)
        cards = self.feed(feed_size=100)
        self.assertEqual(len(self.advert_cards(cards)), 1)
        self.assertEqual(cards[-1].item, earliest)
        # One advert slot, so 99 article slots round up to 50 + 30 + 20
        self.assertEqual(len(cards), 101)

    def test_single_advert_with_enough_articles_is_not_at_the_end(self):
        self.make_advert("Only")
        cards = self.feed()
        index = self.advert_indexes(cards)[0]
        self.assertGreaterEqual(index, 5)
        self.assertLess(index, len(cards) - 1)

    def test_no_adverts_when_none_are_live(self):
        self.assertEqual(self.advert_cards(self.feed()), [])


class FeedSizeTests(FeedTestCase):
    def sizes(self, cards):
        counts = {"small": 0, "medium": 0, "large": 0}
        for card in self.article_cards(cards):
            counts[card.size] += 1
        return counts

    def test_ten_percent_large_thirty_percent_medium_rest_small(self):
        site = self.make_site("Only Site", self.video)
        self.make_articles(site, 300)
        counts = self.sizes(self.feed(feed_size=100))
        self.assertEqual(counts, {"large": 10, "medium": 30, "small": 60})

    def test_adverts_are_not_counted_in_the_size_totals(self):
        site = self.make_site("Only Site", self.video)
        self.make_articles(site, 300)
        self.make_advert("Big", size=self.large)
        counts = self.sizes(self.feed(feed_size=100))
        # 99 article slots round up to 100 articles, so the adverts do not change the sizes
        self.assertEqual(counts, {"large": 10, "medium": 30, "small": 60})

    def test_articles_without_a_valid_image_are_always_small(self):
        site = self.make_site("Only Site", self.video)
        self.make_articles(site, 100, image="")
        self.make_articles(site, 100, first_age=100, image="not-a-link")
        counts = self.sizes(self.feed(feed_size=100))
        self.assertEqual(counts, {"large": 0, "medium": 0, "small": 100})

    def test_few_images_fill_large_first(self):
        site = self.make_site("Only Site", self.video)
        # The 5 articles with an image are the newest, so they are always in the feed
        self.make_articles(site, 5, first_age=0, image=GOOD_IMAGE)
        self.make_articles(site, 195, first_age=5, image="")
        counts = self.sizes(self.feed(feed_size=100))
        self.assertEqual(counts, {"large": 5, "medium": 0, "small": 95})
