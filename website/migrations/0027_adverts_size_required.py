from django.db import migrations, models
import django.db.models.deletion


def fill_missing_advert_sizes(apps, schema_editor):
    # Any advert saved without a size becomes "Feed Small" so the column can be made required.
    # Does nothing when every advert already has a size, or when there are no adverts.
    Adverts = apps.get_model('website', 'Adverts')
    Logic = apps.get_model('website', 'Logic')
    missing = Adverts.objects.filter(advert_size__isnull=True)
    if not missing.exists():
        return
    small, _ = Logic.objects.get_or_create(logic_type='AD_SIZE', value='Feed Small')
    missing.update(advert_size=small)


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0026_sites_recap'),
    ]

    operations = [
        migrations.RunPython(fill_missing_advert_sizes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='adverts',
            name='advert_size',
            field=models.ForeignKey(help_text='The size of this advert', limit_choices_to={'logic_type': 'AD_SIZE'}, on_delete=django.db.models.deletion.PROTECT, related_name='advert_size', to='website.logic', verbose_name='Advert Size'),
        ),
    ]
