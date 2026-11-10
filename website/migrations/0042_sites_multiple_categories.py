from django.db import migrations, models
import django.db.models.deletion


def copy_category_to_categories(apps, schema_editor):
    Site = apps.get_model("website", "Sites")
    for site in Site.objects.only("pk", "category_id").iterator():
        site.categories.add(site.category_id)


def restore_category(apps, schema_editor):
    Site = apps.get_model("website", "Sites")
    for site in Site.objects.iterator(chunk_size=500):
        category_ids = list(site.categories.values_list("pk", flat=True)[:2])
        if len(category_ids) > 1:
            raise RuntimeError(
                "Cannot restore the single-category schema while a site has multiple categories."
            )
        if category_ids:
            site.category_id = category_ids[0]
            site.save(update_fields=["category"])


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0041_contact_message"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.ForeignKey(
                    limit_choices_to={"logic_type": "CATEGORY"},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="site_category_links",
                    to="website.logic",
                )),
                ("site", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="category_links",
                    to="website.sites",
                )),
            ],
            options={
                "db_table": "site_categories",
                "constraints": [
                    models.UniqueConstraint(fields=("site", "category"), name="unique_site_category")
                ],
            },
        ),
        migrations.AddField(
            model_name="sites",
            name="categories",
            field=models.ManyToManyField(
                help_text="Select one or more categories for this site",
                limit_choices_to={"logic_type": "CATEGORY"},
                related_name="site_categories",
                to="website.logic",
                verbose_name="Categories",
                through="website.SiteCategory",
            ),
        ),
        migrations.RunPython(copy_category_to_categories, restore_category),
        migrations.RemoveIndex(
            model_name="sites",
            name="site_hidden_category_idx",
        ),
        migrations.RemoveField(
            model_name="sites",
            name="category",
        ),
    ]
